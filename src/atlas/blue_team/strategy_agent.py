"""Phase 7 bank-strategy proposal selection.

``propose_fixes`` resolves requested ``model_vulnerability_id``s to the
internal records persisted by the Phase 7 ``POST /red-team/search`` flow,
intersects the allowed fix types three ways (request ∩ round_config ∩
card map), emits one ``DefensiveFixCandidate`` per surviving
(vulnerability, fix_type) pair, and persists one matching internal
``DefensiveFixManifest`` so component 7's ``apply_fix`` never has to
parse free-form prose.

Closed-enum text only:

  * ``description``     — per-(family, fix_type) template.
  * ``expected_benefit`` — single fixed shape parametrized by
                           ``family_id`` (already a closed-enum value).

No proposal logic looks at locked / drifted holdouts. Only the judge
reads holdouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Sequence

import yaml

from app.api.schemas.fix import ALLOWED_FIX_TYPES
from atlas.blue_team.manifest import (
    DEFAULT_OUTPUTS_ROOT,
    DefensiveFixManifest,
    ModelVulnerabilityRecord,
    load_vulnerability_record,
    make_defensive_fix_id,
    persist_fix_manifest,
)
from atlas.blue_team.feature_fix_agent import propose_feature_fix
from atlas.blue_team.model_calibration_fix_agent import propose_calibration_fix
from atlas.blue_team.policy_fix_agent import propose_policy_fix

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_ROUND_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "round_config.yaml"
DEFAULT_DECISION_THRESHOLDS_PATH: Final[Path] = (
    REPO_ROOT / "config" / "decision_thresholds.yaml"
)


# ---------------------------------------------------------------------------
# Public dataclass — mirrors the OpenAPI ``DefensiveFixCandidate`` shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DefensiveFixCandidate:
    """One public-safe defensive-fix candidate.

    Maps directly to ``app.api.schemas.fix.DefensiveFixCandidateSchema``.
    The route handler in component 8 converts dataclass → dict for the
    Pydantic response model.
    """

    defensive_fix_id: str
    round_id: int
    fix_type: str
    description: str
    files_changed: tuple[str, ...] = ()
    expected_benefit: str = ""
    rate_limit_claim: dict[str, float] = field(default_factory=dict)
    requires_judge_evaluation: bool = True


# ---------------------------------------------------------------------------
# Closed-enum text templates
#
# Bible §6.1: card summaries + fix descriptions are public-safe and come
# from fixed templates per (family_id, fix_type). The 11 entries below
# match the Phase 6 ``RECOMMENDED_FIX_TYPES_BY_FAMILY`` map exactly —
# every (family, fix_type) pair the strategy agent might emit has a
# template here.
# ---------------------------------------------------------------------------

DESCRIPTION_TEMPLATES: Final[dict[tuple[str, str], str]] = {
    ("low_velocity_high_graph_risk", "feature_fix"): (
        "Apply a synthetic feature transform that boosts the relationship "
        "graph risk signal at training time."
    ),
    ("low_velocity_high_graph_risk", "policy_fix"): (
        "Lower the synthetic challenge_score_threshold by a fixed delta "
        "to surface relationship-graph cohorts the baseline accepts."
    ),
    ("recent_change_feature_delay", "feature_fix"): (
        "Apply a synthetic feature transform that boosts recent security "
        "recovery and account access change signals at training time."
    ),
    ("score_boundary_cluster", "policy_fix"): (
        "Lower the synthetic challenge_score_threshold by a fixed delta "
        "to capture high-risk synthetic events clustered just below the "
        "current threshold."
    ),
    ("activity_channel_shift", "feature_fix"): (
        "Apply a synthetic feature transform that emphasizes geo "
        "consistency at training time."
    ),
    ("current_device_mismatch", "feature_fix"): (
        "Apply a synthetic feature transform that emphasizes current "
        "device tenure at training time."
    ),
    ("label_noise_mislearned", "model_calibration_fix"): (
        "Recalibrate the candidate model on synthetic data with a "
        "different training seed and a tighter L2 strength."
    ),
    ("overfit_fix_failure", "model_calibration_fix"): (
        "Recalibrate the candidate model on synthetic data with a "
        "different training seed and a looser L2 strength."
    ),
    ("overfit_fix_failure", "policy_fix"): (
        "Lower the synthetic challenge_score_threshold by a fixed delta "
        "as a complementary policy-only adjustment."
    ),
}

EXPECTED_BENEFIT_TEMPLATE: Final[str] = (
    "Reduces accepted high-risk synthetic events for the {family_id} "
    "cohort under the configured action-rate limit."
)


# ---------------------------------------------------------------------------
# Family-specific manifest builders — closed enums, deterministic
# ---------------------------------------------------------------------------

# Default rate_limit_claim for the public DefensiveFixCandidate. Pulled
# from ``config/decision_thresholds.yaml.customer_friction_tolerances``
# at proposal time so the surfaced numbers stay in sync with config.
_DEFAULT_RATE_LIMIT_CLAIM_KEYS: Final[tuple[str, ...]] = (
    "max_false_positive_rate_increase",
    "max_challenge_rate_increase",
)


# ---------------------------------------------------------------------------
# Round config + decision-threshold loaders
# ---------------------------------------------------------------------------


_ROUND_CONFIG_CACHE: dict[str, dict] = {}


def reset_caches() -> None:
    """Test-only — drop cached round-config + threshold reads."""
    _ROUND_CONFIG_CACHE.clear()


def _load_round_entry(round_id: int, path: Path) -> dict[str, Any]:
    cache_key = str(path)
    doc = _ROUND_CONFIG_CACHE.get(cache_key)
    if doc is None:
        if not path.exists():
            raise FileNotFoundError(
                f"round_config.yaml not found at {path}. "
                "Phase 7 strategy requires config/round_config.yaml to exist."
            )
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        _ROUND_CONFIG_CACHE[cache_key] = doc
    rounds = doc.get("rounds") or []
    for entry in rounds:
        if int(entry.get("round_id", -1)) == int(round_id):
            return entry
    available = [int(e.get("round_id", -1)) for e in rounds]
    raise ValueError(
        f"unknown round_id {round_id}; available in {path.name}: {available}"
    )


def _load_default_rate_limit_claim(
    path: Path = DEFAULT_DECISION_THRESHOLDS_PATH,
) -> dict[str, float]:
    """Read customer_friction_tolerances from
    ``config/decision_thresholds.yaml`` and project the two keys the
    OpenAPI ``rate_limit_claim`` exposes.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    friction = doc.get("customer_friction_tolerances") or {}
    return {
        k: float(friction.get(k, 0.0))
        for k in _DEFAULT_RATE_LIMIT_CLAIM_KEYS
        if k in friction
    }


