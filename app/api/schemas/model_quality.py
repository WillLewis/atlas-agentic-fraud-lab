"""Pydantic schemas for ``GET /model-quality-matrix``.

Mirrors the OpenAPI ``ModelQualityMatrix`` shape:

  * ``matrix_version``  — version string (sourced from YAML).
  * ``cells``           — synthesized one per ``(red_team_tier,
                          blue_team_tier)`` pair from the YAML
                          ``runs`` list.
  * ``caveat``          — public-safe provenance note for measured vs.
                          unavailable cell metrics.

This schema is the OpenAPI projection. The web-side
``app/web/lib/modelQualityMatrix.ts`` loads the YAML directly and uses
its native shape (``tiers``, ``runs``, ``summary_templates``); both
consumers share one source of truth (``config/model_quality_matrix.yaml``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MatrixCell(BaseModel):
    """One projected matrix cell. Mirrors OpenAPI
    ``ModelQualityMatrix.cells.items``.

    ``average_*`` and ``fixed_action_rate_pass`` are nullable by design:
    cells with ``metrics_source="judge_derived_replay"`` carry values
    computed from curated replay artifacts, while cells with unavailable
    sources carry explicit ``None`` values instead of zero-valued
    stand-ins.
    """

    model_config = ConfigDict(extra="allow")

    cell_id: str
    red_team_model_tier: Literal["frontier", "compact"]
    blue_team_model_tier: Literal["frontier", "compact"]
    source_run_id: str | None = None
    metrics_source: Literal["judge_derived_replay", "unavailable"] = "unavailable"
    metrics_status: Literal[
        "loaded",
        "no_source_run",
        "source_unavailable",
        "incomplete_source",
    ] = "no_source_run"
    average_model_miss_rate: float | None = None
    average_recall_recovery_points: float | None = None
    fixed_action_rate_pass: bool | None = None


class ModelQualityMatrix(BaseModel):
    """Mirrors OpenAPI ``ModelQualityMatrix``."""

    model_config = ConfigDict(extra="allow")

    matrix_version: str
    cells: list[MatrixCell] = Field(default_factory=list)
    caveat: str


__all__ = [
    "MatrixCell",
    "ModelQualityMatrix",
]
