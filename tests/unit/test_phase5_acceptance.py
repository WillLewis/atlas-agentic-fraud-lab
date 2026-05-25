"""Phase 5 acceptance-rule tests (Bible §16.7).

Each of the six §16.7 conditions must independently flip
``accepted_by_judge``. ``judge_notes`` is byte-stable.
"""
from __future__ import annotations

import pytest

from atlas.judge.acceptance import (
    ACCEPTANCE_CONDITION_KEYS,
    apply_acceptance_rule,
    load_acceptance_policy,
    reset_caches,
    run_acceptance_safety_scan,
)
from atlas.judge.evaluate import _build_acceptance_safety_scan_text


# ---------------------------------------------------------------------------
# Acceptance policy loader
# ---------------------------------------------------------------------------


def test_load_acceptance_policy_unit_normalization():
    """All persisted rate-limit values are normalized to fractions
    (0–1) regardless of unit (raw / pct / bps)."""
    reset_caches()
    p = load_acceptance_policy()
    assert p.max_false_positive_rate_increase_fraction == 0.04
    assert p.max_challenge_rate_increase_fraction == 0.005
    assert p.max_alert_rate_increase_fraction == 8.5 / 100  # pct
    assert p.max_decline_rate_increase_fraction == 2 / 10000  # bps
    assert p.challenge_rate_limit_fraction == 8.0 / 100
    assert p.alert_rate_limit_fraction == 15.0 / 100
    assert p.decline_rate_limit_fraction == 25 / 10000


def test_load_acceptance_policy_caches():
    reset_caches()
    a = load_acceptance_policy()
    b = load_acceptance_policy()
    assert a is b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _baseline():
    return {
        "recall_at_fixed_action_rate": 0.5,
        "false_positive_rate_at_fixed_action_rate": 0.05,
        "model_miss_rate": 0.5,
        "synthetic_loss_allowed": 1000.0,
        "challenge_rate": 0.04,
        "alert_rate": 0.05,
        "decline_rate": 0.001,
    }


def _fixed_passing():
    """Improves recall + miss_rate, doesn't increase friction."""
    return {
        "recall_at_fixed_action_rate": 0.6,
        "false_positive_rate_at_fixed_action_rate": 0.05,
        "model_miss_rate": 0.4,
        "synthetic_loss_allowed": 800.0,
        "challenge_rate": 0.04,
        "alert_rate": 0.05,
        "decline_rate": 0.001,
    }


def _hg_pass():
    return {
        "clean_holdout_pass": True,
        "locked_adaptive_holdout_pass": True,
        "drifted_holdout_pass": True,
    }


def _failing_conditions(notes: str) -> list[str]:
    """Pull out the condition keys reported as False in ``judge_notes``."""
    return [k for k in ACCEPTANCE_CONDITION_KEYS if f"{k}=False" in notes]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_accepted():
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
    )
    assert accepted is True
    assert _failing_conditions(notes) == []
    assert notes.startswith("accepted=True;")


# ---------------------------------------------------------------------------
# Each condition independently blocks acceptance (Bible §16.7 conjunction)
# ---------------------------------------------------------------------------


def test_recall_must_strictly_improve():
    fixed = _fixed_passing()
    fixed["recall_at_fixed_action_rate"] = _baseline()["recall_at_fixed_action_rate"]
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert _failing_conditions(notes) == ["recall_improves"]


def test_recall_regression_blocks():
    fixed = _fixed_passing()
    fixed["recall_at_fixed_action_rate"] = 0.4  # below baseline 0.5
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "recall_improves" in _failing_conditions(notes)


def test_miss_rate_must_strictly_decrease():
    fixed = _fixed_passing()
    fixed["model_miss_rate"] = _baseline()["model_miss_rate"]
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "miss_rate_decreases" in _failing_conditions(notes)


