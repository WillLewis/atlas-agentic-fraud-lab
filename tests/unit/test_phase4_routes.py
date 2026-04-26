"""Phase 4 FastAPI route tests via TestClient."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_config_demo(api_client):
    r = api_client.get("/config/demo")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_mode"] == "public"
    assert body["institution_label"] == "RetailBank-X"
    assert body["model_label"] == "Mock Account-Takeover Risk Scorer"


def test_decision_thresholds_match_config(api_client):
    """API names use the OpenAPI public contract; values come from config."""
    r = api_client.get("/decision-thresholds")
    assert r.status_code == 200
    body = r.json()
    with open(REPO_ROOT / "config" / "decision_thresholds.yaml") as fh:
        cfg = yaml.safe_load(fh)
    assert body["threshold_version"] == cfg["decision_threshold_version"]
    assert body["decline_score_threshold"] == cfg["decision_thresholds"]["decline_score_threshold"]
    assert body["alert_score_threshold"] == cfg["decision_thresholds"]["alert_score_threshold"]
    assert body["challenge_score_threshold"] == cfg["decision_thresholds"]["challenge_score_threshold"]
    assert body["decline_rate_limit_bps"] == cfg["action_rate_limits"]["decline_rate_limit_bps"]
    assert body["challenge_rate_limit_pct"] == cfg["action_rate_limits"]["challenge_rate_limit_pct"]
    assert body["alert_rate_limit_pct"] == cfg["action_rate_limits"]["alert_rate_limit_pct"]
    # Persisted-config field name `review_rate_limit_pct` is renamed at the boundary.
    assert body["manual_review_rate_limit_pct"] == cfg["action_rate_limits"]["review_rate_limit_pct"]


def test_decision_thresholds_no_persisted_field_names(api_client):
    """The API response must NOT use persisted-config field names."""
    body = api_client.get("/decision-thresholds").json()
    assert "decision_threshold_version" not in body
    assert "review_rate_limit_pct" not in body


def test_schema(api_client):
    r = api_client.get("/schema")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "entity_types",
        "event_types",
        "feature_names",
        "allowed_model_vulnerability_families",
    }
    # 17 - 2 IDs = 15 emitted feature columns
    assert len(body["feature_names"]) == 15
    assert "event_id" not in body["feature_names"]
    assert "customer_id" not in body["feature_names"]


def test_synthetic_sample_default_limit(api_client):
    r = api_client.get("/synthetic/sample")
    assert r.status_code == 200
    body = r.json()
    assert "customers" in body and "events" in body and "features" in body
    assert len(body["events"]) == 10  # default limit


def test_synthetic_sample_event_id_normalized(api_client):
    r = api_client.get("/synthetic/sample?limit=3")
    body = r.json()
    for e in body["events"]:
        assert "event_id" in e
        # Persisted name MUST NOT leak through.
        assert "transfer_event_id" not in e
        assert e["event_id"].startswith("tx_")


def test_synthetic_sample_features_match_events(api_client):
    r = api_client.get("/synthetic/sample?limit=5")
    body = r.json()
    event_ids = {e["event_id"] for e in body["events"]}
    feature_ids = {f["event_id"] for f in body["features"]}
    # Features must be a subset of events (we sample N events; features
    # for those events).
    assert feature_ids <= event_ids


def test_synthetic_sample_does_not_read_locked(api_client):
    """The route only reads global readable artifacts. Verified by the
    on-disk fact that no event_id from holdouts/locked/feature_vectors.json
    appears in the response."""
    r = api_client.get("/synthetic/sample?limit=100")
    body = r.json()
    feature_ids = {f["event_id"] for f in body["features"]}

    locked_features_path = (
        REPO_ROOT / "data" / "synthetic" / "holdouts" / "locked" / "feature_vectors.json"
    )
    if not locked_features_path.exists():
        pytest.skip("locked feature_vectors.json not present")
    with locked_features_path.open() as fh:
        locked_event_ids = {f["event_id"] for f in json.load(fh)}
    assert not (feature_ids & locked_event_ids)


def test_synthetic_sample_limit_validation(api_client):
    r = api_client.get("/synthetic/sample?limit=0")
    assert r.status_code == 422
    r = api_client.get("/synthetic/sample?limit=101")
    assert r.status_code == 422


def _payload_from_sample(api_client) -> dict:
    """Helper: pull a normal-activity event + its feature vector for scoring."""
    sample = api_client.get("/synthetic/sample?limit=10").json()
    events_by_id = {e["event_id"]: e for e in sample["events"]}
    features_by_id = {f["event_id"]: f for f in sample["features"]}
    eid = next(iter(features_by_id))
    return {"event": events_by_id[eid], "features": features_by_id[eid]}


def test_score_response_shape(api_client):
    payload = _payload_from_sample(api_client)
    r = api_client.post("/score", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    expected_keys = {
        "event_id",
        "score",
        "decision_action",
        "decision_band",
        "model_version",
        "threshold_version",
        "reason_codes",
    }
    assert set(body) == expected_keys
    assert 0.0 <= body["score"] <= 1.0
    assert body["decision_action"] in {"accept", "challenge", "alert", "decline"}
    assert body["model_version"] == "baseline_v1"
    assert body["threshold_version"] == "thresholds_v1"


def test_score_event_id_consistency(api_client):
    payload = _payload_from_sample(api_client)
    r = api_client.post("/score", json=payload)
    body = r.json()
    assert body["event_id"] == payload["event"]["event_id"]


def test_score_rejects_event_features_id_mismatch(api_client):
    payload = _payload_from_sample(api_client)
    payload["features"]["event_id"] = "tx_999999"  # mismatch
    r = api_client.post("/score", json=payload)
    assert r.status_code == 422


def test_score_invariant_to_truth_label(api_client):
    """The synthetic_truth_label on the EventRecord must NOT affect the
    score — the scorer never reads it."""
    p1 = _payload_from_sample(api_client)
    p1["event"]["synthetic_truth_label"] = "normal_activity"
    p2 = _payload_from_sample(api_client)
    p2["event"]["synthetic_truth_label"] = "high_risk_synthetic_activity"
    # Use the same event/features otherwise.
    p2["event"] = dict(p1["event"], synthetic_truth_label="high_risk_synthetic_activity")
    p2["features"] = p1["features"]

    r1 = api_client.post("/score", json=p1).json()
    r2 = api_client.post("/score", json=p2).json()
    assert r1["score"] == r2["score"]
    assert r1["decision_action"] == r2["decision_action"]
    assert r1["reason_codes"] == r2["reason_codes"]


def test_score_reason_codes_in_allowlist(api_client):
    """Every emitted reason code must be in the config allow-list."""
    payload = _payload_from_sample(api_client)
    r = api_client.post("/score", json=payload).json()
    allowlist = {
        "recent_activity_change", "entity_graph_risk", "device_novelty",
        "security_recovery_recent", "cash_movement_velocity_high",
        "new_recipient_low_tenure", "region_change_recent",
        "score_boundary_cluster", "shared_device_high_degree",
        "shared_recipient_high_degree",
    }
    assert set(r["reason_codes"]).issubset(allowlist)


def test_batch_score(api_client):
    sample = api_client.get("/synthetic/sample?limit=5").json()
    events_by_id = {e["event_id"]: e for e in sample["events"]}
    features_by_id = {f["event_id"]: f for f in sample["features"]}
    records = [
        {"event": events_by_id[eid], "features": features_by_id[eid]}
        for eid in features_by_id
    ]
    r = api_client.post("/batch-score", json={"records": records})
    assert r.status_code == 200
    body = r.json()
    assert len(body["scores"]) == len(records)
    assert body["model_version"] == "baseline_v1"
    assert body["threshold_version"] == "thresholds_v1"


def test_batch_score_rejects_oversize(api_client):
    """Phase 4 batch limit is 5000."""
    sample = api_client.get("/synthetic/sample?limit=1").json()
    one_event = sample["events"][0]
    one_feat = sample["features"][0]
    if one_event["event_id"] != one_feat["event_id"]:
        pytest.skip("sample event/feature alignment failed")
    record = {"event": one_event, "features": one_feat}
    payload = {"records": [record] * 5001}
    r = api_client.post("/batch-score", json=payload)
    assert r.status_code == 422  # FastAPI raises 422 when max_length is violated


def test_batch_score_rejects_empty(api_client):
    r = api_client.post("/batch-score", json={"records": []})
    assert r.status_code == 422


def test_score_determinism(api_client):
    payload = _payload_from_sample(api_client)
    r1 = api_client.post("/score", json=payload).json()
    r2 = api_client.post("/score", json=payload).json()
    assert r1 == r2
