"""Phase 8 round_engine tests.

Single-round execution: deterministic candidate selection, carry-forward
semantics, safety_scan flow, ledger row shape.

Helper fixture builds an outputs_root with a mirrored ``baseline_v1``
and patches the judge globals so the tests are hermetic.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def hermetic_outputs(tmp_path, monkeypatch):
    """Build an outputs_root with baseline_v1 + patch judge globals.

    Mirrors the ``api_client`` fixture's monkey-patches but for direct
    Python-level tests of the round engine (no FastAPI app needed).
    """
    import atlas.judge.evaluate as evaluate_mod
    import atlas.ledger.round_engine as re_mod
    from atlas.ledger.report_builder import reset_caches as reset_report_caches

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    src = REPO_ROOT / "outputs" / "baseline_models" / "baseline_v1"
    dst = outputs / "baseline_models" / "baseline_v1"
    shutil.copytree(src, dst)

    monkeypatch.setattr(
        evaluate_mod, "BASELINE_MODELS_ROOT", outputs / "baseline_models"
    )
    monkeypatch.setattr(
        evaluate_mod, "ALTERNATE_THRESHOLDS_ROOT",
        outputs / "decision_thresholds",
    )
    evaluate_mod.reset_caches()
    re_mod.reset_caches()
    reset_report_caches()
    yield outputs
    evaluate_mod.reset_caches()
    re_mod.reset_caches()
    reset_report_caches()


def _build_run_state(outputs):
    from atlas.ledger.ledger import (
        RunState, make_run_id, read_dataset_reference_now_utc,
    )
    return RunState(
        run_id=make_run_id(seed=42, run_label="rt_test", demo_mode="public"),
        seed=42,
        demo_mode="public",
        status="running",
        created_at_utc=read_dataset_reference_now_utc(REPO_ROOT / "data" / "synthetic"),
        current_round=0,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt_test",
        max_rounds=3,
    )


# ---------------------------------------------------------------------------
# Deterministic candidate selection
# ---------------------------------------------------------------------------


def test_select_candidates_orders_by_miss_rate_descending():
    from atlas.blue_team.strategy_agent import DefensiveFixCandidate
    from atlas.ledger.round_engine import _select_candidates
    from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard

    cards = [
        ModelVulnerabilityCard(
            model_vulnerability_id=f"mv_round1_{fam}",
            round_id=1, family_id=fam, summary="...",
            valid_high_risk_events_tested=10, accepted_high_risk_events=10,
            model_miss_rate=miss, miss_rate_lift_vs_random=1.0,
            estimated_synthetic_loss_allowed=1000.0,
            affected_decision_action="accept",
            safe_cohort_definition={}, recommended_defensive_fix_types=("policy_fix",),
        )
        for fam, miss in [
            ("low_velocity_high_graph_risk", 0.3),
            ("score_boundary_cluster", 0.9),
            ("activity_channel_shift", 0.6),
        ]
    ]
    cands = [
        DefensiveFixCandidate(
            defensive_fix_id=f"fix_round1_{fam}_policy_fix",
            round_id=1, fix_type="policy_fix",
            description="...", expected_benefit="...",
        )
        for fam in ("low_velocity_high_graph_risk", "score_boundary_cluster", "activity_channel_shift")
    ]

    sel = _select_candidates(cands, cards, seed=42, round_id=1, k=3)
    # Highest miss_rate (0.9) → first
    assert sel[0].defensive_fix_id == "fix_round1_score_boundary_cluster_policy_fix"
    assert sel[1].defensive_fix_id == "fix_round1_activity_channel_shift_policy_fix"
    assert sel[2].defensive_fix_id == "fix_round1_low_velocity_high_graph_risk_policy_fix"


def test_select_candidates_top_k_one():
    from atlas.blue_team.strategy_agent import DefensiveFixCandidate
    from atlas.ledger.round_engine import _select_candidates
    from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard

    cards = [
        ModelVulnerabilityCard(
            model_vulnerability_id="mv_round1_a", round_id=1, family_id="a",
            summary="...", valid_high_risk_events_tested=1,
            accepted_high_risk_events=1, model_miss_rate=0.5,
            miss_rate_lift_vs_random=1.0, estimated_synthetic_loss_allowed=0.0,
            affected_decision_action="accept", safe_cohort_definition={},
            recommended_defensive_fix_types=(),
        ),
    ]
    cands = [
        DefensiveFixCandidate(defensive_fix_id="fix_round1_a_policy_fix", round_id=1, fix_type="policy_fix", description="", expected_benefit=""),
        DefensiveFixCandidate(defensive_fix_id="fix_round1_a_feature_fix", round_id=1, fix_type="feature_fix", description="", expected_benefit=""),
    ]
    top1 = _select_candidates(cands, cards, seed=42, round_id=1, k=1)
    assert len(top1) == 1


def test_select_candidates_empty_returns_empty():
    from atlas.ledger.round_engine import _select_candidates
    assert _select_candidates([], [], seed=42, round_id=1, k=1) == []


def test_select_candidates_input_order_independent():
    """Different input order → same selected output (deterministic)."""
    from atlas.blue_team.strategy_agent import DefensiveFixCandidate
    from atlas.ledger.round_engine import _select_candidates
    from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard

    cards = [
        ModelVulnerabilityCard(
            model_vulnerability_id=f"mv_round1_{fam}",
            round_id=1, family_id=fam, summary="",
            valid_high_risk_events_tested=10, accepted_high_risk_events=10,
            model_miss_rate=miss, miss_rate_lift_vs_random=1.0,
            estimated_synthetic_loss_allowed=0.0,
            affected_decision_action="accept", safe_cohort_definition={},
            recommended_defensive_fix_types=("policy_fix",),
        )
        for fam, miss in [("a", 0.3), ("b", 0.9), ("c", 0.6)]
    ]
    cands_forward = [
        DefensiveFixCandidate(defensive_fix_id=f"fix_round1_{f}_policy_fix", round_id=1, fix_type="policy_fix", description="", expected_benefit="")
        for f in ("a", "b", "c")
    ]
    cands_reversed = list(reversed(cands_forward))
    sel_forward = _select_candidates(cands_forward, cards, seed=42, round_id=1, k=3)
    sel_reversed = _select_candidates(cands_reversed, cards, seed=42, round_id=1, k=3)
    assert sel_forward == sel_reversed


def test_select_candidates_uses_seed_for_equal_severity_ties():
    """Equal-severity candidates should not collapse to alphabetical order."""
    from atlas.blue_team.strategy_agent import DefensiveFixCandidate
    from atlas.ledger.round_engine import _select_candidates
    from atlas.red_team.model_vulnerability_packager import ModelVulnerabilityCard

    cards = [
        ModelVulnerabilityCard(
            model_vulnerability_id=f"mv_round1_{fam}",
            round_id=1, family_id=fam, summary="",
            valid_high_risk_events_tested=10, accepted_high_risk_events=10,
            model_miss_rate=1.0, miss_rate_lift_vs_random=1.0,
            estimated_synthetic_loss_allowed=0.0,
            affected_decision_action="accept", safe_cohort_definition={},
            recommended_defensive_fix_types=("policy_fix",),
        )
        for fam in ("a", "b")
    ]
    cands = [
        DefensiveFixCandidate(defensive_fix_id=f"fix_round1_{f}_policy_fix", round_id=1, fix_type="policy_fix", description="", expected_benefit="")
        for f in ("a", "b")
    ]

    first = _select_candidates(cands, cards, seed=1, round_id=1, k=1)
    second = _select_candidates(cands, cards, seed=3, round_id=1, k=1)

    assert first[0].defensive_fix_id != second[0].defensive_fix_id


# ---------------------------------------------------------------------------
# Single-round execution (real data, slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_execute_one_round_produces_round_state(hermetic_outputs):
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    rs = execute_one_round(
        run_state, round_id=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    assert rs.run_id == run_state.run_id
    assert rs.round_id == 1
    assert rs.status == "completed"
    # before == carry-forward versions; after either equals before
    # (rejected) or differs (accepted).
    assert rs.model_version_before == "baseline_v1"
    assert rs.threshold_version_before == "thresholds_v1"


@pytest.mark.slow
def test_execute_one_round_persists_round_state(hermetic_outputs):
    from atlas.ledger.ledger import load_round_state
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    rs = execute_one_round(
        run_state, round_id=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    loaded = load_round_state(run_state.run_id, 1, outputs_root=hermetic_outputs)
    assert loaded == rs


@pytest.mark.slow
def test_execute_one_round_appends_ledger_row(hermetic_outputs):
    from atlas.ledger.ledger import load_ledger_records
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    execute_one_round(
        run_state, round_id=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    rows = load_ledger_records(run_state.run_id, outputs_root=hermetic_outputs)
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == run_state.run_id
    assert row["round_id"] == 1
    assert row["model_version_before"] == "baseline_v1"
    assert row["decision_threshold_version_before"] == "thresholds_v1"


@pytest.mark.slow
def test_execute_one_round_safety_scan_passed_true(hermetic_outputs):
    """Closed-enum templates pass the production safety rules."""
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    rs = execute_one_round(
        run_state, round_id=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    assert rs.safety_scan_passed is True
    assert rs.transcript_summary  # non-empty


@pytest.mark.slow
def test_execute_one_round_carry_forward_when_rejected(hermetic_outputs):
    """Real data: rounds reject (model_miss_rate=1.0 dataset state) → versions hold."""
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    rs = execute_one_round(
        run_state, round_id=1,
        outputs_root=hermetic_outputs,
        data_dir=REPO_ROOT / "data" / "synthetic",
    )
    if not rs.accepted_fix_id:
        # Rejected → versions hold.
        assert rs.model_version_after == rs.model_version_before
        assert rs.threshold_version_after == rs.threshold_version_before


# ---------------------------------------------------------------------------
# Carry-forward when judge ACCEPTS (mocked)
# ---------------------------------------------------------------------------


def _accept_judge_report(fix_id):
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


@pytest.mark.slow
def test_execute_one_round_carry_forward_when_accepted(hermetic_outputs):
    """Mock judge accept → after-versions reflect the candidate."""
    import atlas.blue_team.fix_applier as applier_mod
    from atlas.ledger.round_engine import execute_one_round

    run_state = _build_run_state(hermetic_outputs)
    real_evaluate = applier_mod.evaluate_fix

    def _mock_evaluate(*args, **kwargs):
        fid = kwargs.get("defensive_fix_id", "")
        if "no_candidate" in fid:
            return real_evaluate(*args, **kwargs)
        return _accept_judge_report(fid)

    with mock.patch.object(applier_mod, "evaluate_fix", side_effect=_mock_evaluate):
        rs = execute_one_round(
            run_state, round_id=1,
            outputs_root=hermetic_outputs,
            data_dir=REPO_ROOT / "data" / "synthetic",
        )
    assert rs.accepted_fix_id is not None
    # Candidate model_version embedded in feature_fix or calibration_fix path
    assert rs.model_version_after != "baseline_v1" or rs.threshold_version_after != "thresholds_v1"
