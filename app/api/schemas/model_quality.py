"""Pydantic schemas for ``GET /model-quality-matrix`` (Phase 10).

Mirrors the OpenAPI ``ModelQualityMatrix`` shape:

  * ``matrix_version``  — version string (sourced from YAML).
  * ``cells``           — synthesized one per ``(red_team_tier,
                          blue_team_tier)`` pair from the YAML
                          ``runs`` list.
  * ``caveat``          — closed-enum string disclaiming that this is
                          public-safe configuration (Phase 13 will
                          carry measured values).

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

    Phase 10 emits ``average_*`` metrics zeroed and
    ``fixed_action_rate_pass=true`` since the YAML carries no measured
    values; Phase 13 will populate these from real comparison runs.
    """

    model_config = ConfigDict(extra="allow")

    cell_id: str
    red_team_model_tier: Literal["frontier", "compact"]
    blue_team_model_tier: Literal["frontier", "compact"]
    average_model_miss_rate: float = 0.0
    average_recall_recovery_points: float = 0.0
    fixed_action_rate_pass: bool = True


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
