"""Phase 10 ``GET /model-quality-matrix`` route — thin projection of
``config/model_quality_matrix.yaml`` into the OpenAPI
``ModelQualityMatrix`` shape.

The handler:
  * loads the YAML once + memoizes,
  * synthesizes one ``MatrixCell`` per ``runs[]`` entry, mapping
    ``(red_team_tier, bank_defense_tier)`` (YAML) →
    ``(red_team_model_tier, blue_team_model_tier)`` (OpenAPI),
  * sources ``matrix_version`` from
    ``model_quality_matrix_version`` in YAML,
  * uses a closed-enum ``caveat`` string disclaiming Phase 13
    ownership of measured metric values.

Phase 10 invariant (a)(8): NO live multi-tier comparison computation.
The route ONLY reads existing read-only public-safe configuration; all
``average_*`` metrics are zeroed and ``fixed_action_rate_pass`` is
``True`` until Phase 13 fills measured values.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.model_quality import MatrixCell, ModelQualityMatrix  # noqa: E402

router = APIRouter()


# Module-level path — tests monkeypatch when they need a different
# YAML.
MATRIX_CONFIG_PATH: Path = REPO_ROOT / "config" / "model_quality_matrix.yaml"


CAVEAT: str = (
    "Read-only public-safe configuration. Per-cell metric values "
    "(average_model_miss_rate, average_recall_recovery_points, "
    "fixed_action_rate_pass) are placeholders; live multi-tier "
    "comparison runs land in Phase 13."
)


_MATRIX_CACHE: dict[str, Any] | None = None


def reset_caches() -> None:
    """Test-only — drop the memoized YAML."""
    global _MATRIX_CACHE
    _MATRIX_CACHE = None


def _load_matrix() -> dict[str, Any]:
    global _MATRIX_CACHE
    if _MATRIX_CACHE is not None:
        return _MATRIX_CACHE
    if not MATRIX_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"model_quality_matrix.yaml not found at {MATRIX_CONFIG_PATH}."
        )
    with MATRIX_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"{MATRIX_CONFIG_PATH} did not parse as a mapping."
        )
    _MATRIX_CACHE = raw
    return _MATRIX_CACHE


def _project_cells(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthesize OpenAPI ``MatrixCell`` shapes from YAML runs.

    YAML ``runs[].red_team_tier`` / ``bank_defense_tier`` →
    OpenAPI ``red_team_model_tier`` / ``blue_team_model_tier``
    (the OpenAPI schema uses ``blue_team`` whereas the project's
    public terminology elsewhere is ``bank_defense``).
    """
    out: list[dict[str, Any]] = []
    for run in runs:
        cell = MatrixCell(
            cell_id=str(run.get("run_label", "")),
            red_team_model_tier=run.get("red_team_tier", "compact"),
            blue_team_model_tier=run.get("bank_defense_tier", "compact"),
            average_model_miss_rate=0.0,
            average_recall_recovery_points=0.0,
            fixed_action_rate_pass=True,
        )
        out.append(cell.model_dump())
    return out


# ---------------------------------------------------------------------------
# GET /model-quality-matrix
# ---------------------------------------------------------------------------


@router.get(
    "/model-quality-matrix",
    response_model=ModelQualityMatrix,
    response_model_exclude_none=True,
)
def get_model_quality_matrix() -> dict:
    try:
        raw = _load_matrix()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    matrix_version = str(raw.get("model_quality_matrix_version", "matrix_v1"))
    runs = raw.get("runs") or []
    if not isinstance(runs, list):
        runs = []

    return {
        "matrix_version": matrix_version,
        "cells": _project_cells(runs),
        "caveat": CAVEAT,
    }
