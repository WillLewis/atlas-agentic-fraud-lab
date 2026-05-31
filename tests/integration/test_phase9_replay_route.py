"""Phase 9 integration tests — GET /replay/{run_id}.

Validates the thin route over Phase 8's
``atlas.ledger.replay.build_replay_payload``:

  * 404 when run state is missing.
  * Top-level shape (``run`` / ``five_step_story`` / ``charts``) matches
    Phase 8 contract.
  * Field-for-field equality with directly-built payload — i.e. the
    route is purely a getter, no synthesis.
  * Round-0 baseline + round-N fixed snapshots present in the kinds
    union (no ``interpolated`` since live replay doesn't emit that).

Hermetic — no real round execution. We persist run/round states + a
stub judge report and assert the route response.
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
from atlas.ledger.replay import build_replay_payload


def _outputs_root_from_client(api_client) -> Path:
    import app.api.routes.runs as runs_mod
    return runs_mod.OUTPUTS_ROOT


def _persist_run(outputs, run_id="run_replay01", current_round=1, max_rounds=3):
    rs = RunState(
        run_id=run_id, seed=42, demo_mode="public", status="completed",
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=current_round,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt",
        max_rounds=max_rounds,
    )
    persist_run_state(rs, outputs_root=outputs)
    return rs


def _persist_round(outputs, run_id, round_id, judge_report_id="judge_x"):
    rs = RoundState(
        run_id=run_id, round_id=round_id, status="completed",
        model_version_before="baseline_v1",
        threshold_version_before="thresholds_v1",
        model_version_after="baseline_v1",
        threshold_version_after="thresholds_v1",
        model_miss_rate_before=1.0, model_miss_rate_after=1.0,
        recall_at_fixed_action_rate_before=0.0,
        recall_at_fixed_action_rate_after=0.0,
        safety_scan_passed=True,
        accepted_fix_id=None,
        judge_report_id=judge_report_id,
        transcript_summary=f"Round {round_id} summary.",
    )
    persist_round_state(rs, outputs_root=outputs)
    return rs


def _write_judge(outputs, judge_id, run_id):
    rdir = reports_dir(outputs)
    rdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "judge_report_id": judge_id, "run_id": run_id, "round_id": 1,
        "defensive_fix_id": "fx", "accepted_by_judge": False,
        "baseline": {
            "model_miss_rate": 1.0, "recall_at_fixed_action_rate": 0.0,
            "false_positive_rate_at_fixed_action_rate": 0.0,
            "synthetic_loss_allowed": 1000.0,
            "challenge_rate": 0.0, "alert_rate": 0.0, "decline_rate": 0.0,
        },
        "fixed": {
            "model_miss_rate": 0.5, "recall_at_fixed_action_rate": 0.5,
            "false_positive_rate_at_fixed_action_rate": 0.05,
            "synthetic_loss_allowed": 600.0,
            "challenge_rate": 0.1, "alert_rate": 0.1, "decline_rate": 0.0,
        },
        "holdout_generalization": {},
        "judge_notes": "...",
    }
    (rdir / f"{judge_id}.json").write_text(json.dumps(payload, sort_keys=True))


# ---------------------------------------------------------------------------
# Missing
# ---------------------------------------------------------------------------


def test_replay_missing_run_404(api_client):
    resp = api_client.get("/replay/run_does_not_exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_replay_top_level_shape(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs)
    _persist_round(outputs, "run_replay01", 1)
    _write_judge(outputs, "judge_x", "run_replay01")

    body = api_client.get("/replay/run_replay01").json()
    assert sorted(body.keys()) == [
        "charts",
        "five_step_story",
        "round_details",
        "run",
    ]
    assert body["run"]["run_id"] == "run_replay01"
    assert len(body["round_details"]) == 1


def test_replay_five_step_story_length(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs, current_round=3)
    for r in (1, 2, 3):
        _persist_round(outputs, "run_replay01", r, judge_report_id=f"judge_{r}")
        _write_judge(outputs, f"judge_{r}", "run_replay01")

    body = api_client.get("/replay/run_replay01").json()
    assert len(body["five_step_story"]) == 5
    assert [s["step_id"] for s in body["five_step_story"]] == [1, 2, 3, 4, 5]


def test_replay_round_metrics_kinds(api_client):
    outputs = _outputs_root_from_client(api_client)
    _persist_run(outputs)
    _persist_round(outputs, "run_replay01", 1)
    _write_judge(outputs, "judge_x", "run_replay01")

    body = api_client.get("/replay/run_replay01").json()
    snaps = body["charts"]["round_metrics"]
    kinds = {s["kind"] for s in snaps}
    # Phase 9 live replay only emits baseline + fixed; never interpolated.
    assert kinds.issubset({"baseline", "fixed"})
    assert "interpolated" not in kinds
    assert snaps[0]["kind"] == "baseline"


# ---------------------------------------------------------------------------
# Equivalence with direct build_replay_payload call
# ---------------------------------------------------------------------------


def test_replay_route_equals_direct_build(api_client):
    """Route is a thin getter — output equals
    ``build_replay_payload(run_state, round_states, ...)`` byte-for-byte
    minus any None drops from response_model_exclude_none.
    """
    outputs = _outputs_root_from_client(api_client)
    rs = _persist_run(outputs)
    _persist_round(outputs, "run_replay01", 1)
    _write_judge(outputs, "judge_x", "run_replay01")

    rounds = [
        # Reload via load_round_state-style — easier: build expected
        # via the same path as the route handler.
    ]
    # Recompute expected payload in-process.
    from atlas.ledger.ledger import load_round_states, load_run_state
    run_state = load_run_state("run_replay01", outputs_root=outputs)
    round_states = load_round_states("run_replay01", outputs_root=outputs)
    expected = build_replay_payload(
        run_state, round_states, outputs_root=outputs,
    )
    actual = api_client.get("/replay/run_replay01").json()

    # JSON-roundtrip the expected so dict ordering / Pydantic model_dump
    # don't muddy the comparison.
    expected_norm = json.loads(json.dumps(expected, sort_keys=True))
    actual_norm = json.loads(json.dumps(actual, sort_keys=True))
    assert actual_norm == expected_norm


# ---------------------------------------------------------------------------
# Empty (no rounds yet)
# ---------------------------------------------------------------------------


def test_replay_run_with_no_rounds(api_client):
    """Freshly-created run (current_round=0) → empty round_metrics +
    empty per-round cards but still a 200 with the full envelope.
    """
    outputs = _outputs_root_from_client(api_client)
    rs = RunState(
        run_id="run_norounds01", seed=42, demo_mode="public", status="created",
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=0,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt",
        max_rounds=3,
    )
    persist_run_state(rs, outputs_root=outputs)

    body = api_client.get("/replay/run_norounds01").json()
    assert sorted(body.keys()) == [
        "charts",
        "five_step_story",
        "round_details",
        "run",
    ]
    assert body["charts"]["round_metrics"] == []
    assert body["round_details"] == []
    assert len(body["five_step_story"]) == 5
