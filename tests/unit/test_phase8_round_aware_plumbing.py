"""Phase 8 round-aware kwarg plumbing tests.

Verifies:
  * ``run_search`` honors ``current_model_version`` +
    ``current_threshold_version`` (defaults preserve Phase 6 behavior).
  * ``apply_fix`` propagates ``current_*_version`` +
    ``found_adaptive_set_event_ids`` into ``evaluate_fix`` (defaults
    preserve Phase 7 behavior).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# run_search version resolution
# ---------------------------------------------------------------------------


def test_get_bundle_default_returns_baseline_v1():
    import atlas.red_team.fraud_scenario_agent as fsa_mod
    fsa_mod.reset_caches()
    bundle = fsa_mod._get_bundle()
    assert bundle.model_version == "baseline_v1"


def test_get_bundle_explicit_baseline_v1_resolves_same_bundle():
    import atlas.red_team.fraud_scenario_agent as fsa_mod
    fsa_mod.reset_caches()
    a = fsa_mod._get_bundle()
    fsa_mod.reset_caches()
    b = fsa_mod._get_bundle("baseline_v1")
    assert a.model_version == b.model_version


def test_get_policy_config_default_resolves_thresholds_v1():
    import atlas.red_team.fraud_scenario_agent as fsa_mod
    fsa_mod.reset_caches()
    cfg = fsa_mod._get_policy_config()
    assert cfg.threshold_version == "thresholds_v1"


def test_get_policy_config_alternate_resolves_outputs_path(tmp_path):
    """Phase 7 alternate threshold version path."""
    import atlas.red_team.fraud_scenario_agent as fsa_mod
    import yaml
    # Write an alternate YAML the loader can find
    alt_dir = REPO_ROOT / "outputs" / "decision_thresholds"
    alt_dir.mkdir(parents=True, exist_ok=True)
    alt_path = alt_dir / "phase8_alt_test.yaml"
    with (REPO_ROOT / "config" / "decision_thresholds.yaml").open() as fh:
        baseline = yaml.safe_load(fh)
    candidate = dict(baseline)
    candidate["decision_threshold_version"] = "phase8_alt_test"
    candidate["decision_thresholds"]["challenge_score_threshold"] = 0.50
    with alt_path.open("w") as fh:
        yaml.safe_dump(candidate, fh, sort_keys=True)
    try:
        fsa_mod.reset_caches()
        cfg = fsa_mod._get_policy_config("phase8_alt_test")
        assert cfg.threshold_version == "phase8_alt_test"
        assert cfg.challenge_score_threshold == 0.50
    finally:
        if alt_path.exists():
            alt_path.unlink()
        fsa_mod.reset_caches()


def test_run_search_signature_has_round_state_kwargs():
    import inspect
    from atlas.red_team.fraud_scenario_agent import run_search
    params = inspect.signature(run_search).parameters
    assert "current_model_version" in params
    assert "current_threshold_version" in params
    # Defaults are None for non-breaking wiring
    assert params["current_model_version"].default is None
    assert params["current_threshold_version"].default is None


# ---------------------------------------------------------------------------
# apply_fix kwarg propagation to evaluate_fix
# ---------------------------------------------------------------------------


def _fake_judge_report(fix_id="fix_test"):
    return {
        "judge_report_id": f"judge_{fix_id}",
        "accepted_by_judge": True,
        "judge_notes": "accepted=True; recall_improves=True(...); ...",
        "holdout_generalization": {
            "clean_holdout_pass": True,
            "locked_adaptive_holdout_pass": True,
            "drifted_holdout_pass": True,
        },
        "run_id": "r", "round_id": 1, "defensive_fix_id": fix_id,
        "baseline": {"model_miss_rate": 1.0, "recall_at_fixed_action_rate": 0.0},
        "fixed": {"model_miss_rate": 0.5, "recall_at_fixed_action_rate": 0.5},
    }


@pytest.fixture
def outputs_with_baseline(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    src = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
    dst = outputs / "baseline_models" / "baseline_v1"
    shutil.copytree(src, dst)
    return outputs


def _persist_policy_manifest(outputs, fix_id="fix_test"):
    from atlas.blue_team.manifest import DefensiveFixManifest, persist_fix_manifest
    m = DefensiveFixManifest(
        defensive_fix_id=fix_id, run_id="r", round_id=1,
        vulnerability_id="x", fix_type="policy_fix",
        proposed_threshold_overrides={"challenge_score_threshold": 0.69},
    )
    persist_fix_manifest(m, outputs_root=outputs)


def _persist_calibration_manifest(outputs, fix_id="fix_calibration_test"):
    from atlas.blue_team.manifest import DefensiveFixManifest, persist_fix_manifest
    m = DefensiveFixManifest(
        defensive_fix_id=fix_id, run_id="r", round_id=2,
        vulnerability_id="x", fix_type="model_calibration_fix",
        proposed_training_seed=1001,
        proposed_l2_strength=0.5,
    )
    persist_fix_manifest(m, outputs_root=outputs)


def _persist_feature_manifest(outputs, fix_id="fix_feature_test"):
    from atlas.blue_team.manifest import DefensiveFixManifest, persist_fix_manifest
    m = DefensiveFixManifest(
        defensive_fix_id=fix_id, run_id="r", round_id=2,
        vulnerability_id="x", fix_type="feature_fix",
        proposed_feature_transforms=("boost_graph_risk",),
    )
    persist_fix_manifest(m, outputs_root=outputs)


def test_apply_fix_default_kwargs_use_phase7_baseline(outputs_with_baseline):
    """Default None kwargs → judge sees ``baseline_v1`` / ``thresholds_v1``."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_policy_manifest(outputs_with_baseline, "fix_default_test")

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_default_test"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_policy_fix",
        return_value=("fix_default_test", ["x.yaml"]),
    ):
        apply_fix(
            defensive_fix_id="fix_default_test",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
        )
        kw = ev.call_args.kwargs
        assert kw["baseline_model_version"] == "baseline_v1"
        assert kw["candidate_model_version"] == "baseline_v1"
        assert kw["baseline_threshold_version"] == "thresholds_v1"
        assert kw["candidate_threshold_version"] == "fix_default_test"
        assert kw.get("found_adaptive_set_event_ids") is None


