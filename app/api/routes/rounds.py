"""Phase 9 round-execution route — thin wrapper over Phase 8's
``atlas.ledger.round_engine.execute_one_round``.

Route (matches OpenAPI lines 242–262):

  POST /rounds/run → RoundRunResponse

Phase 9 invariants honored:

  * Pre-existing ``RunState`` is required (created via ``POST /runs``
    or via ``make run-rounds``). Missing run → 404.
  * The handler loops ``[start_round, start_round + round_count)`` and
    calls ``execute_one_round`` per round, threading the carry-forward
    versions through ``RunState`` updates between rounds. No HTTP
    self-calls. No reimplementation of judge / red-team / blue-team
    business logic.
  * The ``RunState`` is re-persisted after each round so partial
    progress is reflected on disk; final ``status`` flips to
    ``completed`` once ``current_round == max_rounds``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.run import RoundRunRequest, RoundRunResponse  # noqa: E402
from atlas.ledger.ledger import (  # noqa: E402
    MissingRunError,
    RunState,
    load_run_state,
    persist_run_state,
)
from atlas.ledger.round_engine import execute_one_round  # noqa: E402
from atlas.model.loader import DEFAULT_DATA_DIR  # noqa: E402

router = APIRouter()


OUTPUTS_ROOT: Path = REPO_ROOT / "outputs"
DATA_DIR: Path = DEFAULT_DATA_DIR


def _round_state_to_summary(rs) -> dict[str, Any]:
    """Mirror the projection in ``app/api/routes/runs.py`` so the two
    routes return identical ``RoundSummary`` shapes.
    """
    return {
        "run_id": rs.run_id,
        "round_id": rs.round_id,
        "status": rs.status,
        "model_version_before": rs.model_version_before,
        "model_version_after": rs.model_version_after,
        "model_miss_rate_before": rs.model_miss_rate_before,
        "model_miss_rate_after": rs.model_miss_rate_after,
        "recall_at_fixed_action_rate_before": rs.recall_at_fixed_action_rate_before,
        "recall_at_fixed_action_rate_after": rs.recall_at_fixed_action_rate_after,
    }


@router.post(
    "/rounds/run",
    response_model=RoundRunResponse,
    response_model_exclude_none=True,
)
def post_rounds_run(req: RoundRunRequest) -> dict:
    try:
        run_state = load_run_state(req.run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    end_round = req.start_round + req.round_count - 1
    if end_round > run_state.max_rounds:
        raise HTTPException(
            status_code=422,
            detail=(
                f"start_round={req.start_round} + round_count={req.round_count} "
                f"would exceed run.max_rounds={run_state.max_rounds}."
            ),
        )

    completed: list[dict[str, Any]] = []
    for round_id in range(req.start_round, end_round + 1):
        # Mark "running" so a concurrent listing reflects in-flight state.
        run_state = RunState(
            run_id=run_state.run_id,
            seed=run_state.seed,
            demo_mode=run_state.demo_mode,
            status="running",
            created_at_utc=run_state.created_at_utc,
            current_round=run_state.current_round,
            current_model_version=run_state.current_model_version,
            current_threshold_version=run_state.current_threshold_version,
            run_label=run_state.run_label,
            max_rounds=run_state.max_rounds,
        )
        persist_run_state(run_state, outputs_root=OUTPUTS_ROOT)

        round_state = execute_one_round(
            run_state,
            round_id,
            outputs_root=OUTPUTS_ROOT,
            data_dir=DATA_DIR,
        )
        completed.append(_round_state_to_summary(round_state))

        # Carry-forward — accepted candidate advances versions; rejected
        # holds them. Mirrors ``atlas.ledger.run_engine.execute_run``.
        run_state = RunState(
            run_id=run_state.run_id,
            seed=run_state.seed,
            demo_mode=run_state.demo_mode,
            status=(
                "completed" if round_id == run_state.max_rounds else "running"
            ),
            created_at_utc=run_state.created_at_utc,
            current_round=round_id,
            current_model_version=round_state.model_version_after,
            current_threshold_version=round_state.threshold_version_after,
            run_label=run_state.run_label,
            max_rounds=run_state.max_rounds,
        )
        persist_run_state(run_state, outputs_root=OUTPUTS_ROOT)

    return {
        "run_id": run_state.run_id,
        "completed_rounds": completed,
    }
