"""POST /red-team/search — Phase 6 deterministic red-team search route.

Validates the request via ``RedTeamSearchRequest`` (which uses
``extra="forbid"`` — a client-supplied ``model_vulnerability_cards`` or
other free-form override is rejected at the boundary), runs
``atlas.red_team.fraud_scenario_agent.run_search(...)``, packages
``ModelVulnerabilityCard``s via
``atlas.red_team.model_vulnerability_packager.package_cards(...)``, and
returns ``RedTeamSearchResponse``.

Error mapping (mirrors Phase 5 ``app/api/routes/judge.py``):

  * ``MissingBaselineModelError``  → 503 ("run ``make train`` first").
  * ``MissingDatasetError``        → 503 ("run ``make seed`` first").
  * ``FileNotFoundError`` for round_config.yaml → 503.
  * ``ValueError`` (unknown round_id, empty intersections, negative
    budget, etc.) → 422.

Same inputs always produce a byte-identical response (Bible §18 Phase 6
deterministic + reproducible JSON).
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.red_team import (  # noqa: E402
    RedTeamSearchRequest,
    RedTeamSearchResponse,
)
from atlas.blue_team.manifest import (  # noqa: E402
    DEFAULT_OUTPUTS_ROOT,
    persist_cards_as_records,
)
import atlas.red_team.fraud_scenario_agent as fsa_mod  # noqa: E402
from atlas.red_team.fraud_scenario_agent import run_search  # noqa: E402
from atlas.red_team.model_vulnerability_packager import (  # noqa: E402
    ModelVulnerabilityCard,
    package_cards,
)
from atlas.model.loader import MissingDatasetError  # noqa: E402
from atlas.model.scorer import MissingBaselineModelError  # noqa: E402

router = APIRouter()


# Phase 7 hook — persist Phase 6 cards as ModelVulnerabilityRecords so
# ``POST /defensive-fixes/propose`` can resolve ``model_vulnerability_id``
# without re-running search. Tests monkeypatch this to a tmp dir.
OUTPUTS_ROOT = DEFAULT_OUTPUTS_ROOT


def reset_caches() -> None:
    """Test-only — drop cached bundles, configs, and base state."""
    fsa_mod.reset_caches()


def _card_to_dict(card: ModelVulnerabilityCard) -> dict:
    """Convert dataclass → dict for the Pydantic response model.

    ``recommended_defensive_fix_types`` is a tuple in the dataclass; the
    response schema expects a list, so convert.
    """
    d = asdict(card)
    d["recommended_defensive_fix_types"] = list(d["recommended_defensive_fix_types"])
    return d


@router.post(
    "/red-team/search",
    response_model=RedTeamSearchResponse,
    response_model_exclude_none=True,
)
def post_red_team_search(req: RedTeamSearchRequest) -> dict:
    try:
        result = run_search(
            run_id=req.run_id,
            round_id=req.round_id,
            search_methods=req.search_methods,
            max_score_queries=req.max_score_queries,
            allowed_family_ids=req.allowed_family_ids,
        )
    except MissingBaselineModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MissingDatasetError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        # round_config.yaml missing — treat like make-seed/make-train flow.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # Unknown round_id, empty family/method intersections, negative
        # budget, allocator violations — surface as 422 since the
        # request, not the server state, is what's wrong.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cards = package_cards(
        candidates=result.candidates,
        round_id=result.round_id,
        random_baseline=result.by_method.get("random"),
    )

    # Phase 7 hook — durable lookup keyed by model_vulnerability_id.
    # Non-breaking: failure to write (e.g., read-only fs) is non-fatal
    # because Phase 6 search itself doesn't depend on persistence.
    try:
        persist_cards_as_records(
            cards,
            run_id=result.run_id,
            found_adaptive_set_event_ids=list(result.found_adaptive_set_event_ids),
            outputs_root=OUTPUTS_ROOT,
        )
    except OSError:
        pass

    return {
        "run_id": result.run_id,
        "round_id": result.round_id,
        "valid_high_risk_events_tested": result.valid_high_risk_events_tested,
        "accepted_high_risk_events": result.accepted_high_risk_events,
        "model_miss_rate": result.model_miss_rate,
        "miss_rate_lift_vs_random": result.miss_rate_lift_vs_random,
        "found_adaptive_set_event_ids": list(result.found_adaptive_set_event_ids),
        "model_vulnerability_cards": [_card_to_dict(c) for c in cards],
    }