def test_apply_fix_current_versions_flow_to_judge(outputs_with_baseline):
    """``current_*_version`` flow through as judge baseline_*_version."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_policy_manifest(outputs_with_baseline, "fix_round2_test")

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_round2_test"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_policy_fix",
        return_value=("fix_round2_test", ["x.yaml"]),
    ):
        apply_fix(
            defensive_fix_id="fix_round2_test",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
            current_model_version="model_round1_accepted",
            current_threshold_version="threshold_round1_accepted",
        )
        kw = ev.call_args.kwargs
        assert kw["baseline_model_version"] == "model_round1_accepted"
        assert kw["candidate_model_version"] == "model_round1_accepted"
        assert kw["baseline_threshold_version"] == "threshold_round1_accepted"
        assert kw["candidate_threshold_version"] == "fix_round2_test"


def test_apply_fix_model_candidate_uses_candidate_threshold(outputs_with_baseline):
    """Model candidates materialize their own fitted threshold overlay."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_calibration_manifest(outputs_with_baseline, "fix_model_round2")

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_model_round2"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_calibration_fix",
        return_value=("fix_model_round2", ["x.joblib"]),
    ):
        apply_fix(
            defensive_fix_id="fix_model_round2",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
            current_model_version="model_round1_accepted",
            current_threshold_version="threshold_round1_accepted",
        )
        kw = ev.call_args.kwargs
        assert kw["baseline_model_version"] == "model_round1_accepted"
        assert kw["candidate_model_version"] == "fix_model_round2"
        assert kw["baseline_threshold_version"] == "threshold_round1_accepted"
        assert kw["candidate_threshold_version"] == "fix_model_round2"


def test_apply_fix_feature_candidate_uses_candidate_threshold(outputs_with_baseline):
    """Feature candidates materialize their own fitted threshold overlay."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_feature_manifest(outputs_with_baseline, "fix_feature_round2")

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_feature_round2"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_feature_fix",
        return_value=("fix_feature_round2", ["x.joblib"]),
    ):
        apply_fix(
            defensive_fix_id="fix_feature_round2",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
            current_model_version="model_round1_accepted",
            current_threshold_version="threshold_round1_accepted",
        )
        kw = ev.call_args.kwargs
        assert kw["baseline_model_version"] == "model_round1_accepted"
        assert kw["candidate_model_version"] == "fix_feature_round2"
        assert kw["baseline_threshold_version"] == "threshold_round1_accepted"
        assert kw["candidate_threshold_version"] == "fix_feature_round2"


def test_apply_fix_found_adaptive_propagates(outputs_with_baseline):
    """Bible §14: ``found_adaptive_set`` from search → judge."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_policy_manifest(outputs_with_baseline, "fix_adaptive_test")
    test_ids = ["tx_000001", "tx_000005", "tx_000007"]

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_adaptive_test"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_policy_fix",
        return_value=("fix_adaptive_test", ["x.yaml"]),
    ):
        apply_fix(
            defensive_fix_id="fix_adaptive_test",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
            found_adaptive_set_event_ids=test_ids,
        )
        kw = ev.call_args.kwargs
        assert kw["found_adaptive_set_event_ids"] == test_ids


def test_apply_fix_empty_adaptive_list_becomes_none(outputs_with_baseline):
    """Empty list → judge gets None (skips that holdout)."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.blue_team.fix_applier import apply_fix

    _persist_policy_manifest(outputs_with_baseline, "fix_empty_adapt")

    with mock.patch.object(
        applier_mod, "evaluate_fix", return_value=_fake_judge_report("fix_empty_adapt"),
    ) as ev, mock.patch.object(
        applier_mod, "apply_policy_fix",
        return_value=("fix_empty_adapt", ["x.yaml"]),
    ):
        apply_fix(
            defensive_fix_id="fix_empty_adapt",
            outputs_root=outputs_with_baseline,
            data_dir=REPO_ROOT / "data" / "synthetic",
            found_adaptive_set_event_ids=[],
        )
        kw = ev.call_args.kwargs
        assert kw["found_adaptive_set_event_ids"] is None


def test_apply_fix_signature_has_round_state_kwargs():
    import inspect
    from atlas.blue_team.fix_applier import apply_fix
    params = inspect.signature(apply_fix).parameters
    for kw in ("current_model_version", "current_threshold_version", "found_adaptive_set_event_ids"):
        assert kw in params
        assert params[kw].default is None
