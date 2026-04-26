"""GET /config/demo route."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.common import DemoConfigResponse  # noqa: E402

# Load the Phase 1 web's config loader pattern but server-side.
import yaml  # noqa: E402

DEMO_CONFIG_PATH = REPO_ROOT / "config" / "demo.yaml"

router = APIRouter()


@router.get("/config/demo", response_model=DemoConfigResponse)
def get_demo_config() -> DemoConfigResponse:
    with DEMO_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return DemoConfigResponse(
        demo_mode=cfg["demo_mode"],
        institution_label=cfg["institution_label"],
        model_label=cfg["model_label"],
        disclaimer=cfg["disclaimer"],
    )
