"""Phase 9 integration tests — per-run artifact routes.

  * ``GET /runs/{run_id}/model-vulnerabilities`` — filtered list,
    404 if run missing.
  * ``GET /runs/{run_id}/judge-reports/{judge_report_id}`` — load by
    id, ownership-verified, 404 on missing OR ownership mismatch.

Hermetic — no real round execution. Tests stamp persisted records into
the ``api_client``-patched outputs tree and assert the route response.
"""
from __future__ import annotations

import json
from pathlib import Path

from atlas.ledger.ledger import (
    RunState,
    persist_run_state,
    reports_dir,
)


def _outputs_root_from_client(api_client) -> Path:
    import app.api.routes.runs as runs_mod
    return runs_mod.OUTPUTS_ROOT


def _persist_run(outputs, run_id, status="completed"):
    rs = RunState(
        run_id=run_id,
        seed=42,
        demo_mode="public",
        status=status,
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=1,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt",
        max_rounds=3,
    )
    persist_run_state(rs, outputs_root=outputs)


def _write_mv(outputs, mv_id, run_id, round_id):
    mvdir = outputs / "model_vulnerabilities"
    mvdir.mkdir(parents=True, exist_ok=True)
    record = {
        "model_vulnerability_id": mv_id, "run_id": run_id, "round_id": round_id,
        "family_id": "x", "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0, "recommended_defensive_fix_types": [],
        "summary": "x",
    }
    (mvdir / f"{mv_id}.json").write_text(json.dumps(record, sort_keys=True))


def _write_judge(outputs, judge_id, run_id, round_id=1):
    rdir = reports_dir(outputs)
    rdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "judge_report_id": judge_id, "run_id": run_id, "round_id": round_id,
        "defensive_fix_id": "fx", "accepted_by_judge": False,
        "baseline": {}, "fixed": {},
        "holdout_generalization": {},
        "judge_notes": "...",
    }
    (rdir / f"{judge_id}.json").write_text(json.dumps(payload, sort_keys=True))


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/model-vulnerabilities
# ---------------------------------------------------------------------------


def test_model_vulnerabilities_missing_run_404(api_client):
    resp = api_client.get("/runs/run_does_not_exist/model-vulnerabilities")
    assert resp.status_code == 404


def test_model_vulnerabilities_empty_when_no_records(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    body = api_client.get("/runs/run_aaaaaa01/model-vulnerabilities").json()
    assert body == {"model_vulnerabilities": []}


def test_model_vulnerabilities_filters_by_run_id(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_run(outputs, "run_bbbbbb02")
    _write_mv(outputs, "mv_round1_a", "run_aaaaaa01", 1)
    _write_mv(outputs, "mv_round2_b", "run_aaaaaa01", 2)
    _write_mv(outputs, "mv_round1_c", "run_bbbbbb02", 1)

    body = api_client.get("/runs/run_aaaaaa01/model-vulnerabilities").json()
    ids = {r["model_vulnerability_id"] for r in body["model_vulnerabilities"]}
    assert ids == {"mv_round1_a", "mv_round2_b"}
    assert all(
        r["run_id"] == "run_aaaaaa01" for r in body["model_vulnerabilities"]
    )


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/judge-reports/{judge_report_id}
# ---------------------------------------------------------------------------


def test_judge_report_missing_run_404(api_client):
    resp = api_client.get("/runs/run_nope/judge-reports/judge_x")
    assert resp.status_code == 404


def test_judge_report_missing_report_404(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    resp = api_client.get("/runs/run_aaaaaa01/judge-reports/judge_missing")
    assert resp.status_code == 404


def test_judge_report_returns_payload(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _write_judge(outputs, "judge_x", "run_aaaaaa01", round_id=1)
    body = api_client.get("/runs/run_aaaaaa01/judge-reports/judge_x").json()
    assert body["judge_report_id"] == "judge_x"
    assert body["run_id"] == "run_aaaaaa01"


def test_judge_report_ownership_mismatch_404(api_client):
    """A judge report belonging to a DIFFERENT run must 404."""
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_run(outputs, "run_bbbbbb02")
    _write_judge(outputs, "judge_b", "run_bbbbbb02")
    resp = api_client.get("/runs/run_aaaaaa01/judge-reports/judge_b")
    assert resp.status_code == 404
    assert "does not belong" in resp.json()["detail"]
