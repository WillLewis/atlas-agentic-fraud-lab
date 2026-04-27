"""Phase 7 per-family applier tests.

Policy fix:
  * apply writes versioned YAML under outputs/decision_thresholds/.
  * persisted config/decision_thresholds.yaml NEVER mutated.
  * action_rate_limits + customer_friction_tolerances copied verbatim.
  * judge ``_config_for_version`` resolves the alternate.

Calibration fix:
  * apply uses train+validation only — no holdout fitting.
  * candidate version embedded in feature_columns.json + summary.json.

Feature fix:
  * candidate has 15-column feature_columns.json (public /score
    contract preserved).
  * candidate model is a sklearn Pipeline with the transformer.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "synthetic"
BASELINE_THRESHOLDS_PATH = REPO_ROOT / "config" / "decision_thresholds.yaml"

from atlas.blue_team.feature_fix_agent import (
    ALLOWED_FEATURE_TRANSFORMS, _FeatureFixTransformer,
    apply_feature_fix, propose_feature_fix,
)
from atlas.blue_team.manifest import DefensiveFixManifest
from atlas.blue_team.model_calibration_fix_agent import (
    apply_calibration_fix, candidate_models_dir, propose_calibration_fix,
)
from atlas.blue_team.policy_fix_agent import (
    alternate_thresholds_dir, apply_policy_fix, propose_policy_fix,
)


@pytest.fixture
def outputs(tmp_path) -> Path:
    return tmp_path / "outputs"


# ===========================================================================
# Policy fix
# ===========================================================================


def test_propose_policy_fix_per_family():
    """Phase 11+: multiplicative factor (0.95) per family."""
    o = propose_policy_fix(
        family_id="score_boundary_cluster", baseline_challenge_threshold=0.74,
    )
    assert o == {"challenge_score_threshold": 0.703}  # 0.74 * 0.95


def test_propose_policy_fix_clamps_to_unit_interval():
    """Bounds preserved across the multiplicative factor."""
    # Very small baseline still clamps at 0.0 (positive scaler can't
    # produce a negative, but rounding may emit 0.0 for ~tiny inputs).
    low = propose_policy_fix(family_id="score_boundary_cluster", baseline_challenge_threshold=0.0)
    assert low["challenge_score_threshold"] == 0.0
    # Above-1 baseline still clamps to 1.0.
    high = propose_policy_fix(family_id="score_boundary_cluster", baseline_challenge_threshold=2.0)
    # 2.0 * 0.95 = 1.9 → clamped to 1.0
    assert high["challenge_score_threshold"] == 1.0


def test_propose_policy_fix_relative_to_fitted_baseline_regime():
    """Phase 11+: factor is meaningful at any baseline regime, including
    the fitted-low ~0.06 range. The blind ``-0.05`` delta would have
    clamped the result to 0.0, challenging every event.
    """
    o = propose_policy_fix(
        family_id="score_boundary_cluster", baseline_challenge_threshold=0.06,
    )
    assert o["challenge_score_threshold"] == 0.057  # 0.06 * 0.95
    assert o["challenge_score_threshold"] > 0.0


def _policy_manifest():
    return DefensiveFixManifest(
        defensive_fix_id="fix_round1_score_boundary_cluster_policy_fix",
        run_id="r", round_id=1,
        vulnerability_id="mv_round1_score_boundary_cluster",
        fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.69},
    )


def test_apply_policy_fix_writes_versioned_yaml(outputs):
    candidate_version, changed = apply_policy_fix(
        _policy_manifest(), outputs_root=outputs,
    )
    assert candidate_version == "fix_round1_score_boundary_cluster_policy_fix"
    out_path = alternate_thresholds_dir(outputs) / f"{candidate_version}.yaml"
    assert out_path.exists()
    assert changed == [f"outputs/decision_thresholds/{candidate_version}.yaml"]


def test_apply_policy_fix_does_not_mutate_baseline_config(outputs):
    """The persisted ``config/decision_thresholds.yaml`` must be byte-
    and mtime-identical before/after apply_policy_fix runs."""
    bytes_before = BASELINE_THRESHOLDS_PATH.read_bytes()
    mtime_before = BASELINE_THRESHOLDS_PATH.stat().st_mtime
    apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    bytes_after = BASELINE_THRESHOLDS_PATH.read_bytes()
    mtime_after = BASELINE_THRESHOLDS_PATH.stat().st_mtime
    assert bytes_before == bytes_after
    assert mtime_before == mtime_after


def test_apply_policy_fix_copies_friction_caps_verbatim(outputs):
    apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    candidate_path = alternate_thresholds_dir(outputs) / "fix_round1_score_boundary_cluster_policy_fix.yaml"
    with candidate_path.open() as fh:
        candidate_doc = yaml.safe_load(fh)
    with BASELINE_THRESHOLDS_PATH.open() as fh:
        baseline_doc = yaml.safe_load(fh)

    for verbatim_key in (
        "action_rate_limits",
        "customer_friction_tolerances",
        "decision_bands",
        "allowed_reason_codes",
    ):
        assert candidate_doc[verbatim_key] == baseline_doc[verbatim_key]


def test_apply_policy_fix_preserves_decline_and_alert_thresholds(outputs):
    apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    candidate_path = alternate_thresholds_dir(outputs) / "fix_round1_score_boundary_cluster_policy_fix.yaml"
    with candidate_path.open() as fh:
        candidate_doc = yaml.safe_load(fh)
    with BASELINE_THRESHOLDS_PATH.open() as fh:
        baseline_doc = yaml.safe_load(fh)
    # challenge_score_threshold updated; decline + alert preserved
    assert candidate_doc["decision_thresholds"]["challenge_score_threshold"] == 0.69
    assert candidate_doc["decision_thresholds"]["decline_score_threshold"] == \
        baseline_doc["decision_thresholds"]["decline_score_threshold"]
    assert candidate_doc["decision_thresholds"]["alert_score_threshold"] == \
        baseline_doc["decision_thresholds"]["alert_score_threshold"]


def test_apply_policy_fix_byte_identical_on_repeat(outputs):
    candidate_version, _ = apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    out_path = alternate_thresholds_dir(outputs) / f"{candidate_version}.yaml"
    bytes_a = out_path.read_bytes()
    apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    bytes_b = out_path.read_bytes()
    assert bytes_a == bytes_b


def test_judge_loads_alternate_threshold_version(outputs):
    """End-to-end: apply_policy_fix → judge `_config_for_version` returns
    a config with the new challenge_score_threshold."""
    import atlas.judge.evaluate as evaluate_mod

    candidate_version, _ = apply_policy_fix(_policy_manifest(), outputs_root=outputs)
    original_root = evaluate_mod.ALTERNATE_THRESHOLDS_ROOT
    evaluate_mod.ALTERNATE_THRESHOLDS_ROOT = alternate_thresholds_dir(outputs)
    evaluate_mod.reset_caches()
    try:
        config = evaluate_mod._config_for_version(candidate_version)
        assert config.threshold_version == candidate_version
        assert config.challenge_score_threshold == 0.69
    finally:
        evaluate_mod.ALTERNATE_THRESHOLDS_ROOT = original_root
        evaluate_mod.reset_caches()


def test_apply_policy_fix_rejects_wrong_fix_type(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="model_calibration_fix",
        proposed_training_seed=1001, proposed_l2_strength=0.5,
    )
    with pytest.raises(ValueError, match="apply_policy_fix"):
        apply_policy_fix(bad, outputs_root=outputs)


def test_apply_policy_fix_rejects_empty_overrides(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="policy_fix", proposed_threshold_overrides={},
    )
    with pytest.raises(ValueError, match="no proposed_threshold_overrides"):
        apply_policy_fix(bad, outputs_root=outputs)


# ===========================================================================
# Calibration fix
# ===========================================================================


def test_propose_calibration_fix_per_family():
    assert propose_calibration_fix(family_id="label_noise_mislearned") == (1001, 0.5)
    assert propose_calibration_fix(family_id="overfit_fix_failure") == (2002, 2.0)


def test_propose_calibration_fix_default_for_unmapped_family():
    assert propose_calibration_fix(family_id="some_unknown") == (3003, 1.0)


def _calibration_manifest():
    return DefensiveFixManifest(
        defensive_fix_id="fix_round2_label_noise_mislearned_model_calibration_fix",
        run_id="r", round_id=2,
        vulnerability_id="mv_round2_label_noise_mislearned",
        fix_type="model_calibration_fix",
        proposed_training_seed=1001, proposed_l2_strength=0.5,
    )


@pytest.mark.slow
def test_apply_calibration_fix_produces_non_identical_judge_metrics(
    outputs, monkeypatch, tmp_path,
):
    """Phase 11+ regression: with distribution-aware fitted thresholds,
    a calibration_fix candidate's score distribution shifts enough that
    the judge sees baseline ≠ fixed metric snapshots. Pins the
    round-loop fix; would have been all-zero deltas under the old
    all-``accept`` regime.
    """
    import atlas.judge.evaluate as evaluate_mod
    from atlas.blue_team.model_calibration_fix_agent import (
        apply_calibration_fix, candidate_models_dir,
    )
    from atlas.judge.evaluate import evaluate_fix
    from atlas.model.train import train_baseline_model

    # 1) Train the baseline into a hermetic dir; fitted thresholds land
    # under tmp_path/decision_thresholds/thresholds_v1.yaml so the
    # judge picks them up via the patched ALTERNATE_THRESHOLDS_ROOT.
    baseline_dir = candidate_models_dir(outputs) / "baseline_v1"
    train_baseline_model(
        seed=42,
        data_dir=DATA_DIR,
        output_dir=baseline_dir,
        model_version="baseline_v1",
        fitted_thresholds_dir=outputs / "decision_thresholds",
    )

    # 2) Apply the calibration_fix candidate (retrains with c_override).
    apply_calibration_fix(
        _calibration_manifest(), outputs_root=outputs, data_dir=DATA_DIR,
    )

    # 3) Point the judge at the hermetic dirs.
    monkeypatch.setattr(
        evaluate_mod, "BASELINE_MODELS_ROOT", candidate_models_dir(outputs),
    )
    monkeypatch.setattr(
        evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT",
        outputs / "decision_thresholds",
    )
    evaluate_mod.reset_caches()

    # 4) Run the judge and compare snapshots.
    candidate_id = _calibration_manifest().defensive_fix_id
    report = evaluate_fix(
        run_id="r", round_id=1, defensive_fix_id=candidate_id,
        baseline_model_version="baseline_v1",
        candidate_model_version=candidate_id,
        baseline_threshold_version="thresholds_v1",
        candidate_threshold_version="thresholds_v1",
        data_dir=DATA_DIR,
    )
    baseline = dict(report["baseline"])
    fixed = {k: v for k, v in report["fixed"].items() if k != "synthetic_loss_prevented"}
    # Pre-fix: baseline.miss_rate was 1.0 (all-accept). Post-fix: < 1.0.
    assert baseline["model_miss_rate"] < 1.0, (
        f"baseline still all-accept: {baseline}"
    )
    # Pre-fix: every fix produced byte-identical metrics. Post-fix:
    # at least one family shifts something.
    assert baseline != fixed, (
        f"calibration_fix produced byte-identical metrics: "
        f"baseline={baseline}, fixed={fixed}"
    )


@pytest.mark.slow
def test_apply_calibration_fix_uses_only_train_validation(outputs):
    """Patch ``load_features_for_partition`` and assert the trainer
    requested ONLY {train, validation} — never any holdout."""
    import atlas.model.loader as loader_mod
    real = loader_mod.load_features_for_partition
    requested: list[str] = []

    def _spy(partition, *args, **kwargs):
        requested.append(partition)
        return real(partition, *args, **kwargs)

    with mock.patch.object(loader_mod, "load_features_for_partition", side_effect=_spy):
        apply_calibration_fix(
            _calibration_manifest(),
            outputs_root=outputs, data_dir=DATA_DIR,
        )

    # Only train + validation requested — no clean / locked / drifted.
    forbidden = {"clean_holdout", "locked_adaptive_holdout", "drifted_holdout"}
    assert not (set(requested) & forbidden)
    assert set(requested) <= {"train", "validation"}


@pytest.mark.slow
def test_apply_calibration_fix_embeds_candidate_version(outputs):
    apply_calibration_fix(
        _calibration_manifest(),
        outputs_root=outputs, data_dir=DATA_DIR,
    )
    candidate_dir = candidate_models_dir(outputs) / "fix_round2_label_noise_mislearned_model_calibration_fix"
    fc = json.loads((candidate_dir / "feature_columns.json").read_text())
    assert fc["model_version"] == "fix_round2_label_noise_mislearned_model_calibration_fix"
    summary = json.loads((candidate_dir / "baseline_summary.json").read_text())
    assert summary["model_version"] == fc["model_version"]
    assert summary["train_seed"] == 1001
    assert summary["l2_strength_c"] == 0.5


@pytest.mark.slow
def test_apply_calibration_fix_writes_4_artifacts(outputs):
    apply_calibration_fix(
        _calibration_manifest(),
        outputs_root=outputs, data_dir=DATA_DIR,
    )
    candidate_dir = candidate_models_dir(outputs) / "fix_round2_label_noise_mislearned_model_calibration_fix"
    files = sorted(p.name for p in candidate_dir.iterdir())
    assert files == [
        "baseline_summary.json", "calibration.json",
        "feature_columns.json", "model.joblib",
    ]


def test_apply_calibration_fix_rejects_wrong_fix_type(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.7},
    )
    with pytest.raises(ValueError, match="apply_calibration_fix"):
        apply_calibration_fix(bad, outputs_root=outputs, data_dir=DATA_DIR)


def test_apply_calibration_fix_rejects_missing_seed(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="model_calibration_fix",
        proposed_training_seed=None, proposed_l2_strength=1.0,
    )
    with pytest.raises(ValueError, match="proposed_training_seed"):
        apply_calibration_fix(bad, outputs_root=outputs, data_dir=DATA_DIR)


# ===========================================================================
# Feature fix
# ===========================================================================


def test_propose_feature_fix_per_family():
    assert propose_feature_fix(family_id="low_velocity_high_graph_risk") == ("boost_graph_risk",)
    assert propose_feature_fix(family_id="recent_change_feature_delay") == ("boost_recent_security_signals",)
    assert propose_feature_fix(family_id="activity_channel_shift") == ("boost_geo_consistency",)
    assert propose_feature_fix(family_id="current_device_mismatch") == ("boost_current_device_tenure",)


def test_propose_feature_fix_unmapped_family_returns_empty():
    assert propose_feature_fix(family_id="overfit_fix_failure") == ()


def test_feature_fix_transformer_validates_at_construction():
    with pytest.raises(ValueError, match="unknown feature-fix transform"):
        _FeatureFixTransformer(("nonexistent_transform",))


def test_feature_fix_transformer_does_not_mutate_input():
    import numpy as np
    from atlas.model.loader import FEATURE_COLUMNS

    n_features = len(FEATURE_COLUMNS)
    x = np.zeros((2, n_features), dtype=float)
    idx = FEATURE_COLUMNS.index("entity_graph_risk_score")
    x[:, idx] = 0.4

    t = _FeatureFixTransformer(("boost_graph_risk",))
    y = t.transform(x)
    # Output is doubled
    assert y[0, idx] == 0.8
    # Input is unchanged
    assert x[0, idx] == 0.4


def _feature_manifest():
    return DefensiveFixManifest(
        defensive_fix_id="fix_round1_low_velocity_high_graph_risk_feature_fix",
        run_id="r", round_id=1,
        vulnerability_id="mv_round1_low_velocity_high_graph_risk",
        fix_type="feature_fix",
        proposed_feature_transforms=("boost_graph_risk",),
    )


@pytest.mark.slow
def test_apply_feature_fix_preserves_15_column_public_contract(outputs):
    """The public ``/score`` contract: feature_columns.json has exactly
    15 columns identical to baseline_v1."""
    apply_feature_fix(_feature_manifest(), outputs_root=outputs, data_dir=DATA_DIR)
    candidate_dir = candidate_models_dir(outputs) / "fix_round1_low_velocity_high_graph_risk_feature_fix"
    fc = json.loads((candidate_dir / "feature_columns.json").read_text())
    assert len(fc["feature_columns"]) == 15

    # Identical to baseline_v1's columns
    baseline_fc_path = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1" / "feature_columns.json"
    if baseline_fc_path.exists():
        baseline_fc = json.loads(baseline_fc_path.read_text())
        assert fc["feature_columns"] == baseline_fc["feature_columns"]


@pytest.mark.slow
def test_apply_feature_fix_persists_pipeline_with_transformer(outputs):
    """The candidate model.joblib is a sklearn Pipeline with the
    _FeatureFixTransformer as its first step."""
    import joblib
    from sklearn.pipeline import Pipeline

    apply_feature_fix(_feature_manifest(), outputs_root=outputs, data_dir=DATA_DIR)
    candidate_dir = candidate_models_dir(outputs) / "fix_round1_low_velocity_high_graph_risk_feature_fix"
    pipeline = joblib.load(candidate_dir / "model.joblib")
    assert isinstance(pipeline, Pipeline)
    pre_step = pipeline.named_steps.get("pre_model_step")
    assert pre_step is not None
    assert pre_step.transform_specs == ("boost_graph_risk",)


@pytest.mark.slow
def test_apply_feature_fix_does_not_emit_convergence_warning(outputs):
    """Phase 7 ``feature_fix`` candidates retrain via the Phase 4
    trainer with ``pre_model_step`` + ``StandardScaler``. The combo
    must converge cleanly — ``make run-rounds`` re-runs this path 3×.
    """
    import warnings

    from sklearn.exceptions import ConvergenceWarning

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        apply_feature_fix(
            _feature_manifest(), outputs_root=outputs, data_dir=DATA_DIR,
        )


@pytest.mark.slow
def test_apply_feature_fix_score_path_works_with_unmodified_feature_vector(outputs):
    """The score path takes a 17-field FeatureVector dict (unchanged)
    and produces a score. The transform is applied internally by the
    Pipeline."""
    from atlas.model.scorer import load_baseline_bundle, score_features

    apply_feature_fix(_feature_manifest(), outputs_root=outputs, data_dir=DATA_DIR)
    candidate_dir = candidate_models_dir(outputs) / "fix_round1_low_velocity_high_graph_risk_feature_fix"
    bundle = load_baseline_bundle(candidate_dir)

    fv = {
        "event_id": "tx_test", "customer_id": "cust_test",
        "login_count_72h": 2, "login_count_30d": 18, "login_velocity_ratio": 0.11,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0, "device_count_72h": 1,
        "current_device_tenure_days": 200, "geo_consistency_flag": 1,
        "transfer_count_72h": 1, "recipient_tenure_days": 50,
        "shared_device_degree": 1, "shared_recipient_degree": 1,
        "entity_graph_risk_score": 0.5, "cash_movement_velocity_score": 0.3,
    }
    score = score_features(fv, bundle)
    assert 0.0 <= score <= 1.0


def test_apply_feature_fix_rejects_wrong_fix_type(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.7},
    )
    with pytest.raises(ValueError, match="apply_feature_fix"):
        apply_feature_fix(bad, outputs_root=outputs, data_dir=DATA_DIR)


def test_apply_feature_fix_rejects_empty_transforms(outputs):
    bad = DefensiveFixManifest(
        defensive_fix_id="x", run_id="r", round_id=1, vulnerability_id="y",
        fix_type="feature_fix", proposed_feature_transforms=(),
    )
    with pytest.raises(ValueError, match="proposed_feature_transforms"):
        apply_feature_fix(bad, outputs_root=outputs, data_dir=DATA_DIR)


# ===========================================================================
# Closed-enum invariants
# ===========================================================================


def test_allowed_feature_transforms_canonical():
    assert ALLOWED_FEATURE_TRANSFORMS == frozenset({
        "boost_graph_risk",
        "boost_recent_security_signals",
        "boost_geo_consistency",
        "boost_current_device_tenure",
    })
