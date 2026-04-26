"""GET /schema route — returns synthetic schema metadata."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.common import SyntheticSchemaResponse  # noqa: E402

import yaml  # noqa: E402

SCHEMA_CONFIG_PATH = REPO_ROOT / "config" / "synthetic_schema.yaml"

router = APIRouter()


@router.get("/schema", response_model=SyntheticSchemaResponse)
def get_schema() -> SyntheticSchemaResponse:
    with SCHEMA_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    # Phase 3 emitted feature contract — the only feature surface this
    # API ever exposes. `feature_families` (Bible §11.3 superset) is
    # documentation only and must not leak through here.
    p3 = cfg.get("phase_3_emitted_features", {})
    feature_names: list[str] = []
    for v in p3.values():
        if isinstance(v, list):
            feature_names.extend(v)
    # Drop the two ID fields — they're references, not features.
    feature_names = [f for f in feature_names if f not in {"event_id", "customer_id"}]

    entity_types = list(cfg.get("entities", {}).keys())
    event_types = list(cfg.get("events", {}).get("allowed_types", []))
    families = [f["id"] for f in cfg.get("model_vulnerability_families", [])]

    return SyntheticSchemaResponse(
        entity_types=entity_types,
        event_types=event_types,
        feature_names=feature_names,
        allowed_model_vulnerability_families=families,
    )
