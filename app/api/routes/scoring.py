"""POST /score and POST /batch-score routes.

Loads the trained baseline bundle and the decision-policy config once at
module import time. If artifacts are missing the routes return 503 with
a clear "run `make train`" hint.

Phase 4 invariants enforced here:
  * Scorer reads only the 17 FeatureVector fields. ``synthetic_truth_label``
    is on the EventRecord (for OpenAPI compat) but never reaches the
    feature matrix — `score_features(features.dict(), bundle)` only sees
    the FeatureVector schema.
  * Decision policy + reason codes come straight from the Phase 4 policy
    module — no API-layer overrides.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.scoring import (  # noqa: E402
    BatchScoreRequest,
    BatchScoreResponse,
    ScoreRequest,
    ScoreResponse,
)
import atlas.model.scorer as scorer_mod  # noqa: E402  (read DEFAULT_OUTPUT_DIR at call time)
from atlas.model.policy import (  # noqa: E402
    DEFAULT_OUTPUTS_ROOT,
    DecisionPolicyConfig,
    apply_decision_policy,
    resolve_decision_policy_config,
)
from atlas.model.scorer import (  # noqa: E402
    BaselineModelBundle,
    MissingBaselineModelError,
    load_baseline_bundle,
    score_features,
)

router = APIRouter()
OUTPUTS_ROOT = DEFAULT_OUTPUTS_ROOT

# Module-level lazy-load. The route handlers call ``_get_bundle`` /
# ``_get_policy_config`` which cache on first use. This keeps test
# fixtures simple — they can swap the cached instances directly.
_bundle: BaselineModelBundle | None = None
_policy_config: DecisionPolicyConfig | None = None


def _get_bundle() -> BaselineModelBundle:
    global _bundle
    if _bundle is None:
        try:
            # Read DEFAULT_OUTPUT_DIR via module attribute so tests can
            # monkeypatch it. (A bare ``load_baseline_bundle()`` would bind
            # the default at function-definition time and miss the patch.)
            _bundle = load_baseline_bundle(scorer_mod.DEFAULT_OUTPUT_DIR)
        except MissingBaselineModelError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _bundle


def _get_policy_config() -> DecisionPolicyConfig:
    global _policy_config
    if _policy_config is None:
        _policy_config = resolve_decision_policy_config(
            outputs_root=OUTPUTS_ROOT,
        )
    return _policy_config


def reset_caches() -> None:
    """Test-only — drop cached bundle + config so the next request reloads."""
    global _bundle, _policy_config
    _bundle = None
    _policy_config = None


def _score_one(req: ScoreRequest) -> ScoreResponse:
    bundle = _get_bundle()
    config = _get_policy_config()

    if req.event.event_id != req.features.event_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"event.event_id ({req.event.event_id!r}) and "
                f"features.event_id ({req.features.event_id!r}) must match"
            ),
        )

    # FeatureVector dict — exclude None-only optional fields and the two IDs
    # are still emitted because the scorer's column projector ignores them.
    fv_dict = req.features.model_dump()
    raw_score = score_features(fv_dict, bundle)

    decision = apply_decision_policy(raw_score, fv_dict, config)
    return ScoreResponse(
        event_id=req.event.event_id,
        score=decision.score,
        decision_action=decision.decision_action,
        decision_band=decision.decision_band,
        model_version=bundle.model_version,
        threshold_version=decision.threshold_version,
        reason_codes=list(decision.reason_codes),
    )


@router.post("/score", response_model=ScoreResponse)
def post_score(req: ScoreRequest) -> ScoreResponse:
    return _score_one(req)


@router.post("/batch-score", response_model=BatchScoreResponse)
def post_batch_score(req: BatchScoreRequest) -> BatchScoreResponse:
    bundle = _get_bundle()
    scored = [_score_one(r) for r in req.records]
    config = _get_policy_config()
    return BatchScoreResponse(
        scores=scored,
        model_version=bundle.model_version,
        threshold_version=config.threshold_version,
    )
