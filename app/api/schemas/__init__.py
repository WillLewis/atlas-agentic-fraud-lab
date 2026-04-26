"""Pydantic schemas + persisted-record adapters for Phase 4.

Two responsibilities:

  1. Mirror the API request / response shapes from
     ``project_atlas_openapi.yaml`` so FastAPI can validate payloads.
  2. Adapt the persisted Phase 2/3 record shapes to the API shapes
     without renaming the stored data:
       * ``transfer_event_id`` (persisted) → ``event_id`` (API)
       * ``decision_threshold_version`` (config) → ``threshold_version`` (API)
       * ``review_rate_limit_pct`` (config) → ``manual_review_rate_limit_pct`` (API)
"""

__all__: list[str] = []
