"""POST /judge/evaluate-fix — Phase 5 deterministic judge route.

Validates the request via ``JudgeEvaluationRequest`` (which uses
``extra="forbid"`` — a client-supplied ``judge_notes`` is rejected at
the boundary), runs ``atlas.judge.evaluate.evaluate_fix(...)``, and
returns the resulting ``JudgeReport``.

Error mapping:

  * ``MissingBaselineModelError``       → 503 ("run ``make train`` first").
  * ``MissingDatasetError``             → 503 ("run ``make seed`` first").
  * ``UnknownThresholdVersionError``    → 422 (Phase 5 supports only
                                            ``thresholds_v1``).
  * ``ValueError`` from holdout loaders → 422 (e.g. bogus
                                            ``found_adaptive_set_event_ids``).

Same inputs always produce a byte-identical response (Bible §18 Phase 5
acceptance: deterministic + reproducible JSON).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.judge import (  # noqa: E402
    JudgeEvaluationRequest,
    JudgeReportResponse,
)
import atlas.judge.acceptance as acceptance_mod  # noqa: E402
import atlas.judge.evaluate as evaluate_mod  # noqa: E402
from atlas.judge.evaluate import (  # noqa: E402
    UnknownThresholdVersionError,
    evaluate_fix,
)
from atlas.model.loader import MissingDatasetError  # noqa: E402
from atlas.model.scorer import MissingBaselineModelError  # noqa: E402

router = APIRouter()


def reset_caches() -> None:
    """Test-only — drop cached bundles, configs, and acceptance policy."""
    evaluate_mod.reset_caches()
    acceptance_mod.reset_caches()


@router.post(
    "/judge/evaluate-fix",
    response_model=JudgeReportResponse,
    response_model_exclude_none=True,
)
def post_evaluate_fix(req: JudgeEvaluationRequest) -> dict:
    try:
        report = evaluate_fix(
            run_id=req.run_id,
            round_id=req.round_id,
            defensive_fix_id=req.defensive_fix_id,
            baseline_model_version=req.baseline_model_version,
            candidate_model_version=req.candidate_model_version,
            baseline_threshold_version=req.baseline_threshold_version,
            candidate_threshold_version=req.candidate_threshold_version,
            found_adaptive_set_event_ids=req.found_adaptive_set_event_ids,
        )
    except MissingBaselineModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MissingDatasetError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownThresholdVersionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        # Holdout loader rejections (bogus found_adaptive_set IDs,
        # misaligned features/labels, etc.) — surface as 422 since the
        # request, not the server state, is what's wrong.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report
