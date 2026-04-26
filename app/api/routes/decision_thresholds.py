"""GET /decision-thresholds route.

Adapts the persisted-config field names to the OpenAPI public contract
exactly once at the route boundary (the only place the translation lives).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.common import DecisionThresholdsResponse  # noqa: E402

import yaml  # noqa: E402

THRESHOLDS_CONFIG_PATH = REPO_ROOT / "config" / "decision_thresholds.yaml"

router = APIRouter()


@router.get("/decision-thresholds", response_model=DecisionThresholdsResponse)
def get_decision_thresholds() -> DecisionThresholdsResponse:
    with THRESHOLDS_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    thresholds = cfg["decision_thresholds"]
    rate_limits = cfg["action_rate_limits"]

    # Persisted → API name translation: this is the single point of mapping.
    return DecisionThresholdsResponse(
        threshold_version=cfg["decision_threshold_version"],
        decline_score_threshold=thresholds["decline_score_threshold"],
        challenge_score_threshold=thresholds["challenge_score_threshold"],
        alert_score_threshold=thresholds["alert_score_threshold"],
        decline_rate_limit_bps=rate_limits["decline_rate_limit_bps"],
        challenge_rate_limit_pct=rate_limits["challenge_rate_limit_pct"],
        alert_rate_limit_pct=rate_limits["alert_rate_limit_pct"],
        manual_review_rate_limit_pct=rate_limits["review_rate_limit_pct"],
    )
