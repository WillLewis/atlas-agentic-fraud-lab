"""Pydantic schemas for `/score` and `/batch-score` (Phase 4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.synthetic import EventRecordSchema, FeatureVectorSchema

MAX_BATCH_SIZE: int = 5000


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreRequest(_StrictModel):
    event: EventRecordSchema
    features: FeatureVectorSchema
    model_version: str = "baseline_v1"
    threshold_version: str = "thresholds_v1"


class ScoreResponse(_StrictModel):
    """Bible §18 Phase 4 acceptance: 7 required fields."""

    event_id: str
    score: float = Field(ge=0, le=1)
    decision_action: str = Field(pattern="^(accept|challenge|alert|decline)$")
    decision_band: str
    model_version: str
    threshold_version: str
    reason_codes: list[str]


class BatchScoreRequest(_StrictModel):
    records: list[ScoreRequest] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class BatchScoreResponse(_StrictModel):
    scores: list[ScoreResponse]
    model_version: str
    threshold_version: str
