"""Phase 7 policy-fix family.

Owns:

  * ``propose_policy_fix(record, baseline_challenge_threshold)`` —
    deterministic per-family ``challenge_score_threshold`` deltas.
    Returns the override dict the strategy agent embeds in the
    ``DefensiveFixManifest``.
  * ``apply_policy_fix(manifest, ...)`` — materializes a candidate
    decision-threshold YAML at
    ``outputs/decision_thresholds/<version>.yaml``. **Never mutates the
    persisted ``config/decision_thresholds.yaml``**. ``action_rate_limits``,
    ``customer_friction_tolerances``, ``decision_bands``, and
    ``allowed_reason_codes`` are copied verbatim from the baseline file —
    the proposal only touches the three score thresholds.

The candidate YAML uses the same shape as the persisted baseline so the
Phase 5 ``atlas.model.policy.load_decision_policy_config`` loader handles
it without changes. The Phase 5 judge's ``_config_for_version`` resolves
alternate versions to this directory (extended in component 4 below).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml

from atlas.blue_team.manifest import DEFAULT_OUTPUTS_ROOT, DefensiveFixManifest

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_DECISION_THRESHOLDS_PATH: Final[Path] = (
    REPO_ROOT / "config" / "decision_thresholds.yaml"
)
ALTERNATE_THRESHOLDS_SUBDIR: Final[str] = "decision_thresholds"


def alternate_thresholds_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    """Single source of truth for the candidate-threshold output dir.

    Imported by the Phase 5 judge in component 4 to resolve alternate
    threshold versions written here.
    """
    return outputs_root / ALTERNATE_THRESHOLDS_SUBDIR


# ---------------------------------------------------------------------------
# Per-family closed-enum proposal deltas
# ---------------------------------------------------------------------------


# Keep deltas small enough that the friction caps in
# ``config/decision_thresholds.yaml.customer_friction_tolerances`` stay
# at least nominally satisfiable for some round/dataset combinations —
# the judge enforces the actual acceptance ruling.
_POLICY_CHALLENGE_DELTA_BY_FAMILY: Final[dict[str, float]] = {
    "low_velocity_high_graph_risk": -0.05,
    "score_boundary_cluster":       -0.05,
    "overfit_fix_failure":          -0.03,
}


# ---------------------------------------------------------------------------
# Propose
# ---------------------------------------------------------------------------


def propose_policy_fix(
    *, family_id: str, baseline_challenge_threshold: float
) -> dict[str, float]:
    """Return the per-family ``challenge_score_threshold`` override.

    Pure function; closed enum on ``family_id``; deterministic.
    Returns ``{"challenge_score_threshold": new_value}`` clamped to
    ``[0, 1]`` and rounded to 4 decimals.
    """
    delta = _POLICY_CHALLENGE_DELTA_BY_FAMILY.get(family_id, -0.05)
    new_value = max(0.0, min(1.0, baseline_challenge_threshold + delta))
    return {"challenge_score_threshold": round(float(new_value), 4)}


# ---------------------------------------------------------------------------
# Apply — write versioned YAML
# ---------------------------------------------------------------------------


def apply_policy_fix(
    manifest: DefensiveFixManifest,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    baseline_thresholds_path: Path = DEFAULT_DECISION_THRESHOLDS_PATH,
) -> tuple[str, list[str]]:
    """Materialize a candidate decision-threshold YAML.

    Returns ``(candidate_threshold_version, [relative changed file paths])``.

    Behavior:
      * Reads the baseline ``config/decision_thresholds.yaml`` once
        (read-only).
      * Copies ``action_rate_limits``, ``customer_friction_tolerances``,
        ``decision_bands``, and ``allowed_reason_codes`` verbatim.
      * Replaces ``decision_threshold_version`` with the new version
        string (the manifest's ``defensive_fix_id``).
      * Replaces ``decision_thresholds.<key>`` for every key in
        ``manifest.proposed_threshold_overrides``; other entries
        (decline / alert / challenge that weren't overridden) are
        preserved from the baseline.
      * Writes the YAML to
        ``outputs/decision_thresholds/<version>.yaml`` with sorted keys
        for byte-stability.

    Raises:
        ValueError: ``manifest.fix_type != "policy_fix"`` or
                    ``proposed_threshold_overrides`` is empty.
        FileNotFoundError: baseline thresholds file is missing.
    """
    if manifest.fix_type != "policy_fix":
        raise ValueError(
            f"apply_policy_fix received fix_type {manifest.fix_type!r}; "
            "expected 'policy_fix'"
        )
    if not manifest.proposed_threshold_overrides:
        raise ValueError(
            f"manifest {manifest.defensive_fix_id} has no "
            "proposed_threshold_overrides — nothing to apply."
        )
    if not baseline_thresholds_path.exists():
        raise FileNotFoundError(
            f"baseline decision-thresholds config not found at "
            f"{baseline_thresholds_path}. Phase 7 policy-fix needs the "
            "baseline as the read-only template."
        )

    with baseline_thresholds_path.open("r", encoding="utf-8") as fh:
        baseline_doc = yaml.safe_load(fh) or {}

    candidate_version = manifest.defensive_fix_id

    # Build the candidate doc by COPYING the baseline. action_rate_limits,
    # customer_friction_tolerances, decision_bands, and
    # allowed_reason_codes carry over verbatim. Only the score thresholds
    # and the version string change.
    candidate_doc: dict = {}
    for key, value in baseline_doc.items():
        if key == "decision_threshold_version":
            candidate_doc[key] = candidate_version
        elif key == "decision_thresholds":
            new_thresholds = dict(value or {})
            for override_key, override_value in manifest.proposed_threshold_overrides.items():
                new_thresholds[override_key] = float(override_value)
            candidate_doc[key] = new_thresholds
        else:
            # action_rate_limits, customer_friction_tolerances,
            # decision_bands, allowed_reason_codes, …
            candidate_doc[key] = value

    out_path = alternate_thresholds_dir(outputs_root) / f"{candidate_version}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            candidate_doc, fh, sort_keys=True, default_flow_style=False
        )

    # Surface relative path for the public ``changed_files`` field.
    rel_path = (
        f"outputs/{ALTERNATE_THRESHOLDS_SUBDIR}/{candidate_version}.yaml"
    )
    return candidate_version, [rel_path]


__all__ = [
    "ALTERNATE_THRESHOLDS_SUBDIR",
    "DEFAULT_DECISION_THRESHOLDS_PATH",
    "alternate_thresholds_dir",
    "apply_policy_fix",
    "propose_policy_fix",
]
