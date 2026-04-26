"""Pydantic schemas for `POST /judge/evaluate-fix` (Phase 5).

Mirrors the OpenAPI ``JudgeEvaluationRequest`` / ``JudgeReport`` /
``MetricSnapshot`` shapes. ``extra="forbid"`` so a client-supplied
``judge_notes`` (or any other free-form override) is rejected at the
boundary — Bible §18 Phase 5 acceptance criterion: agent text cannot
override judge results.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JudgeEvaluationRequest(_StrictModel):
    run_id: str
    round_id: int
    defensive_fix_id: str
    baseline_model_version: str
    candidate_model_version: str
    baseline_threshold_version: str | None = None
    candidate_threshold_version: str | None = None
    found_adaptive_set_event_ids: list[str] | None = None


class MetricSnapshotSchema(_StrictModel):
    recall_at_fixed_action_rate: float = Field(ge=0, le=1)
    false_positive_rate_at_fixed_action_rate: float = Field(ge=0, le=1)
    model_miss_rate: float = Field(ge=0, le=1)
    synthetic_loss_allowed: float | None = None
    synthetic_loss_prevented: float | None = None
    challenge_rate: float | None = Field(default=None, ge=0, le=1)
    alert_rate: float | None = Field(default=None, ge=0, le=1)
    decline_rate: float | None = Field(default=None, ge=0, le=1)


class HoldoutGeneralizationSchema(_StrictModel):
    clean_holdout_pass: bool
    found_adaptive_set_pass: bool | None = None
    locked_adaptive_holdout_pass: bool
    drifted_holdout_pass: bool


class JudgeReportResponse(_StrictModel):
    judge_report_id: str
    run_id: str
    round_id: int
    defensive_fix_id: str
    accepted_by_judge: bool
    baseline: MetricSnapshotSchema
    fixed: MetricSnapshotSchema
    holdout_generalization: HoldoutGeneralizationSchema
    judge_notes: str
