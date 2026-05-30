"""Phase 9 replay-payload route — thin wrapper over Phase 8's
``atlas.ledger.replay.build_replay_payload``.

Route (matches OpenAPI lines 411–432):

  GET /replay/{run_id} → ReplayPayload

The handler:
  * loads the persisted ``RunState`` (404 if missing),
  * loads all per-round ``RoundState`` companions (may be empty for a
    freshly-created run),
  * calls ``build_replay_payload`` to assemble the public-safe envelope,
  * returns the envelope as-is.

No business logic, no five-step-story or chart synthesis here — Phase 8
owns those. The handler does NOT persist; ``scripts/build_replay.py``
is the canonical write path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.run import ReplayPayload  # noqa: E402
from atlas.ledger.ledger import (  # noqa: E402
    MissingRunError,
    list_run_states,
    load_round_states,
    load_run_state,
)
from atlas.ledger.replay import build_replay_payload  # noqa: E402
from atlas.model.loader import DEFAULT_DATA_DIR  # noqa: E402

router = APIRouter()


OUTPUTS_ROOT: Path = REPO_ROOT / "outputs"
DATA_DIR: Path = DEFAULT_DATA_DIR
DEMO_CASE_SEARCH_REPORT_PATH: Path = REPO_ROOT / "outputs" / "demo_case_search_report.json"


@router.get(
    "/replay/{run_id}",
    response_model=ReplayPayload,
    response_model_exclude_none=True,
)
def get_replay(run_id: str) -> dict:
    try:
        run_state = load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    round_states = load_round_states(run_id, outputs_root=OUTPUTS_ROOT)
    payload = build_replay_payload(
        run_state, round_states,
        outputs_root=OUTPUTS_ROOT,
        data_dir=DATA_DIR,
    )
    return payload


@router.get("/demo-case-search-report")
def get_demo_case_search_report() -> dict:
    """Return the transparent publish-case search report when present."""
    if not DEMO_CASE_SEARCH_REPORT_PATH.exists():
        return {"selected": None, "available": False}
    try:
        with DEMO_CASE_SEARCH_REPORT_PATH.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Demo case search report is not readable.",
        ) from exc
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=503,
            detail="Demo case search report has an invalid shape.",
        )
    raw["available"] = True
    return raw
