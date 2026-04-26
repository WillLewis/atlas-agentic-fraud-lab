"""Pydantic schemas for read-only metadata routes (Phase 4).

Mirrors the OpenAPI shapes for ``DemoConfig``, ``DecisionThresholds``,
``SyntheticSchemaResponse``, and shared error envelopes. Field names use
the OpenAPI public contract (``threshold_version``,
``manual_review_rate_limit_pct``); the persisted-config field-name
translation lives in the ``decision_thresholds`` route adapter.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Reject unknown fields by default — Phase 4 schemas are explicit."""

    model_config = ConfigDict(extra="forbid")


class DemoConfigResponse(_StrictModel):
    demo_mode: str
    institution_label: str
    model_label: str
    disclaimer: str


class DecisionThresholdsResponse(_StrictModel):
    threshold_version: str
    decline_score_threshold: float = Field(ge=0, le=1)
    challenge_score_threshold: float = Field(ge=0, le=1)
    alert_score_threshold: float = Field(ge=0, le=1)
    decline_rate_limit_bps: float
    challenge_rate_limit_pct: float
    alert_rate_limit_pct: float
    manual_review_rate_limit_pct: float


class SyntheticSchemaResponse(_StrictModel):
    entity_types: list[str]
    event_types: list[str]
    feature_names: list[str]
    allowed_model_vulnerability_families: list[str]


class ErrorResponse(BaseModel):
    """OpenAPI ``ErrorResponse`` envelope. Used for 4xx / 5xx replies."""

    error: str
    details: dict[str, Any] | None = None
