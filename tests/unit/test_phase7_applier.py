"""Phase 7 fix_applier + governance_agent tests.

Visible-rejection invariants (Bible §18 Phase 7):
  * applied=True ⇔ judge_accepted; applied=False ⇔ judge_rejected.
  * Judge report persisted in BOTH outcomes.
  * Governance points at the failed §16.7 condition.
  * Governance never overrides judge metrics.
  * Governance text passes the production safety scanner.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "synthetic"

import atlas.blue_team.fix_applier as applier_mod
from atlas.blue_team.fix_applier import (
    FixApplyOutcome, apply_fix, reports_dir,
)
from atlas.blue_team.governance_agent import format_decision
from atlas.blue_team.manifest import (
    DefensiveFixManifest, MissingManifestError,
    persist_fix_manifest,
)
from atlas.judge.acceptance import ACCEPTANCE_CONDITION_KEYS


@pytest.fixture
def outputs(tmp_path) -> Path:
    return tmp_path / "outputs"


# ===========================================================================
# governance_agent.format_decision unit tests
# ===========================================================================


def _accept_report(fix_id="fix_test"):
    return {
        "judge_report_id": f"judge_{fix_id}",
        "accepted_by_judge": True,
        "judge_notes": (
            "accepted=True; recall_improves=True(...); miss_rate_decreases=True(...); "
            "false_positive_rate_within_tolerance=True(...); "
            "action_rate_limits_within_tolerance=True(...); "
            "locked_holdout_neutral_or_better=True(locked_pass=True); "
            "safety_scan_passed=True(...)"
        ),
        "holdout_generalization": {
            "clean_holdout_pass": True,
            "locked_adaptive_holdout_pass": True,
            "drifted_holdout_pass": True,
        },
    }


def _reject_report(failed_conditions, fix_id="fix_test"):
    """Build a synthesized judge report whose judge_notes mentions
    the supplied conditions as False."""
    note_parts = ["accepted=False"]
    for key in ACCEPTANCE_CONDITION_KEYS:
        flag = "False" if key in failed_conditions else "True"
        note_parts.append(f"{key}={flag}(detail)")
    return {
        "judge_report_id": f"judge_{fix_id}",
        "accepted_by_judge": False,
        "judge_notes": "; ".join(note_parts),
        "holdout_generalization": {
            "clean_holdout_pass": True,
            "locked_adaptive_holdout_pass": "locked_holdout_neutral_or_better" not in failed_conditions,
            "drifted_holdout_pass": True,
        },
    }


def _manifest(fix_id="fix_test", fix_type="policy_fix"):
    return DefensiveFixManifest(
        defensive_fix_id=fix_id, run_id="r", round_id=1,
        vulnerability_id="x", fix_type=fix_type,
        proposed_threshold_overrides=(
            {"challenge_score_threshold": 0.69} if fix_type == "policy_fix" else {}
        ),
        proposed_training_seed=(1001 if fix_type == "model_calibration_fix" else None),
        proposed_l2_strength=(0.5 if fix_type == "model_calibration_fix" else None),
        proposed_feature_transforms=(
            ("boost_graph_risk",) if fix_type == "feature_fix" else ()
        ),
    )


def test_format_decision_accepted_lists_holdout_flags():
    rationale = format_decision(judge_report=_accept_report(), manifest=_manifest())
    assert "judge accepted under §16.7" in rationale
    assert "clean_holdout_pass=True" in rationale
    assert "locked_adaptive_holdout_pass=True" in rationale


def test_format_decision_rejected_lists_failed_conditions():
    report = _reject_report({"recall_improves", "miss_rate_decreases"})
    rationale = format_decision(judge_report=report, manifest=_manifest())
    assert "judge rejected" in rationale
    assert "recall_improves" in rationale
    assert "miss_rate_decreases" in rationale


def test_format_decision_rejected_friction_violation():
    report = _reject_report({"false_positive_rate_within_tolerance"})
    rationale = format_decision(judge_report=report, manifest=_manifest())
    assert "false_positive_rate_within_tolerance" in rationale


def test_format_decision_rejected_locked_holdout_regression():
    report = _reject_report({"locked_holdout_neutral_or_better"})
    rationale = format_decision(judge_report=report, manifest=_manifest())
    assert "locked_holdout_neutral_or_better" in rationale


def test_format_decision_only_emits_canonical_condition_names():
    """Even if judge_notes contains noise like ``locked_pass=False``
    in a parenthesized detail, the rationale should only mention
    canonical ACCEPTANCE_CONDITION_KEYS."""
    report = {
        "judge_report_id": "j",
        "accepted_by_judge": False,
        "judge_notes": (
            "accepted=False; recall_improves=False(detail_with locked_pass=False); "
            "miss_rate_decreases=True(...); "
            "false_positive_rate_within_tolerance=True(...); "
            "action_rate_limits_within_tolerance=True(...); "
            "locked_holdout_neutral_or_better=True(locked_pass=True); "
            "safety_scan_passed=True(...)"
        ),
        "holdout_generalization": {},
    }
    rationale = format_decision(judge_report=report, manifest=_manifest())
    # Should mention recall_improves but NOT locked_pass (noise token)
    assert "recall_improves" in rationale
    assert "locked_pass" not in rationale


def test_format_decision_deterministic():
    args = dict(judge_report=_accept_report(), manifest=_manifest())
    a = format_decision(**args)
    b = format_decision(**args)
    assert a == b


# ===========================================================================
# Governance never overrides judge
# ===========================================================================


def test_governance_says_accepted_when_judge_accepts():
    rationale = format_decision(judge_report=_accept_report(), manifest=_manifest())
    assert "judge accepted" in rationale
    assert "judge rejected" not in rationale


def test_governance_says_rejected_when_judge_rejects():
    report = _reject_report({"recall_improves"})
    rationale = format_decision(judge_report=report, manifest=_manifest())
    assert "judge rejected" in rationale
    assert "judge accepted" not in rationale


def test_governance_does_not_invent_metric_values():
    """Rationale should not contain fabricated numerical metric values
    that aren't somewhere in the report. The literal Bible section
    reference ``§16.7`` is allowed; any other numeric is not."""
    rationale = format_decision(
        judge_report=_accept_report(), manifest=_manifest(),
    )
    import re
    # Strip the literal section reference, then check for stray floats
    stripped = rationale.replace("§16.7", "")
    floats_found = re.findall(r"\d+\.\d+", stripped)
    assert floats_found == []


# ===========================================================================
# Governance text passes safety scan
# ===========================================================================


def test_governance_templates_pass_safety_scan():
    """Run the production safety scanner against a sample of governance
    rationale strings (one per fix_type, both accept + reject paths)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from safety_scan import compile_rules, load_config

    cfg = load_config(REPO_ROOT / "config" / "safety.yaml")
    rules = compile_rules(cfg)

    sample_rationales: list[str] = []
    for fix_type in ("policy_fix", "model_calibration_fix", "feature_fix"):
        m = _manifest(fix_type=fix_type)
        sample_rationales.append(format_decision(
            judge_report=_accept_report(), manifest=m,
        ))
        for failed in ACCEPTANCE_CONDITION_KEYS:
            sample_rationales.append(format_decision(
                judge_report=_reject_report({failed}), manifest=m,
            ))
    for rationale in sample_rationales:
        for rule in rules:
            for pattern in rule.patterns:
                m = pattern.search(rationale)
                assert m is None, (
                    f"governance rationale matches {rule.id}: "
                    f"{m.group(0)!r} in {rationale!r}"
                )