def test_fpr_increase_above_tolerance_blocks():
    base = _baseline()
    fixed = _fixed_passing()
    # Baseline FPR 0.05; tolerance 0.04 -> fixed=0.091 violates
    fixed["false_positive_rate_at_fixed_action_rate"] = 0.091
    accepted, notes = apply_acceptance_rule(
        baseline=base, fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "false_positive_rate_within_tolerance" in _failing_conditions(notes)


def test_fpr_increase_within_tolerance_accepted():
    base = _baseline()
    fixed = _fixed_passing()
    # +0.0005 < 0.04 tolerance
    fixed["false_positive_rate_at_fixed_action_rate"] = 0.0505
    accepted, _ = apply_acceptance_rule(
        baseline=base, fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is True


def test_challenge_rate_above_absolute_cap_blocks():
    fixed = _fixed_passing()
    fixed["challenge_rate"] = 0.10  # > 0.08 cap
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "action_rate_limits_within_tolerance" in _failing_conditions(notes)


def test_alert_rate_friction_violation_blocks():
    fixed = _fixed_passing()
    # Baseline alert 0.05; friction tolerance 0.085 -> +0.09 violates.
    # This stays under the absolute 0.15 cap so the tolerance condition is tested.
    fixed["alert_rate"] = 0.14
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "action_rate_limits_within_tolerance" in _failing_conditions(notes)


def test_decline_rate_friction_violation_blocks():
    fixed = _fixed_passing()
    # Baseline decline 0.001; friction tolerance 0.0002 → +0.0005 violates
    fixed["decline_rate"] = 0.0015
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=fixed, holdout_generalization=_hg_pass(),
    )
    assert accepted is False
    assert "action_rate_limits_within_tolerance" in _failing_conditions(notes)


def test_locked_holdout_failure_blocks():
    hg = _hg_pass()
    hg["locked_adaptive_holdout_pass"] = False
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(), fixed=_fixed_passing(), holdout_generalization=hg,
    )
    assert accepted is False
    assert "locked_holdout_neutral_or_better" in _failing_conditions(notes)


def test_safety_scan_error_blocks_without_echoing_snippet():
    unsafe_text = "candidate text says how to bypass mfa quickly"
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
        safety_scan_text=unsafe_text,
    )

    assert accepted is False
    assert _failing_conditions(notes) == ["safety_scan_passed"]
    assert "unsafe_redteam_phrasing" in notes
    assert "how to bypass" not in notes


def test_safety_scan_warning_only_does_not_block_acceptance():
    accepted, notes = apply_acceptance_rule(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
        safety_scan_text="legacy public copy mentions fraud playbook",
    )

    assert accepted is True
    assert _failing_conditions(notes) == []
    assert "warnings=1" in notes
    assert "legacy_terminology_in_public_copy" in notes


def test_judge_safety_scan_payload_includes_identifiers():
    text = _build_acceptance_safety_scan_text(
        run_id="run_test",
        round_id=1,
        defensive_fix_id="fix how to bypass mfa quickly",
        baseline_model_version="baseline_v1",
        candidate_model_version="baseline_v1",
        baseline_threshold_version="thresholds_v1",
        candidate_threshold_version="thresholds_v1",
        found_adaptive_set_event_ids=[],
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
    )
    decision = run_acceptance_safety_scan(text)

    assert decision.passed is False
    assert decision.error_count == 1
    assert decision.rule_ids == ("unsafe_redteam_phrasing",)


# ---------------------------------------------------------------------------
# Notes byte-stability + condition order
# ---------------------------------------------------------------------------


def test_judge_notes_byte_identical_under_repeat():
    args = dict(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
    )
    a1, n1 = apply_acceptance_rule(**args)
    a2, n2 = apply_acceptance_rule(**args)
    assert (a1, n1) == (a2, n2)


def test_judge_notes_emits_conditions_in_canonical_order():
    _, notes = apply_acceptance_rule(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
    )
    # Each condition key appears exactly once in canonical order.
    indices = [notes.index(k) for k in ACCEPTANCE_CONDITION_KEYS]
    assert indices == sorted(indices)


def test_judge_notes_starts_with_accepted_flag():
    a, n = apply_acceptance_rule(
        baseline=_baseline(),
        fixed=_fixed_passing(),
        holdout_generalization=_hg_pass(),
    )
    assert n.split(";")[0].strip() == f"accepted={a}"


# ---------------------------------------------------------------------------
# All six conditions vs the canonical list
# ---------------------------------------------------------------------------


def test_acceptance_condition_keys_are_six():
    assert len(ACCEPTANCE_CONDITION_KEYS) == 6


def test_acceptance_condition_keys_canonical():
    assert ACCEPTANCE_CONDITION_KEYS == (
        "recall_improves",
        "miss_rate_decreases",
        "false_positive_rate_within_tolerance",
        "action_rate_limits_within_tolerance",
        "locked_holdout_neutral_or_better",
        "safety_scan_passed",
    )
