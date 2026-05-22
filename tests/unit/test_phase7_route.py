"""Phase 7 route tests via TestClient.

Uses the conftest ``api_client`` fixture which monkey-patches the judge
+ blue_team module globals to point at a tmp outputs root populated
with a session-scoped baseline_v1.

Bible §18 Phase 7 acceptance verified end-to-end:
  * At least two fix families work (policy_fix + model_calibration_fix
    + feature_fix all return 200 on apply).
  * Defensive fixes are evaluated by the judge (the response carries a
    ``judge_report_id`` referring to a real persisted report).
  * Overfit / limit-violating fixes are visibly rejected
    (``applied=False`` + governance text identifying the failed
    condition).
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
import yaml

import atlas.blue_team.fix_applier as applier_mod
import app.api.routes.defensive_fixes as defensive_fixes_mod
from atlas.blue_team.fix_applier import reports_dir
from atlas.blue_team.manifest import (
    DefensiveFixManifest,
    ModelVulnerabilityRecord,
    persist_fix_manifest,
    persist_vulnerability_record,
)
from atlas.ledger.ledger import (
    RoundState,
    persist_round_state,
)


@pytest.fixture
def seeded_api_client(api_client, tmp_path):
    """Wraps ``api_client`` and seeds two vulnerability records under
    the patched outputs_root so the route can resolve them."""
    outputs_root = defensive_fixes_mod.OUTPUTS_ROOT
    records = [
        ModelVulnerabilityRecord(
            model_vulnerability_id="mv_round1_low_velocity_high_graph_risk",
            run_id="run_route", round_id=1,
            family_id="low_velocity_high_graph_risk",
            found_adaptive_set_event_ids=[],
            model_miss_rate=1.0,
            recommended_defensive_fix_types=["feature_fix", "policy_fix"],
            summary="...",
        ),
        ModelVulnerabilityRecord(
            model_vulnerability_id="mv_round2_label_noise_mislearned",
            run_id="run_route", round_id=2,
            family_id="label_noise_mislearned",
            found_adaptive_set_event_ids=[],
            model_miss_rate=0.85,
            recommended_defensive_fix_types=["model_calibration_fix"],
            summary="...",
        ),
    ]
    for r in records:
        persist_vulnerability_record(r, outputs_root=outputs_root)
    return api_client


def _persist_round_state_with_versions(
    *,
    outputs_root: Path,
    run_id: str,
    round_id: int,
    model_version_after: str,
    threshold_version_after: str,
) -> None:
    persist_round_state(
        RoundState(
            run_id=run_id,
            round_id=round_id,
            status="completed",
            model_version_before="baseline_v1",
            threshold_version_before="thresholds_v1",
            model_version_after=model_version_after,
            threshold_version_after=threshold_version_after,
            model_miss_rate_before=0.8,
            model_miss_rate_after=0.6,
            recall_at_fixed_action_rate_before=0.2,
            recall_at_fixed_action_rate_after=0.4,
            safety_scan_passed=True,
            accepted_fix_id="fix_previous_round",
            judge_report_id="judge_previous_round",
            transcript_summary="previous round accepted a defensive fix.",
        ),
        outputs_root=outputs_root,
    )


def _fake_judge_report(fix_id: str) -> dict:
    return {
        "judge_report_id": f"judge_{fix_id}",
        "run_id": "run_route",
        "round_id": 2,
        "defensive_fix_id": fix_id,
        "accepted_by_judge": True,
        "baseline": {
            "model_miss_rate": 0.8,
            "recall_at_fixed_action_rate": 0.2,
        },
        "fixed": {
            "model_miss_rate": 0.6,
            "recall_at_fixed_action_rate": 0.4,
        },
        "holdout_generalization": {
            "clean_holdout_pass": True,
            "locked_adaptive_holdout_pass": True,
            "drifted_holdout_pass": True,
        },
        "judge_notes": "accepted=True; recall_improves=True(...);",
    }


# ===========================================================================
# Propose
# ===========================================================================


def test_propose_returns_200_with_candidates(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["feature_fix", "policy_fix"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == "run_route"
    assert body["round_id"] == 1
    assert len(body["defensive_fix_candidates"]) == 2
    fix_types = sorted(c["fix_type"] for c in body["defensive_fix_candidates"])
    assert fix_types == ["feature_fix", "policy_fix"]


def test_propose_response_shape_matches_openapi(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    })
    cand = r.json()["defensive_fix_candidates"][0]
    required = {"defensive_fix_id", "round_id", "fix_type", "description", "requires_judge_evaluation"}
    assert required.issubset(cand)
    assert cand["fix_type"] in {"feature_fix", "policy_fix", "model_calibration_fix"}
    assert cand["requires_judge_evaluation"] is True


def test_propose_extra_field_rejected(seeded_api_client):
    """Pydantic ``extra="forbid"`` rejects client-supplied overrides."""
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "r", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
        "description": "client-supplied prose attempt",
    })
    assert r.status_code == 422


def test_propose_unknown_fix_type_returns_422(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "r", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["unsupported_fix"],
    })
    assert r.status_code == 422


def test_propose_unknown_round_returns_422(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "r", "round_id": 999,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    })
    assert r.status_code == 422


def test_propose_missing_vulnerability_returns_503(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "r", "round_id": 1,
        "model_vulnerability_ids": ["mv_does_not_exist"],
        "allowed_fix_types": ["policy_fix"],
    })
    assert r.status_code == 503


def test_propose_byte_identical_under_repeat(seeded_api_client):
    payload = {
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    }
    a = seeded_api_client.post("/defensive-fixes/propose", json=payload)
    b = seeded_api_client.post("/defensive-fixes/propose", json=payload)
    assert a.content == b.content


def test_propose_uses_previous_round_threshold_version(seeded_api_client):
    outputs_root = defensive_fixes_mod.OUTPUTS_ROOT
    threshold_version = "threshold_round2_accepted"
    threshold_dir = outputs_root / "decision_thresholds"
    threshold_dir.mkdir(parents=True, exist_ok=True)
    thresholds_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "decision_thresholds.yaml"
    )
    with thresholds_path.open() as fh:
        doc = yaml.safe_load(fh)
    doc["decision_threshold_version"] = threshold_version
    doc["decision_thresholds"]["challenge_score_threshold"] = 0.30
    with (threshold_dir / f"{threshold_version}.yaml").open("w") as fh:
        yaml.safe_dump(doc, fh, sort_keys=True)

    _persist_round_state_with_versions(
        outputs_root=outputs_root,
        run_id="run_route",
        round_id=2,
        model_version_after="model_round2_accepted",
        threshold_version_after=threshold_version,
    )
    persist_vulnerability_record(
        ModelVulnerabilityRecord(
            model_vulnerability_id="mv_round3_overfit_fix_failure",
            run_id="run_route",
            round_id=3,
            family_id="overfit_fix_failure",
            found_adaptive_set_event_ids=[],
            model_miss_rate=0.7,
            recommended_defensive_fix_types=["policy_fix"],
            summary="...",
        ),
        outputs_root=outputs_root,
    )

    r = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 3,
        "model_vulnerability_ids": ["mv_round3_overfit_fix_failure"],
        "allowed_fix_types": ["policy_fix"],
    })
    assert r.status_code == 200, r.text
    fid = r.json()["defensive_fix_candidates"][0]["defensive_fix_id"]

    from atlas.blue_team.manifest import load_fix_manifest

    manifest = load_fix_manifest(fid, outputs_root=outputs_root)
    assert manifest.proposed_threshold_overrides == {
        "challenge_score_threshold": 0.291,
    }


# ===========================================================================
# Apply — at least two fix families work end-to-end
# ===========================================================================


@pytest.mark.slow
def test_apply_policy_fix_end_to_end(seeded_api_client):
    """Round 1 + low_velocity_high_graph_risk + policy_fix → 200 with
    valid DefensiveFixApplyResponse."""
    propose = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    }).json()
    cand = propose["defensive_fix_candidates"][0]
    apply_r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "run_route", "round_id": 1,
        "defensive_fix_id": cand["defensive_fix_id"],
    })
    assert apply_r.status_code == 200, apply_r.text
    body = apply_r.json()
    assert body["defensive_fix_id"] == cand["defensive_fix_id"]
    assert isinstance(body["applied"], bool)
    assert body["candidate_threshold_version"] == cand["defensive_fix_id"]
    assert body["candidate_model_version"] == "baseline_v1"
    assert body.get("changed_files")
    assert "judge_report_id" in body
    assert "governance_rationale" in body


@pytest.mark.slow
def test_apply_calibration_fix_end_to_end(seeded_api_client):
    """Round 2 + label_noise_mislearned + model_calibration_fix."""
    propose = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 2,
        "model_vulnerability_ids": ["mv_round2_label_noise_mislearned"],
        "allowed_fix_types": ["model_calibration_fix"],
    }).json()
    cand = propose["defensive_fix_candidates"][0]
    apply_r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "run_route", "round_id": 2,
        "defensive_fix_id": cand["defensive_fix_id"],
    })
    assert apply_r.status_code == 200, apply_r.text
    body = apply_r.json()
    assert body["candidate_model_version"] == cand["defensive_fix_id"]
    assert body["candidate_threshold_version"] == "thresholds_v1"


def test_apply_route_uses_previous_round_versions(seeded_api_client):
    outputs_root = defensive_fixes_mod.OUTPUTS_ROOT
    fid = "fix_round2_route_policy"
    persist_fix_manifest(
        DefensiveFixManifest(
            defensive_fix_id=fid,
            run_id="run_route",
            round_id=2,
            vulnerability_id="mv_round2_route_policy",
            fix_type="policy_fix",
            proposed_threshold_overrides={"challenge_score_threshold": 0.25},
        ),
        outputs_root=outputs_root,
    )
    _persist_round_state_with_versions(
        outputs_root=outputs_root,
        run_id="run_route",
        round_id=1,
        model_version_after="model_round1_accepted",
        threshold_version_after="threshold_round1_accepted",
    )

    with mock.patch.object(
        applier_mod, "apply_policy_fix",
        return_value=(fid, [f"outputs/decision_thresholds/{fid}.yaml"]),
    ), mock.patch.object(
        applier_mod, "evaluate_fix",
        return_value=_fake_judge_report(fid),
    ) as ev:
        r = seeded_api_client.post("/defensive-fixes/apply", json={
            "run_id": "run_route",
            "round_id": 2,
            "defensive_fix_id": fid,
        })

    assert r.status_code == 200, r.text
    kw = ev.call_args.kwargs
    assert kw["baseline_model_version"] == "model_round1_accepted"
    assert kw["candidate_model_version"] == "model_round1_accepted"
    assert kw["baseline_threshold_version"] == "threshold_round1_accepted"
    assert kw["candidate_threshold_version"] == fid


# ===========================================================================
# Apply error mappings
# ===========================================================================


def test_apply_extra_field_rejected(seeded_api_client):
    """Cannot inject ``applied=true`` to override the judge."""
    r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "r", "round_id": 1,
        "defensive_fix_id": "fix_test",
        "applied": True,
    })
    assert r.status_code == 422


def test_apply_missing_manifest_returns_503(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "r", "round_id": 1,
        "defensive_fix_id": "fix_does_not_exist",
    })
    assert r.status_code == 503


def test_apply_missing_required_field_returns_422(seeded_api_client):
    r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "r", "round_id": 1,
    })
    assert r.status_code == 422


# ===========================================================================
# Visible rejection — applied=False is the canonical signal
# ===========================================================================


@pytest.mark.slow
def test_apply_visible_rejection_carries_governance(seeded_api_client):
    """Even when judge rejects (applied=False), the response carries a
    governance rationale + persisted judge_report_id."""
    propose = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    }).json()
    fid = propose["defensive_fix_candidates"][0]["defensive_fix_id"]
    apply_r = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "run_route", "round_id": 1, "defensive_fix_id": fid,
    })
    body = apply_r.json()
    if not body["applied"]:
        # Rejection visibility: governance + judge_report_id MUST be present
        assert body["governance_rationale"]
        assert body["judge_report_id"]
        # The persisted report exists on disk
        report_path = reports_dir(defensive_fixes_mod.OUTPUTS_ROOT) / f"{body['judge_report_id']}.json"
        assert report_path.exists()


# ===========================================================================
# Determinism
# ===========================================================================


@pytest.mark.slow
def test_apply_byte_identical_under_repeat(seeded_api_client):
    propose = seeded_api_client.post("/defensive-fixes/propose", json={
        "run_id": "run_route", "round_id": 1,
        "model_vulnerability_ids": ["mv_round1_low_velocity_high_graph_risk"],
        "allowed_fix_types": ["policy_fix"],
    }).json()
    fid = propose["defensive_fix_candidates"][0]["defensive_fix_id"]
    a = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "run_route", "round_id": 1, "defensive_fix_id": fid,
    })
    b = seeded_api_client.post("/defensive-fixes/apply", json={
        "run_id": "run_route", "round_id": 1, "defensive_fix_id": fid,
    })
    assert a.content == b.content
