"""Phase 9 integration tests — POST /rounds/run.

Validates the thin route layer over Phase 8's
``atlas.ledger.round_engine.execute_one_round``:

  * Missing run → 404.
  * round_count = 1 executes one round and writes a ledger row.
  * Carry-forward of versions across multiple rounds.
  * Validation rejects ranges that exceed ``run.max_rounds``.

These tests run real round-engine code (slow) so they are marked
``slow`` to mirror the Phase 8 lifecycle test pattern.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from atlas.ledger.ledger import (
    RunState,
    load_ledger_records,
    load_round_state,
    persist_run_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _outputs_root_from_client(api_client) -> Path:
    import app.api.routes.runs as runs_mod
    return runs_mod.OUTPUTS_ROOT


def _create_run(api_client, run_label="rt_round_route") -> str:
    body = api_client.post(
        "/runs",
        json={
            "seed": 42,
            "run_label": run_label,
            "demo_mode": "public",
            "max_rounds": 3,
        },
    ).json()
    return body["run_id"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_post_rounds_run_missing_run_404(api_client):
    resp = api_client.post(
        "/rounds/run",
        json={"run_id": "run_does_not_exist", "start_round": 1, "round_count": 1},
    )
    assert resp.status_code == 404


def test_post_rounds_run_overflow_explicit(api_client):
    """end_round (start_round + round_count - 1) > max_rounds → 422."""
    outputs = _outputs_root_from_client(api_client)
    rs = RunState(
        run_id="run_overflow1",
        seed=42,
        demo_mode="public",
        status="created",
        created_at_utc="2026-06-01T12:00:00Z",
        current_round=0,
        current_model_version="baseline_v1",
        current_threshold_version="thresholds_v1",
        run_label="rt",
        max_rounds=2,  # tight bound
    )
    persist_run_state(rs, outputs_root=outputs)

    resp = api_client.post(
        "/rounds/run",
        json={"run_id": "run_overflow1", "start_round": 2, "round_count": 2},
    )
    assert resp.status_code == 422
    assert "max_rounds" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Single-round execution (slow — runs real round engine)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_post_rounds_run_one_round_writes_ledger_row(api_client):
    """One round executed via POST /rounds/run produces one ledger row
    + one persisted RoundState matching what ``execute_one_round`` does
    directly.
    """
    outputs = _outputs_root_from_client(api_client)
    run_id = _create_run(api_client, run_label="single_round")

    resp = api_client.post(
        "/rounds/run",
        json={"run_id": run_id, "start_round": 1, "round_count": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert len(body["completed_rounds"]) == 1
    assert body["completed_rounds"][0]["round_id"] == 1

    # Persisted RoundState exists.
    rs = load_round_state(run_id, 1, outputs_root=outputs)
    assert rs.status == "completed"

    # Ledger has one row.
    rows = load_ledger_records(run_id, outputs_root=outputs)
    assert len(rows) == 1
    assert rows[0]["round_id"] == 1


@pytest.mark.slow
def test_post_rounds_run_updates_run_state_after_round(api_client):
    """``GET /runs/{run_id}`` after one POST /rounds/run reflects
    current_round = 1 and status running/completed depending on
    max_rounds.
    """
    run_id = _create_run(api_client, run_label="state_after_one")
    api_client.post(
        "/rounds/run",
        json={"run_id": run_id, "start_round": 1, "round_count": 1},
    )
    body = api_client.get(f"/runs/{run_id}").json()
    assert body["current_round"] == 1
    # max_rounds=3, only round 1 done → status="running"
    assert body["status"] == "running"


@pytest.mark.slow
def test_post_rounds_run_completes_when_final_round_runs(api_client):
    """Running the final round flips status to 'completed'."""
    run_id = _create_run(api_client, run_label="finalize")
    # Run all 3 rounds in one shot.
    resp = api_client.post(
        "/rounds/run",
        json={"run_id": run_id, "start_round": 1, "round_count": 3},
    )
    assert resp.status_code == 200
    assert len(resp.json()["completed_rounds"]) == 3

    body = api_client.get(f"/runs/{run_id}").json()
    assert body["current_round"] == 3
    assert body["status"] == "completed"


@pytest.mark.slow
def test_post_rounds_run_carry_forward_versions(api_client):
    """After round 1, round 2's RoundState.before-versions equal round
    1's after-versions (carry-forward). Real-data run rejects fixes by
    default → versions hold across rounds.
    """
    outputs = _outputs_root_from_client(api_client)
    run_id = _create_run(api_client, run_label="carryforward")

    api_client.post(
        "/rounds/run",
        json={"run_id": run_id, "start_round": 1, "round_count": 2},
    )
    rs1 = load_round_state(run_id, 1, outputs_root=outputs)
    rs2 = load_round_state(run_id, 2, outputs_root=outputs)
    assert rs2.model_version_before == rs1.model_version_after
    assert rs2.threshold_version_before == rs1.threshold_version_after