# ===========================================================================
# fix_applier.apply_fix orchestration
# ===========================================================================


def _persist_manifest(outputs, manifest):
    persist_fix_manifest(manifest, outputs_root=outputs)


def test_apply_fix_missing_manifest_raises(outputs):
    with pytest.raises(MissingManifestError):
        apply_fix(defensive_fix_id="fix_does_not_exist", outputs_root=outputs)


def test_apply_fix_visible_rejection_friction_violation(outputs):
    """Synthesize a judge report with friction violation; verify
    apply_fix returns applied=False AND governance text mentions
    false_positive_rate_within_tolerance."""
    manifest = _manifest(fix_id="fix_test_friction", fix_type="policy_fix")
    _persist_manifest(outputs, manifest)

    fake_report = _reject_report(
        {"false_positive_rate_within_tolerance"},
        fix_id="fix_test_friction",
    )
    # Add minimal MetricSnapshot fields the JudgeReport TypedDict
    # contract expects (the applier reads accepted_by_judge + judge_notes
    # + judge_report_id only — extra fields are fine)
    fake_report.update({
        "run_id": "r", "round_id": 1, "defensive_fix_id": manifest.defensive_fix_id,
        "baseline": {}, "fixed": {},
    })

    with mock.patch.object(applier_mod, "evaluate_fix", return_value=fake_report) as ev_spy, \
         mock.patch.object(applier_mod, "apply_policy_fix",
                           return_value=("fix_test_friction", ["outputs/decision_thresholds/x.yaml"])):
        outcome = apply_fix(
            defensive_fix_id="fix_test_friction",
            outputs_root=outputs, data_dir=DATA_DIR,
        )
    assert outcome.applied is False
    assert "false_positive_rate_within_tolerance" in outcome.governance_rationale
    # Visible rejection: artifacts still on disk
    report_path = reports_dir(outputs) / f"{outcome.judge_report_id}.json"
    assert report_path.exists()


