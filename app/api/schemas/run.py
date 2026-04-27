"""Pydantic schemas for the Phase 9 run / round / replay surface.

Mirrors the OpenAPI shapes defined in ``project_atlas_openapi.yaml``:

  * ``RunCreateRequest``        (lines 759–778)
  * ``RunSummary``              (lines 779–796)
  * ``RunDetail``               (lines 797–807, allOf RunSummary)
  * ``RoundRunRequest``         (lines 808–826)
  * ``RoundRunResponse``        (lines 827–836)
  * ``RoundSummary``            (lines 837–858)
  * ``RoundDetail``             (lines 859–875, allOf RoundSummary)
  * ``MetricSnapshot``          (lines 1091–1110)
  * ``ReplayPayload``           (lines 1111–1131)

Phase 9 reconciliation:

  * ``RoundDetail`` carries the closed-enum
    ``transcript_summary`` produced by ``atlas.ledger.report_builder``
    so Bible §18 transcript wording is satisfied without inventing a
    public ``/transcripts`` endpoint.
  * ``ReplayPayload.charts.round_metrics`` is the metric series
    (``MetricSnapshot[]``) Bible §18 calls out — also no separate
    ``/metrics`` route family.

Request schemas use ``extra="forbid"`` so the boundary rejects unknown
fields. Response schemas allow extra fields so the existing replay
payload's open-shaped ``cards`` arrays + ``charts`` dict are surfaced
unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Shared metric snapshot
# ---------------------------------------------------------------------------


class MetricSnapshot(BaseModel):
    """Mirrors OpenAPI ``MetricSnapshot``. Field names match
    ``app/web/lib/types.ts.MetricSnapshot`` and
    ``src/atlas/ledger/replay.py:_make_snapshot`` exactly.
    """

    model_config = ConfigDict(extra="allow")

    round_id: int
    round_label: str
    kind: Literal["baseline", "fixed", "interpolated"]
    model_miss_rate: float
    recall_at_fixed_action_rate: float
    false_positive_rate_at_fixed_action_rate: float
    synthetic_loss_allowed: float
    challenge_rate: float
    alert_rate: float
    decline_rate: float


# ---------------------------------------------------------------------------
# Run schemas
# ---------------------------------------------------------------------------


class RunCreateRequest(_StrictModel):
    seed: int
    run_label: str | None = None
    demo_mode: Literal["public", "internal"] = "public"
    max_rounds: int = Field(default=3, ge=1, le=5)
    max_score_queries_per_round: int = Field(default=1200, ge=1)


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    seed: int
    demo_mode: str
    status: Literal["created", "running", "completed", "failed"]
    current_round: int | None = None
    created_at_utc: str | None = None


class RoundSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    round_id: int
    status: str
    model_version_before: str | None = None
    model_version_after: str | None = None
    model_miss_rate_before: float | None = None
    model_miss_rate_after: float | None = None
    recall_at_fixed_action_rate_before: float | None = None
    recall_at_fixed_action_rate_after: float | None = None


class RunDetail(RunSummary):
    rounds: list[RoundSummary] = Field(default_factory=list)
    latest_metrics: MetricSnapshot | None = None


# ---------------------------------------------------------------------------
# Round schemas
# ---------------------------------------------------------------------------


class RoundRunRequest(_StrictModel):
    run_id: str
    start_round: int = Field(default=1, ge=1)
    round_count: int = Field(default=1, ge=1, le=3)
    max_score_queries_per_round: int = Field(default=1200, ge=1)


class RoundRunResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    completed_rounds: list[RoundSummary]


class RoundDetail(RoundSummary):
    """Mirrors OpenAPI ``RoundDetail``. Phase 9 surfaces the deterministic
    closed-enum transcript summary alongside the round's persisted
    artifact arrays so the web shell can render the SafeTranscriptPanel
    + cards without a separate transcript route.
    """

    model_vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    defensive_fixes: list[dict[str, Any]] = Field(default_factory=list)
    judge_reports: list[dict[str, Any]] = Field(default_factory=list)
    transcript_summary: str | None = None
    safety_scan_passed: bool | None = None


# ---------------------------------------------------------------------------
# Replay payload
# ---------------------------------------------------------------------------


class ReplayPayload(BaseModel):
    """Mirrors OpenAPI ``ReplayPayload``. The five-step ``cards`` arrays
    and ``charts`` dict are open-shaped (replay-side authoritative
    artifact mosaic), so we allow extras and use ``dict[str, Any]``
    on the open envelopes.
    """

    model_config = ConfigDict(extra="allow")

    run: RunDetail
    five_step_story: list[dict[str, Any]]
    charts: dict[str, Any]


__all__ = [
    "MetricSnapshot",
    "ReplayPayload",
    "RoundDetail",
    "RoundRunRequest",
    "RoundRunResponse",
    "RoundSummary",
    "RunCreateRequest",
    "RunDetail",
    "RunSummary",
]
