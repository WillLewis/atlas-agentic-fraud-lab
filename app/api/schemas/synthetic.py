"""Pydantic schemas for `/synthetic/sample` (Phase 4).

Mirrors the OpenAPI ``Customer`` / ``EventRecord`` / ``FeatureVector`` /
``SyntheticSampleResponse`` shapes. The persisted Phase 2/3 dataset uses
``transfer_event_id``; the ``EventRecord`` schema renames to ``event_id``
at the API boundary so the OpenAPI public contract stays satisfied
without a dataset rewrite.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerSchema(_StrictModel):
    customer_id: str
    customer_segment: str
    home_region_bucket: str
    account_age_days: int
    normal_login_frequency_30d: int | None = None
    normal_transfer_frequency_30d: int | None = None
    synthetic_base_risk: float | None = None


class EventRecordSchema(_StrictModel):
    """Normalized API view. ``event_id`` ← persisted ``transfer_event_id``."""

    event_id: str
    customer_id: str
    event_type: str
    event_time_utc: str
    device_id: str | None = None
    account_id: str | None = None
    recipient_id: str | None = None
    channel: str | None = None
    amount_bucket: str | None = None
    # OpenAPI marks this required; the scorer never reads it (component 6
    # tests cover label-leakage invariance).
    synthetic_truth_label: str = Field(
        pattern="^(normal_activity|high_risk_synthetic_activity)$"
    )


class FeatureVectorSchema(_StrictModel):
    """17 fields — mirrors ``atlas.synthetic.features.FeatureVector``."""

    event_id: str
    customer_id: str
    login_count_72h: int = Field(ge=0)
    login_count_30d: int = Field(ge=0)
    login_velocity_ratio: float = Field(ge=0)
    challenge_count_72h: int = Field(ge=0)
    challenge_pass_ratio_30d: float = Field(ge=0, le=1)
    password_recovery_count_72h: int = Field(ge=0)
    device_count_72h: int = Field(ge=0)
    current_device_tenure_days: int = Field(ge=0)
    geo_consistency_flag: int = Field(ge=0, le=1)
    transfer_count_72h: int = Field(ge=0)
    recipient_tenure_days: int = Field(ge=0)
    shared_device_degree: int = Field(ge=0)
    shared_recipient_degree: int = Field(ge=0)
    entity_graph_risk_score: float = Field(ge=0, le=1)
    cash_movement_velocity_score: float = Field(ge=0, le=1)


class SyntheticSampleResponse(_StrictModel):
    customers: list[CustomerSchema]
    events: list[EventRecordSchema]
    features: list[FeatureVectorSchema]
