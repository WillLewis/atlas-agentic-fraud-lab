"""Pydantic schemas for ``POST /red-team/search`` (Phase 6).

Mirrors the OpenAPI ``RedTeamSearchRequest`` / ``RedTeamSearchResponse``
/ ``ModelVulnerabilityCard`` shapes. ``extra="forbid"`` so a
client-supplied override (e.g. injecting ``model_vulnerability_cards``
into a request) is rejected at the boundary — Bible §6.1: agent text
cannot drive judge or red-team output.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class RedTeamSearchRequest(_StrictModel):
    run_id: str
    round_id: int
    allowed_family_ids: list[str] | None = None
    max_score_queries: int = Field(ge=1)
    search_methods: list[str] = Field(min_length=1)


# ---------------------------------------------------------------------------
# ModelVulnerabilityCard
# ---------------------------------------------------------------------------


class ModelVulnerabilityCardSchema(_StrictModel):
    model_vulnerability_id: str
    round_id: int
    family_id: str
    summary: str
    valid_high_risk_events_tested: int | None = None
    accepted_high_risk_events: int | None = None
    model_miss_rate: float
    miss_rate_lift_vs_random: float | None = None
    estimated_synthetic_loss_allowed: float | None = None
    affected_decision_action: str | None = None
    safe_cohort_definition: dict[str, Any] | None = None
    recommended_defensive_fix_types: list[str] | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class RedTeamSearchResponse(_StrictModel):
    run_id: str
    round_id: int
    valid_high_risk_events_tested: int
    accepted_high_risk_events: int
    model_miss_rate: float
    miss_rate_lift_vs_random: float | None = None
    found_adaptive_set_event_ids: list[str] | None = None
    model_vulnerability_cards: list[ModelVulnerabilityCardSchema] | None = None
