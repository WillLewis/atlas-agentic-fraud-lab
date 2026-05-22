"""POST /defensive-fixes/{propose,apply} — Phase 7 deterministic
bank-defense routes.

Validates each request via Pydantic (``extra="forbid"`` so a
client-supplied ``description`` / ``applied`` / ``governance_rationale``
is rejected at the boundary), runs the in-process Phase 7 logic, and
returns the matching response.

Error mapping (mirrors Phase 5/6):

  * ``MissingBaselineModelError``      → 503 ("run ``make train`` first").
  * ``MissingDatasetError``            → 503 ("run ``make seed`` first").
  * ``MissingVulnerabilityError``      → 503 ("run ``POST /red-team/search`` first").
  * ``MissingManifestError``           → 503 ("run ``POST /defensive-fixes/propose`` first").
  * ``UnknownThresholdVersionError``   → 422 (judge-side: candidate
                                           threshold version not on disk).
  * ``ValueError`` (intersection / unknown family / wrong fix_type) → 422.
  * Pydantic extra-field / validation error → 422 (FastAPI default).

Same inputs always produce a byte-identical response — the orchestrators
under ``atlas.blue_team`` are deterministic.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.fix import (  # noqa: E402
    DefensiveFixApplyRequest,
    DefensiveFixApplyResponse,
    DefensiveFixCandidateSchema,
    DefensiveFixProposalRequest,
    DefensiveFixProposalResponse,
)
import atlas.blue_team.fix_applier as applier_mod  # noqa: E402
import atlas.blue_team.strategy_agent as strategy_mod  # noqa: E402
from atlas.blue_team.fix_applier import apply_fix  # noqa: E402
from atlas.blue_team.manifest import (  # noqa: E402
    MissingManifestError,
    MissingVulnerabilityError,
)
from atlas.blue_team.strategy_agent import propose_fixes  # noqa: E402
from atlas.judge.evaluate import UnknownThresholdVersionError  # noqa: E402
from atlas.ledger.ledger import (  # noqa: E402
    MissingRunError,
    load_round_state,
    load_run_state,
)
from atlas.model.loader import DEFAULT_DATA_DIR, MissingDatasetError  # noqa: E402
from atlas.model.scorer import MissingBaselineModelError  # noqa: E402

router = APIRouter()


# Module-level paths — tests monkeypatch these to point at tmp dirs so
# Phase 7 candidates land where the judge fixture's
# ``BASELINE_MODELS_ROOT`` and ``ALTERNATE_THRESHOLDS_ROOT`` look.
OUTPUTS_ROOT: Path = REPO_ROOT / "outputs"
DATA_DIR: Path = DEFAULT_DATA_DIR


def reset_caches() -> None:
    """Test-only — drop strategy + fix_applier module caches."""
    strategy_mod.reset_caches()


# ---------------------------------------------------------------------------
# /defensive-fixes/propose
# ---------------------------------------------------------------------------


def _candidate_to_dict(candidate) -> dict:
    """``DefensiveFixCandidate`` dataclass → dict for the Pydantic
    response model. Preserves the OpenAPI shape (lines 980–1007).
    """
    d = asdict(candidate)
    d["files_changed"] = list(d["files_changed"])
    return d


def _carry_forward_versions_for_request(
    *,
    run_id: str,
    round_id: int,
) -> tuple[str | None, str | None]:
    """Return the versions that should be the baseline for ``round_id``.

    The full round engine is the canonical carry-forward writer. These
    standalone Phase 7 routes are still useful for direct API workflows,
    so they derive the current versions from already-persisted run/round
    state when present. Missing state falls back to ``None`` so legacy
    standalone calls continue to use ``baseline_v1`` / ``thresholds_v1``.
    """
    if round_id <= 1:
        return None, None

    previous_round_id = round_id - 1
    try:
        previous = load_round_state(
            run_id,
            previous_round_id,
            outputs_root=OUTPUTS_ROOT,
        )
        return previous.model_version_after, previous.threshold_version_after
    except MissingRunError:
        pass

    try:
        run_state = load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError:
        return None, None

    if run_state.current_round == previous_round_id:
        return run_state.current_model_version, run_state.current_threshold_version
    return None, None


@router.post(
    "/defensive-fixes/propose",
    response_model=DefensiveFixProposalResponse,
    response_model_exclude_none=True,
)
def post_defensive_fixes_propose(req: DefensiveFixProposalRequest) -> dict:
    try:
        _, current_threshold_version = _carry_forward_versions_for_request(
            run_id=req.run_id,
            round_id=req.round_id,
        )
        candidates = propose_fixes(
            run_id=req.run_id,
            round_id=req.round_id,
            model_vulnerability_ids=req.model_vulnerability_ids,
            allowed_fix_types=req.allowed_fix_types,
            outputs_root=OUTPUTS_ROOT,
            current_threshold_version=current_threshold_version,
        )
    except MissingVulnerabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        # round_config.yaml or decision_thresholds.yaml missing.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "run_id": req.run_id,
        "round_id": req.round_id,
        "defensive_fix_candidates": [_candidate_to_dict(c) for c in candidates],
    }


# ---------------------------------------------------------------------------
# /defensive-fixes/apply
# ---------------------------------------------------------------------------


@router.post(
    "/defensive-fixes/apply",
    response_model=DefensiveFixApplyResponse,
    response_model_exclude_none=True,
)
def post_defensive_fixes_apply(req: DefensiveFixApplyRequest) -> dict:
    try:
        current_model_version, current_threshold_version = (
            _carry_forward_versions_for_request(
                run_id=req.run_id,
                round_id=req.round_id,
            )
        )
        outcome = apply_fix(
            defensive_fix_id=req.defensive_fix_id,
            outputs_root=OUTPUTS_ROOT,
            data_dir=DATA_DIR,
            current_model_version=current_model_version,
            current_threshold_version=current_threshold_version,
        )
    except MissingManifestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MissingBaselineModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MissingDatasetError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnknownThresholdVersionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "defensive_fix_id": outcome.defensive_fix_id,
        "applied": outcome.applied,
        "candidate_model_version": outcome.candidate_model_version,
        "candidate_threshold_version": outcome.candidate_threshold_version,
        "changed_files": list(outcome.changed_files),
        "judge_report_id": outcome.judge_report_id,
        "governance_rationale": outcome.governance_rationale,
    }