def test_apply_fix_visible_rejection_locked_holdout_regression(outputs):
    manifest = _manifest(fix_id="fix_test_locked", fix_type="policy_fix")
    _persist_manifest(outputs, manifest)

    fake_report = _reject_report(
        {"locked_holdout_neutral_or_better"},
        fix_id="fix_test_locked",
    )
    fake_report.update({
        "run_id": "r", "round_id": 1, "defensive_fix_id": manifest.defensive_fix_id,
        "baseline": {}, "fixed": {},
    })

    with mock.patch.object(applier_mod, "evaluate_fix", return_value=fake_report), \
         mock.patch.object(applier_mod, "apply_policy_fix",
                           return_value=("fix_test_locked", ["outputs/decision_thresholds/x.yaml"])):
        outcome = apply_fix(
            defensive_fix_id="fix_test_locked",
            outputs_root=outputs, data_dir=DATA_DIR,
        )
    assert outcome.applied is False
    assert "locked_holdout_neutral_or_better" in outcome.governance_rationale


def test_apply_fix_acceptance_path(outputs):
    manifest = _manifest(fix_id="fix_test_accepted", fix_type="policy_fix")
    _persist_manifest(outputs, manifest)

    fake_report = _accept_report(fix_id="fix_test_accepted")
    fake_report.update({
        "run_id": "r", "round_id": 1, "defensive_fix_id": manifest.defensive_fix_id,
        "baseline": {}, "fixed": {},
    })

    with mock.patch.object(applier_mod, "evaluate_fix", return_value=fake_report), \
         mock.patch.object(applier_mod, "apply_policy_fix",
                           return_value=("fix_test_accepted", ["outputs/decision_thresholds/x.yaml"])):
        outcome = apply_fix(
            defensive_fix_id="fix_test_accepted",
            outputs_root=outputs, data_dir=DATA_DIR,
        )
    assert outcome.applied is True
    assert "judge accepted" in outcome.governance_rationale


def test_apply_fix_persists_judge_report(outputs):
    """Whether accepted or rejected, the judge report goes to disk."""
    manifest = _manifest(fix_id="fix_test_persist", fix_type="policy_fix")
    _persist_manifest(outputs, manifest)
    fake_report = _accept_report(fix_id="fix_test_persist")
    fake_report.update({
        "run_id": "r", "round_id": 1, "defensive_fix_id": manifest.defensive_fix_id,
        "baseline": {}, "fixed": {},
    })
    with mock.patch.object(applier_mod, "evaluate_fix", return_value=fake_report), \
         mock.patch.object(applier_mod, "apply_policy_fix",
                           return_value=("fix_test_persist", [])):
        outcome = apply_fix(
            defensive_fix_id="fix_test_persist",
            outputs_root=outputs, data_dir=DATA_DIR,
        )
    report_path = reports_dir(outputs) / f"{outcome.judge_report_id}.json"
    assert report_path.exists()
    persisted = json.loads(report_path.read_text())
    assert persisted["accepted_by_judge"] == fake_report["accepted_by_judge"]


def test_apply_fix_dispatches_by_family(outputs):
    """Verify each fix_type calls the right family applier."""
    for fix_type, expected_applier in [
        ("policy_fix", "apply_policy_fix"),
        ("model_calibration_fix", "apply_calibration_fix"),
        ("feature_fix", "apply_feature_fix"),
    ]:
        manifest = _manifest(fix_id=f"fix_test_{fix_type}", fix_type=fix_type)
        _persist_manifest(outputs, manifest)
        fake_report = _accept_report(fix_id=manifest.defensive_fix_id)
        fake_report.update({
            "run_id": "r", "round_id": 1, "defensive_fix_id": manifest.defensive_fix_id,
            "baseline": {}, "fixed": {},
        })

        with mock.patch.object(applier_mod, "evaluate_fix", return_value=fake_report), \
             mock.patch.object(
                 applier_mod, expected_applier,
                 return_value=(manifest.defensive_fix_id, ["outputs/x"]),
             ) as spy:
            apply_fix(
                defensive_fix_id=manifest.defensive_fix_id,
                outputs_root=outputs, data_dir=DATA_DIR,
            )
            assert spy.call_count == 1


def test_apply_fix_unknown_fix_type_raises(outputs):
    bad_manifest = DefensiveFixManifest(
        defensive_fix_id="fix_bad", run_id="r", round_id=1,
        vulnerability_id="x", fix_type="totally_unknown",
    )
    _persist_manifest(outputs, bad_manifest)
    with pytest.raises(ValueError, match="unknown manifest.fix_type"):
        apply_fix(defensive_fix_id="fix_bad", outputs_root=outputs, data_dir=DATA_DIR)


# ===========================================================================
# Manifest contains structured apply data
# ===========================================================================


def test_manifest_carries_structured_data_per_family(outputs):
    """Every persisted manifest has non-empty family-specific fields."""
    cases = [
        ("policy_fix", lambda m: bool(m.proposed_threshold_overrides)),
        ("model_calibration_fix", lambda m: m.proposed_training_seed is not None
                                            and m.proposed_l2_strength is not None),
        ("feature_fix", lambda m: bool(m.proposed_feature_transforms)),
    ]
    for fix_type, predicate in cases:
        m = _manifest(fix_type=fix_type)
        assert predicate(m), f"{fix_type} manifest missing structured params"
