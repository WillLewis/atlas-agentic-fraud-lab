"""Phase 5 ``POST /judge/evaluate-fix`` route tests via TestClient.

Uses the session-scoped ``api_client`` fixture (see ``tests/conftest.py``)
which monkey-patches ``BASELINE_MODELS_ROOT`` to the test-trained
baseline so the version-keyed lookup resolves under tmp.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop_payload(**overrides):
    base = {
        "run_id": "run_local_test",
        "round_id": 1,
        "defensive_fix_id": "fix_noop",
        "baseline_model_version": "baseline_v1",
        "candidate_model_version": "baseline_v1",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy-path response shape (Bible §18 Phase 5 acceptance)
# ---------------------------------------------------------------------------


def test_judge_evaluate_fix_response_shape(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    expected = {
        "judge_report_id",
        "run_id",
        "round_id",
        "defensive_fix_id",
        "accepted_by_judge",
        "baseline",
        "fixed",
        "holdout_generalization",
        "judge_notes",
    }
    assert set(body) == expected


def test_metric_snapshot_required_fields_present(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    body = r.json()
    required = {
        "recall_at_fixed_action_rate",
        "false_positive_rate_at_fixed_action_rate",
        "model_miss_rate",
    }
    assert required.issubset(set(body["baseline"]))
    assert required.issubset(set(body["fixed"]))


def test_synthetic_loss_prevented_only_on_fixed(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    body = r.json()
    assert "synthetic_loss_prevented" in body["fixed"]
    assert "synthetic_loss_prevented" not in body["baseline"]


def test_judge_report_id_derived_deterministically(api_client):
    r = api_client.post(
        "/judge/evaluate-fix",
        json=_noop_payload(
            run_id="run_2026_001",
            round_id=2,
            defensive_fix_id="fix_round2_threshold",
        ),
    )
    body = r.json()
    assert body["judge_report_id"] == "judge_run_2026_001_2_fix_round2_threshold"


def test_noop_fix_not_accepted(api_client):
    """Identical baseline and candidate → recall doesn't improve, miss
    rate doesn't decrease → §16.7 rejects."""
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    body = r.json()
    assert body["accepted_by_judge"] is False
    assert "recall_improves=False" in body["judge_notes"]
    assert "miss_rate_decreases=False" in body["judge_notes"]


# ---------------------------------------------------------------------------
# Determinism (Bible §18 Phase 5 acceptance)
# ---------------------------------------------------------------------------


def test_judge_report_byte_identical_under_repeat(api_client):
    r1 = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    r2 = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content


# ---------------------------------------------------------------------------
# Agent text cannot override judge results (Bible §18 Phase 5 acceptance)
# ---------------------------------------------------------------------------


def test_request_judge_notes_override_is_rejected(api_client):
    """The Pydantic schema is ``extra="forbid"`` — a client-supplied
    ``judge_notes`` (or any other free-form override) must 422."""
    payload = _noop_payload(judge_notes="override attempt")
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 422


def test_request_accepted_by_judge_override_is_rejected(api_client):
    payload = _noop_payload(accepted_by_judge=True)
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 422


def test_request_arbitrary_field_override_is_rejected(api_client):
    payload = _noop_payload(arbitrary_field="hi")
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 422


def test_judge_notes_is_judge_generated(api_client):
    """The route's judge_notes must come from the judge — verified by
    the fixed deterministic prefix ``accepted=...``."""
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    notes = r.json()["judge_notes"]
    assert notes.startswith("accepted=")


# ---------------------------------------------------------------------------
# found_adaptive_set semantics
# ---------------------------------------------------------------------------


def test_found_adaptive_set_pass_omitted_when_absent(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    hg = r.json()["holdout_generalization"]
    assert "found_adaptive_set_pass" not in hg
    # The other three are always present
    assert "clean_holdout_pass" in hg
    assert "locked_adaptive_holdout_pass" in hg
    assert "drifted_holdout_pass" in hg


def test_found_adaptive_set_pass_present_when_supplied(api_client):
    # Pull a few real readable IDs
    sample = api_client.get("/synthetic/sample?limit=5").json()
    ids = [f["event_id"] for f in sample["features"]][:3]
    payload = _noop_payload(found_adaptive_set_event_ids=ids)
    r = api_client.post("/judge/evaluate-fix", json=payload)
    body = r.json()
    assert r.status_code == 200, r.text
    assert "found_adaptive_set_pass" in body["holdout_generalization"]


def test_bogus_found_adaptive_set_ids_returns_422(api_client):
    payload = _noop_payload(found_adaptive_set_event_ids=["tx_does_not_exist"])
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 422


def test_empty_found_adaptive_set_ids_omits_check(api_client):
    """Empty list = same as not supplying it: no found_adaptive_set
    evaluation, no key in the response."""
    payload = _noop_payload(found_adaptive_set_event_ids=[])
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 200
    assert "found_adaptive_set_pass" not in r.json()["holdout_generalization"]


# ---------------------------------------------------------------------------
# Error mappings
# ---------------------------------------------------------------------------


def test_unknown_model_version_returns_503(api_client):
    payload = _noop_payload(baseline_model_version="baseline_v999")
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 503
    assert "make train" in r.json()["detail"]


def test_unknown_threshold_version_returns_422(api_client):
    payload = _noop_payload(candidate_threshold_version="thresholds_v999")
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 422
    assert "thresholds_v1" in r.json()["detail"]


def test_persisted_threshold_version_accepted(api_client):
    payload = _noop_payload(
        baseline_threshold_version="thresholds_v1",
        candidate_threshold_version="thresholds_v1",
    )
    r = api_client.post("/judge/evaluate-fix", json=payload)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Pass-flag types are bool
# ---------------------------------------------------------------------------


def test_holdout_generalization_flags_are_bool(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    hg = r.json()["holdout_generalization"]
    for k, v in hg.items():
        assert isinstance(v, bool), f"{k} = {v!r}"


# ---------------------------------------------------------------------------
# All metric values rounded to 4 decimals at the report-emit boundary
# ---------------------------------------------------------------------------


def test_metric_values_rounded_to_four_decimals(api_client):
    r = api_client.post("/judge/evaluate-fix", json=_noop_payload())
    body = r.json()
    for side in ("baseline", "fixed"):
        for k, v in body[side].items():
            assert isinstance(v, (int, float))
            # round-trip with 4dp must not change the value
            assert round(v, 4) == v, f"{side}.{k} not 4dp: {v}"