def _load_baseline_challenge_threshold(
    path: Path = DEFAULT_DECISION_THRESHOLDS_PATH,
) -> float:
    if not path.exists():
        return 0.74  # Phase 4 default
    with path.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return float(
        (doc.get("decision_thresholds") or {}).get("challenge_score_threshold", 0.74)
    )


# ---------------------------------------------------------------------------
# Manifest builders per fix_type
# ---------------------------------------------------------------------------


def _build_policy_manifest(
    *,
    record: ModelVulnerabilityRecord,
    defensive_fix_id: str,
    run_id: str,
    rate_limit_claim: dict[str, float],
    baseline_challenge: float,
) -> DefensiveFixManifest:
    overrides = propose_policy_fix(
        family_id=record["family_id"],
        baseline_challenge_threshold=baseline_challenge,
    )
    return DefensiveFixManifest(
        defensive_fix_id=defensive_fix_id,
        run_id=run_id,
        round_id=record["round_id"],
        vulnerability_id=record["model_vulnerability_id"],
        fix_type="policy_fix",
        proposed_threshold_overrides=overrides,
        expected_rate_limit_claim=rate_limit_claim,
    )


def _build_calibration_manifest(
    *,
    record: ModelVulnerabilityRecord,
    defensive_fix_id: str,
    run_id: str,
    rate_limit_claim: dict[str, float],
) -> DefensiveFixManifest:
    seed_offset, l2 = propose_calibration_fix(family_id=record["family_id"])
    return DefensiveFixManifest(
        defensive_fix_id=defensive_fix_id,
        run_id=run_id,
        round_id=record["round_id"],
        vulnerability_id=record["model_vulnerability_id"],
        fix_type="model_calibration_fix",
        proposed_training_seed=seed_offset,
        proposed_l2_strength=l2,
        expected_rate_limit_claim=rate_limit_claim,
    )


def _build_feature_manifest(
    *,
    record: ModelVulnerabilityRecord,
    defensive_fix_id: str,
    run_id: str,
    rate_limit_claim: dict[str, float],
) -> DefensiveFixManifest:
    transforms = propose_feature_fix(family_id=record["family_id"])
    return DefensiveFixManifest(
        defensive_fix_id=defensive_fix_id,
        run_id=run_id,
        round_id=record["round_id"],
        vulnerability_id=record["model_vulnerability_id"],
        fix_type="feature_fix",
        proposed_feature_transforms=transforms,
        expected_rate_limit_claim=rate_limit_claim,
    )


