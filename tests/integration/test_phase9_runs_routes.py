"""Phase 9 integration tests — POST /runs + GET /runs* family.

Validates the thin route layer over the Phase 8 ``RunState`` artifacts:

  * ``POST /runs`` builds an initial RunState (no rounds executed).
  * ``run_id`` is deterministic — same payload → same id.
  * ``GET /runs`` lists persisted runs.
  * ``GET /runs/{run_id}`` 404s when missing; returns ``RunDetail`` else.
  * ``GET /runs/{run_id}/rounds`` returns RoundSummary[].
  * ``GET /runs/{run_id}/rounds/{round_id}`` joins persisted artifacts.

All tests use the shared ``api_client`` fixture from ``tests/conftest.py``
which patches the route module ``OUTPUTS_ROOT`` to a hermetic tmp dir.
"""
from __future__ import annotations

import json
from pathlib import Path

from atlas.ledger.ledger import (
    RoundState,
    RunState,
    persist_round_state,
    persist_run_state,
    reports_dir,
)


def _persist_run(outputs_root, run_id, status="completed", current_round=2):
    rs = RunState(
        run_id=run_id,
        seed=42,
        demo_mode="public",
        status=status,
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=current_round,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt_test",
        max_rounds=3,
    )
    persist_run_state(rs, outputs_root=outputs_root)
    return rs


def _persist_round(
    outputs_root,
    run_id,
    round_id,
    accepted_fix_id=None,
    judge_report_id=None,
    transcript_summary="Round summary.",
):
    rs = RoundState(
        run_id=run_id,
        round_id=round_id,
        status="completed",
        model_version_before="baseline_v1",
        threshold_version_before="thresholds_v1",
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
        model_miss_rate_before=1.0,
        model_miss_rate_after=1.0,
        recall_at_fixed_action_rate_before=0.0,
        recall_at_fixed_action_rate_after=0.0,
        safety_scan_passed=True,
        accepted_fix_id=accepted_fix_id,
        judge_report_id=judge_report_id,
        transcript_summary=transcript_summary,
    )
    persist_round_state(rs, outputs_root=outputs_root)
    return rs


def _outputs_root_from_client(api_client) -> Path:
    """Pull the patched OUTPUTS_ROOT back out of the runs route module
    so test-side helpers can write artifacts to the same hermetic dir.
    """
    import app.api.routes.runs as runs_mod
    return runs_mod.OUTPUTS_ROOT


# ---------------------------------------------------------------------------
# POST /runs
# ---------------------------------------------------------------------------


