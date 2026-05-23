"""``GET /model-quality-matrix`` route.

The handler:
  * loads the YAML once + memoizes,
  * synthesizes one ``MatrixCell`` per ``runs[]`` entry, mapping
    ``(red_team_tier, bank_defense_tier)`` (YAML) →
    ``(red_team_model_tier, blue_team_model_tier)`` (OpenAPI),
  * sources ``matrix_version`` from ``model_quality_matrix_version`` in YAML,
  * derives cell metrics from curated replay artifacts when a
    ``source_run_id`` is configured.

Invariant: no live model-tier comparison work happens in this route.
It only reads reviewed public-safe config plus existing replay artifacts.
Cells without a source replay return nullable metrics with
``metrics_source="unavailable"`` instead of zero-valued stand-ins.
"""

from __future__ import annotations

import json
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
REPLAY_ROOT: Path = REPO_ROOT / "outputs" / "demo_replays"
DECISION_THRESHOLDS_PATH: Path = REPO_ROOT / "config" / "decision_thresholds.yaml"


CAVEAT: str = (
    "Read-only public-safe configuration. Cells with source_run_id load "
    "judge-derived metrics from curated replay artifacts; cells without "
    "a reviewed source expose unavailable metrics explicitly."
)


_MATRIX_CACHE: dict[str, Any] | None = None
_ACTION_LIMIT_CACHE: dict[str, float] | None = None


def reset_caches() -> None:
    """Test-only — drop memoized config reads."""
    global _MATRIX_CACHE, _ACTION_LIMIT_CACHE
    _MATRIX_CACHE = None
    _ACTION_LIMIT_CACHE = None


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


def _safe_source_run_id(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        return None
    if "/" in raw or "\\" in raw or raw.startswith("."):
        return None
    return raw


def _as_float(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    return value


def _load_action_rate_limits() -> dict[str, float] | None:
    """Return replay-comparable action-rate limits as fractions."""
    global _ACTION_LIMIT_CACHE
    if _ACTION_LIMIT_CACHE is not None:
        return _ACTION_LIMIT_CACHE
    if not DECISION_THRESHOLDS_PATH.exists():
        return None
    with DECISION_THRESHOLDS_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    limits = raw.get("action_rate_limits") if isinstance(raw, dict) else None
    if not isinstance(limits, dict):
        return None
    challenge_limit = _as_float(limits.get("challenge_rate_limit_pct"))
    alert_limit = _as_float(limits.get("alert_rate_limit_pct"))
    decline_limit_bps = _as_float(limits.get("decline_rate_limit_bps"))
    if challenge_limit is None or alert_limit is None or decline_limit_bps is None:
        return None
    _ACTION_LIMIT_CACHE = {
        "challenge_rate": challenge_limit / 100.0,
        "alert_rate": alert_limit / 100.0,
        "decline_rate": decline_limit_bps / 10000.0,
    }
    return _ACTION_LIMIT_CACHE


def _unavailable_metrics(
    source_run_id: str | None,
    status: str,
) -> dict[str, Any]:
    return {
        "source_run_id": source_run_id,
        "metrics_source": "unavailable",
        "metrics_status": status,
        "average_model_miss_rate": None,
        "average_recall_recovery_points": None,
        "fixed_action_rate_pass": None,
    }


def _load_replay_snapshots(source_run_id: str) -> list[dict[str, Any]] | None:
    path = REPLAY_ROOT / f"{source_run_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    charts = raw.get("charts") if isinstance(raw, dict) else None
    snapshots = charts.get("round_metrics") if isinstance(charts, dict) else None
    if not isinstance(snapshots, list):
        return None
    return [s for s in snapshots if isinstance(s, dict)]


def _derive_replay_metrics(source_run_id: str | None) -> dict[str, Any]:
    if source_run_id is None:
        return _unavailable_metrics(None, "no_source_run")

    snapshots = _load_replay_snapshots(source_run_id)
    if not snapshots:
        return _unavailable_metrics(source_run_id, "source_unavailable")

    baseline = next(
        (
            s for s in snapshots
            if s.get("kind") == "baseline" or s.get("round_id") == 0
        ),
        None,
    )
    fixed = [
        s for s in snapshots
        if s.get("kind") == "fixed" and (_as_float(s.get("round_id")) or 0) > 0
    ]
    if baseline is None or not fixed:
        return _unavailable_metrics(source_run_id, "incomplete_source")

    miss_values = [_as_float(s.get("model_miss_rate")) for s in fixed]
    baseline_recall = _as_float(baseline.get("recall_at_fixed_action_rate"))
    final_recall = _as_float(fixed[-1].get("recall_at_fixed_action_rate"))
    limits = _load_action_rate_limits()
    if (
        any(v is None for v in miss_values)
        or baseline_recall is None
        or final_recall is None
        or limits is None
    ):
        return _unavailable_metrics(source_run_id, "incomplete_source")
    numeric_miss_values = [v for v in miss_values if v is not None]

    action_rates_complete = all(
        _as_float(s.get(rate_name)) is not None
        for s in fixed
        for rate_name in limits
    )
    if not action_rates_complete:
        return _unavailable_metrics(source_run_id, "incomplete_source")

    fixed_action_rate_pass = all(
        _as_float(s[rate_name]) <= limit + 1e-12
        for s in fixed
        for rate_name, limit in limits.items()
    )

    return {
        "source_run_id": source_run_id,
        "metrics_source": "judge_derived_replay",
        "metrics_status": "loaded",
        "average_model_miss_rate": round(
            sum(numeric_miss_values) / len(numeric_miss_values),
            4,
        ),
        "average_recall_recovery_points": round(
            (final_recall - baseline_recall) * 100.0,
            4,
        ),
        "fixed_action_rate_pass": fixed_action_rate_pass,
    }


def _project_cells(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthesize OpenAPI ``MatrixCell`` shapes from YAML runs.

    YAML ``runs[].red_team_tier`` / ``bank_defense_tier`` →
    OpenAPI ``red_team_model_tier`` / ``blue_team_model_tier``
    (the OpenAPI schema uses ``blue_team`` whereas the project's
    public terminology elsewhere is ``bank_defense``).
    """
    out: list[dict[str, Any]] = []
    for run in runs:
        source_run_id = _safe_source_run_id(run.get("source_run_id"))
        metrics_source = run.get("metrics_source")
        metrics = (
            _derive_replay_metrics(source_run_id)
            if metrics_source == "judge_derived_replay"
            else _unavailable_metrics(None, "no_source_run")
        )
        cell = MatrixCell(
            cell_id=str(run.get("run_label", "")),
            red_team_model_tier=run.get("red_team_tier", "compact"),
            blue_team_model_tier=run.get("bank_defense_tier", "compact"),
            **metrics,
        )
        out.append(cell.model_dump())
    return out


# ---------------------------------------------------------------------------
# GET /model-quality-matrix
# ---------------------------------------------------------------------------


@router.get(
    "/model-quality-matrix",
    response_model=ModelQualityMatrix,
    response_model_exclude_none=False,
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