_MANIFEST_BUILDERS = {
    "policy_fix": _build_policy_manifest,
    "model_calibration_fix": _build_calibration_manifest,
    "feature_fix": _build_feature_manifest,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def propose_fixes(
    *,
    run_id: str,
    round_id: int,
    model_vulnerability_ids: Sequence[str],
    allowed_fix_types: Sequence[str],
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    round_config_path: Path = DEFAULT_ROUND_CONFIG_PATH,
    decision_thresholds_path: Path = DEFAULT_DECISION_THRESHOLDS_PATH,
) -> list[DefensiveFixCandidate]:
    """Resolve vulnerabilities, intersect fix types, emit candidates.

    Three-way intersection per vulnerability:
        request.allowed_fix_types
          ∩ round_config.defensive_fix_types_allowed
          ∩ record.recommended_defensive_fix_types

    Empty intersection → no candidate for that (vulnerability) — not an
    error. Same inputs → byte-identical output (sorted by
    vulnerability_id then fix_type).
    """
    # Validate request fix types early
    request_fix_types = sorted(set(allowed_fix_types))
    unknown = [f for f in request_fix_types if f not in ALLOWED_FIX_TYPES]
    if unknown:
        raise ValueError(
            f"unknown fix_type(s) {unknown}; expected subset of "
            f"{list(ALLOWED_FIX_TYPES)}"
        )

    # Load round config (raises ValueError on unknown round)
    round_entry = _load_round_entry(round_id, round_config_path)
    round_allowed = set(round_entry.get("defensive_fix_types_allowed") or [])

    rate_limit_claim = _load_default_rate_limit_claim(decision_thresholds_path)
    baseline_challenge = _load_baseline_challenge_threshold(decision_thresholds_path)

    # Sort the requested vulnerabilities for byte-stability
    sorted_vuln_ids = sorted(set(model_vulnerability_ids))

    candidates: list[DefensiveFixCandidate] = []
    for vuln_id in sorted_vuln_ids:
        record = load_vulnerability_record(vuln_id, outputs_root=outputs_root)
        record_recommended = set(record["recommended_defensive_fix_types"])

        # Three-way intersection
        intersection = sorted(
            set(request_fix_types) & round_allowed & record_recommended
        )
        if not intersection:
            continue  # No candidate for this vulnerability — not an error

        for fix_type in intersection:
            defensive_fix_id = make_defensive_fix_id(
                round_id, vuln_id, fix_type
            )
            template_key = (record["family_id"], fix_type)
            description = DESCRIPTION_TEMPLATES.get(template_key)
            if description is None:
                # Defensive fallback — should never trigger because
                # RECOMMENDED_FIX_TYPES_BY_FAMILY constrains the inputs.
                description = (
                    f"Synthetic defensive-fix candidate for the "
                    f"{record['family_id']} family."
                )
            expected_benefit = EXPECTED_BENEFIT_TEMPLATE.format(
                family_id=record["family_id"]
            )

            builder = _MANIFEST_BUILDERS[fix_type]
            if fix_type == "policy_fix":
                manifest = builder(
                    record=record,
                    defensive_fix_id=defensive_fix_id,
                    run_id=run_id,
                    rate_limit_claim=rate_limit_claim,
                    baseline_challenge=baseline_challenge,
                )
            else:
                manifest = builder(
                    record=record,
                    defensive_fix_id=defensive_fix_id,
                    run_id=run_id,
                    rate_limit_claim=rate_limit_claim,
                )
            persist_fix_manifest(manifest, outputs_root=outputs_root)

            candidates.append(
                DefensiveFixCandidate(
                    defensive_fix_id=defensive_fix_id,
                    round_id=round_id,
                    fix_type=fix_type,
                    description=description,
                    files_changed=_files_changed_for(fix_type, defensive_fix_id),
                    expected_benefit=expected_benefit,
                    rate_limit_claim=dict(rate_limit_claim),
                    requires_judge_evaluation=True,
                )
            )

    return candidates


def _files_changed_for(fix_type: str, defensive_fix_id: str) -> tuple[str, ...]:
    """Deterministic relative paths the fix WILL touch when applied.

    Surface to the caller as a hint — the actual artifacts are written
    by component 7 ``apply_fix``.
    """
    if fix_type == "policy_fix":
        return (f"outputs/decision_thresholds/{defensive_fix_id}.yaml",)
    if fix_type in ("model_calibration_fix", "feature_fix"):
        return (
            f"outputs/baseline_models/{defensive_fix_id}/model.joblib",
            f"outputs/baseline_models/{defensive_fix_id}/calibration.json",
            f"outputs/baseline_models/{defensive_fix_id}/feature_columns.json",
            f"outputs/baseline_models/{defensive_fix_id}/baseline_summary.json",
        )
    return ()


__all__ = [
    "DEFAULT_DECISION_THRESHOLDS_PATH",
    "DEFAULT_ROUND_CONFIG_PATH",
    "DESCRIPTION_TEMPLATES",
    "DefensiveFixCandidate",
    "EXPECTED_BENEFIT_TEMPLATE",
    "propose_fixes",
    "reset_caches",
]