def test_post_runs_creates_run_summary(api_client):
    resp = api_client.post(
        "/runs",
        json={"seed": 42, "run_label": "smoke", "demo_mode": "public", "max_rounds": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["seed"] == 42
    assert body["demo_mode"] == "public"
    assert body["status"] == "created"
    assert body["current_round"] == 0
    assert body["run_id"].startswith("run_")
    assert len(body["run_id"]) == 4 + 8


def test_post_runs_deterministic_run_id(api_client):
    payload = {"seed": 42, "run_label": "alpha", "demo_mode": "public"}
    a = api_client.post("/runs", json=payload).json()
    b = api_client.post("/runs", json=payload).json()
    assert a["run_id"] == b["run_id"]


def test_post_runs_different_seed_different_run_id(api_client):
    base = {"run_label": "alpha", "demo_mode": "public"}
    a = api_client.post("/runs", json={**base, "seed": 42}).json()
    b = api_client.post("/runs", json={**base, "seed": 43}).json()
    assert a["run_id"] != b["run_id"]


def test_post_runs_persists_run_state_file(api_client):
    """A persisted ``runs/<run_id>.json`` exists after POST /runs."""
    body = api_client.post(
        "/runs",
        json={"seed": 42, "run_label": "persist_test", "demo_mode": "public"},
    ).json()
    outputs_root = _outputs_root_from_client(api_client)
    path = outputs_root / "runs" / f"{body['run_id']}.json"
    assert path.exists()


def test_post_runs_rejects_extra_fields(api_client):
    """``RunCreateRequest.extra='forbid'`` rejects unknown keys."""
    resp = api_client.post(
        "/runs",
        json={"seed": 42, "demo_mode": "public", "secret_override": "x"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /runs
# ---------------------------------------------------------------------------


def test_get_runs_empty_list(api_client):
    resp = api_client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_get_runs_lists_persisted(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01", status="completed")
    _persist_run(outputs, "run_bbbbbb02", status="created")
    body = api_client.get("/runs").json()
    ids = {r["run_id"] for r in body["runs"]}
    assert ids == {"run_aaaaaa01", "run_bbbbbb02"}


def test_get_runs_skips_round_companion_files(api_client):
    """``run_xxx.round_NN.json`` must not be parsed as a RunState."""
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(outputs, "run_aaaaaa01", 1)
    _persist_round(outputs, "run_aaaaaa01", 2)
    body = api_client.get("/runs").json()
    assert [r["run_id"] for r in body["runs"]] == ["run_aaaaaa01"]


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------


def test_get_run_missing_404(api_client):
    resp = api_client.get("/runs/run_does_not_exist")
    assert resp.status_code == 404
    assert "make run-rounds" in resp.json()["detail"]


def test_get_run_returns_detail_with_rounds(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(outputs, "run_aaaaaa01", 1)
    _persist_round(outputs, "run_aaaaaa01", 2)
    body = api_client.get("/runs/run_aaaaaa01").json()
    assert body["run_id"] == "run_aaaaaa01"
    assert body["status"] == "completed"
    assert len(body["rounds"]) == 2
    assert [r["round_id"] for r in body["rounds"]] == [1, 2]


def test_get_run_latest_metrics_from_judge_report(api_client):
    """``RunDetail.latest_metrics`` derives from the latest round's
    judge report ``baseline``/``fixed`` side.
    """
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(
        outputs, "run_aaaaaa01", 1,
        accepted_fix_id="fix_round1_x",
        judge_report_id="judge_x",
    )
    rdir = reports_dir(outputs)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "judge_x.json").write_text(json.dumps({
        "judge_report_id": "judge_x",
        "accepted_by_judge": True,
        "baseline": {
            "model_miss_rate": 1.0, "recall_at_fixed_action_rate": 0.0,
            "false_positive_rate_at_fixed_action_rate": 0.0,
            "synthetic_loss_allowed": 1000.0,
            "challenge_rate": 0.0, "alert_rate": 0.0, "decline_rate": 0.0,
        },
        "fixed": {
            "model_miss_rate": 0.5, "recall_at_fixed_action_rate": 0.5,
            "false_positive_rate_at_fixed_action_rate": 0.05,
            "synthetic_loss_allowed": 500.0,
            "challenge_rate": 0.1, "alert_rate": 0.1, "decline_rate": 0.0,
        },
    }))
    body = api_client.get("/runs/run_aaaaaa01").json()
    lm = body["latest_metrics"]
    assert lm is not None
    # Accepted → "fixed" side
    assert lm["model_miss_rate"] == 0.5
    assert lm["recall_at_fixed_action_rate"] == 0.5
    assert lm["kind"] == "fixed"


def test_get_run_no_latest_metrics_when_no_rounds(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01", status="created", current_round=0)
    body = api_client.get("/runs/run_aaaaaa01").json()
    assert body["rounds"] == []
    # Pydantic response_model_exclude_none drops the field entirely.
    assert "latest_metrics" not in body or body["latest_metrics"] is None


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/rounds
# ---------------------------------------------------------------------------


def test_get_run_rounds_missing_run_404(api_client):
    resp = api_client.get("/runs/run_nope/rounds")
    assert resp.status_code == 404


def test_get_run_rounds_lists_summaries(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(outputs, "run_aaaaaa01", 2)
    _persist_round(outputs, "run_aaaaaa01", 1)  # out of order on disk
    body = api_client.get("/runs/run_aaaaaa01/rounds").json()
    assert [r["round_id"] for r in body["rounds"]] == [1, 2]


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/rounds/{round_id}
# ---------------------------------------------------------------------------


def test_get_run_round_404_when_missing(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    resp = api_client.get("/runs/run_aaaaaa01/rounds/9")
    assert resp.status_code == 404


def test_get_run_round_returns_joined_artifacts(api_client):
    """RoundDetail joins per-round vulnerability + fix + judge records."""
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(
        outputs, "run_aaaaaa01", 1,
        accepted_fix_id="fix_round1_x",
        judge_report_id="judge_x",
        transcript_summary="Round 1 transcript.",
    )

    # Persist a model_vulnerability record for run_aaaaaa01 round 1 + an
    # unrelated record under a different run_id and round_id.
    mvdir = outputs / "model_vulnerabilities"
    mvdir.mkdir(parents=True, exist_ok=True)
    (mvdir / "mv_round1_a.json").write_text(json.dumps({
        "model_vulnerability_id": "mv_round1_a", "run_id": "run_aaaaaa01",
        "round_id": 1, "family_id": "x", "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0, "recommended_defensive_fix_types": [],
        "summary": "x",
    }))
    (mvdir / "mv_round2_b.json").write_text(json.dumps({
        "model_vulnerability_id": "mv_round2_b", "run_id": "run_aaaaaa01",
        "round_id": 2, "family_id": "y", "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0, "recommended_defensive_fix_types": [],
        "summary": "y",
    }))
    (mvdir / "mv_round1_other.json").write_text(json.dumps({
        "model_vulnerability_id": "mv_round1_other", "run_id": "run_other",
        "round_id": 1, "family_id": "z", "found_adaptive_set_event_ids": [],
        "model_miss_rate": 1.0, "recommended_defensive_fix_types": [],
        "summary": "z",
    }))

    fdir = outputs / "defensive_fixes"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "fix_round1_x.json").write_text(json.dumps({
        "defensive_fix_id": "fix_round1_x", "run_id": "run_aaaaaa01",
        "round_id": 1, "vulnerability_id": "mv_round1_a", "fix_type": "policy_fix",
    }))

    rdir = reports_dir(outputs)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "judge_x.json").write_text(json.dumps({
        "judge_report_id": "judge_x", "accepted_by_judge": True,
        "baseline": {}, "fixed": {},
    }))

    body = api_client.get("/runs/run_aaaaaa01/rounds/1").json()
    assert body["round_id"] == 1
    # Only the round_id=1 + run_id=run_aaaaaa01 vulnerability is joined.
    assert [m["model_vulnerability_id"] for m in body["model_vulnerabilities"]] == [
        "mv_round1_a"
    ]
    assert [f["defensive_fix_id"] for f in body["defensive_fixes"]] == [
        "fix_round1_x"
    ]
    assert len(body["judge_reports"]) == 1
    assert body["judge_reports"][0]["judge_report_id"] == "judge_x"
    assert body["transcript_summary"] == "Round 1 transcript."
    assert body["safety_scan_passed"] is True


def test_get_run_round_handles_missing_judge_report(api_client):
    """A round_state pointing at a vanished judge report should still
    return a 200 — just with judge_reports=[].
    """
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, "run_aaaaaa01")
    _persist_round(
        outputs, "run_aaaaaa01", 1,
        judge_report_id="judge_missing",
    )
    body = api_client.get("/runs/run_aaaaaa01/rounds/1").json()
    assert body["judge_reports"] == []
