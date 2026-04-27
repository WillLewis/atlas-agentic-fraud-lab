"""Pydantic schemas for ``POST /defensive-fixes/propose`` and
``POST /defensive-fixes/apply`` (Phase 7).

Mirrors the OpenAPI ``DefensiveFix*`` shapes (lines 951–1033 of
``project_atlas_openapi.yaml``). All request schemas use
``extra="forbid"`` so a client-supplied ``description`` (or any other
free-form override) is rejected at the boundary — Bible §13.3 +
§18 Phase 7 acceptance: agent text cannot drive judge or governance
output.

``DefensiveFixApplyResponse.applied`` semantics (documented contract):

  * ``applied=True``  — candidate was materialized AND judge-accepted
                       (i.e. ``JudgeReport.accepted_by_judge == True``).
  * ``applied=False`` — candidate was materialized but judge-rejected.
                       Artifacts may still exist on disk under
                       ``outputs/baseline_models/<v>/`` and/or
                       ``outputs/decision_thresholds/<v>.yaml``.

The OpenAPI schema lists ``applied`` as just ``boolean``; the semantics
above live in this docstring + the Phase 7 tests.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Allowed Phase 7 fix-type enum. Matches OpenAPI
# ``DefensiveFixCandidate.fix_type.enum`` (lines 988–989).
ALLOWED_FIX_TYPES: tuple[str, ...] = (
    "feature_fix",
    "policy_fix",
    "model_calibration_fix",
)


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


class DefensiveFixProposalRequest(_StrictModel):
    run_id: str
    round_id: int
    model_vulnerability_ids: list[str] = Field(min_length=1)
    allowed_fix_types: list[str] = Field(min_length=1)


class RateLimitClaimSchema(_StrictModel):
    max_false_positive_rate_increase: float | None = None
    max_challenge_rate_increase: float | None = None


class DefensiveFixCandidateSchema(_StrictModel):
    """Public, summary-shaped candidate. Structured apply parameters live
    in the internal ``DefensiveFixManifest`` (component 2), not here.
    """

    defensive_fix_id: str
    round_id: int
    fix_type: str = Field(pattern="^(feature_fix|policy_fix|model_calibration_fix)$")
    description: str
    files_changed: list[str] | None = None
    expected_benefit: str | None = None
    rate_limit_claim: RateLimitClaimSchema | None = None
    requires_judge_evaluation: bool


class DefensiveFixProposalResponse(_StrictModel):
    run_id: str
    round_id: int
    defensive_fix_candidates: list[DefensiveFixCandidateSchema]


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


class DefensiveFixApplyRequest(_StrictModel):
    run_id: str
    round_id: int
    defensive_fix_id: str


class DefensiveFixApplyResponse(_StrictModel):
    """See module docstring for ``applied`` semantics.

    The OpenAPI shape (lines 1018–1033) lists 5 fields. Phase 7 adds two
    optional fields surfaced by the route for visibility — they don't
    yet appear in the public spec; OpenAPI reconciliation deferred to
    Phase 8 when the ledger surfaces these uniformly.

      * ``judge_report_id``       — points at the persisted judge
                                    report under
                                    ``outputs/reports/<id>.json``.
      * ``governance_rationale``  — brief, deterministic, public-safe
                                    rationale from
                                    ``atlas.blue_team.governance_agent``.
                                    NEVER overrides judge metrics.
    """

    defensive_fix_id: str
    applied: bool
    candidate_model_version: str | None = None
    candidate_threshold_version: str | None = None
    changed_files: list[str] | None = None
    judge_report_id: str | None = None
    governance_rationale: str | None = None
