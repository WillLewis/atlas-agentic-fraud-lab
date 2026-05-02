"""Phase 7 fix-applier orchestration.

``apply_fix`` is the single entry point for materializing a defensive
fix candidate, evaluating it via the Phase 5 judge in-process, and
returning the visible-rejection-aware outcome.

Flow:

  1. ``manifest = load_fix_manifest(defensive_fix_id)``.
  2. Dispatch on ``manifest.fix_type`` to one of:
       ``policy_fix``           → ``apply_policy_fix``
       ``model_calibration_fix`` → ``apply_calibration_fix``
       ``feature_fix``          → ``apply_feature_fix``
  3. Get back ``(candidate_model_version, candidate_threshold_version,
     changed_files)``.
  4. Call ``atlas.judge.evaluate.evaluate_fix(...)`` directly (in-
     process; no HTTP self-call).
  5. Persist the judge report to
     ``outputs/reports/<judge_report_id>.json``.
  6. Format a deterministic public-safe governance rationale from the
     report + manifest.
  7. Return ``FixApplyOutcome`` with ``applied = report.accepted_by_judge``.

``applied=true`` ⇔ judge accepted. ``applied=false`` ⇔ judge rejected.
**Artifacts are persisted in BOTH cases** — the candidate model /
threshold YAML / report stays on disk regardless. Only the boolean
flips. This is the "visible rejection" Phase 7 acceptance criterion:
the rejected candidate is durable and the governance rationale points
at the failed §16.7 condition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from atlas.blue_team.feature_fix_agent import apply_feature_fix
from atlas.blue_team.governance_agent import format_decision
from atlas.blue_team.manifest import (
    DEFAULT_OUTPUTS_ROOT,
    DefensiveFixManifest,
    load_fix_manifest,
)
from atlas.blue_team.model_calibration_fix_agent import apply_calibration_fix
from atlas.blue_team.policy_fix_agent import apply_policy_fix
from atlas.judge.evaluate import evaluate_fix
from atlas.model.loader import DEFAULT_DATA_DIR

# ---------------------------------------------------------------------------
# Path conventions
# ---------------------------------------------------------------------------

JUDGE_REPORTS_SUBDIR: Final[str] = "reports"

# Phase 4/5 baseline identities — used as the "left side" of the judge
# comparison when the candidate is a policy_fix or feature_fix that
# doesn't override the model version, etc.
_BASELINE_MODEL_VERSION: Final[str] = "baseline_v1"
_BASELINE_THRESHOLD_VERSION: Final[str] = "thresholds_v1"


def reports_dir(outputs_root: Path = DEFAULT_OUTPUTS_ROOT) -> Path:
    return outputs_root / JUDGE_REPORTS_SUBDIR


# ---------------------------------------------------------------------------
# Public outcome dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixApplyOutcome:
    """Result of one ``apply_fix`` call.

    Maps to ``app.api.schemas.fix.DefensiveFixApplyResponse``. Includes
    Phase 7-only fields (``judge_report_id``, ``governance_rationale``)
    on top of the OpenAPI shape — both optional.
    """

    defensive_fix_id: str
    applied: bool
    candidate_model_version: str
    candidate_threshold_version: str
    changed_files: list[str]
    judge_report_id: str
    governance_rationale: str


# ---------------------------------------------------------------------------
# Internal: family dispatch
# ---------------------------------------------------------------------------


def _materialize_candidate(
    *,
    manifest: DefensiveFixManifest,
    outputs_root: Path,
    data_dir: Path,
) -> tuple[str, str, list[str]]:
    """Apply the family-specific changes and return
    ``(candidate_model_version, candidate_threshold_version, changed_files)``.

    Conventions:
      * ``policy_fix``           → candidate threshold version =
                                  ``manifest.defensive_fix_id``;
                                  model version stays at ``baseline_v1``.
      * ``model_calibration_fix`` → candidate model version =
                                   ``manifest.defensive_fix_id``;
                                   threshold version stays at
                                   ``thresholds_v1``.
      * ``feature_fix``          → candidate model version =
                                   ``manifest.defensive_fix_id``;
                                   threshold version stays at
                                   ``thresholds_v1``.
    """
    if manifest.fix_type == "policy_fix":
        candidate_threshold_version, changed_files = apply_policy_fix(
            manifest, outputs_root=outputs_root
        )
        return _BASELINE_MODEL_VERSION, candidate_threshold_version, changed_files

    if manifest.fix_type == "model_calibration_fix":
        candidate_model_version, changed_files = apply_calibration_fix(
            manifest, outputs_root=outputs_root, data_dir=data_dir
        )
        return candidate_model_version, _BASELINE_THRESHOLD_VERSION, changed_files

    if manifest.fix_type == "feature_fix":
        candidate_model_version, changed_files = apply_feature_fix(
            manifest, outputs_root=outputs_root, data_dir=data_dir
        )
        return candidate_model_version, _BASELINE_THRESHOLD_VERSION, changed_files

    raise ValueError(
        f"unknown manifest.fix_type {manifest.fix_type!r}; "
        f"expected one of (policy_fix, model_calibration_fix, feature_fix)"
    )


# ---------------------------------------------------------------------------
# Persist judge report
# ---------------------------------------------------------------------------


def _persist_judge_report(
    report: dict[str, Any], outputs_root: Path
) -> Path:
    """Write the judge report to
    ``outputs/reports/<judge_report_id>.json``. Sorted-key JSON for
    byte-stability.
    """
    rid = report["judge_report_id"]
    path = reports_dir(outputs_root) / f"{rid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_fix(
    *,
    defensive_fix_id: str,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
    data_dir: Path = DEFAULT_DATA_DIR,
    current_model_version: str | None = None,
    current_threshold_version: str | None = None,
    found_adaptive_set_event_ids: list[str] | None = None,
) -> FixApplyOutcome:
    """Apply the manifest, run the judge in-process, format governance.

    Phase 8 round-state extension (non-breaking — defaults preserve
    Phase 7 behavior):

      * ``current_model_version`` / ``current_threshold_version`` —
        when the round engine carries forward an accepted fix from a
        previous round, these are the round-state's accepted versions.
        The judge compares the candidate against these instead of the
        hard-coded ``baseline_v1`` / ``thresholds_v1``. ``None`` falls
        back to the Phase 7 defaults.
      * ``found_adaptive_set_event_ids`` — Phase 6 search output for
        the current round. The judge already accepts this kwarg
        (``atlas.judge.evaluate.evaluate_fix``) and will evaluate the
        ``found_adaptive_set`` holdout if non-empty. ``None`` falls
        back to Phase 7 (judge skips that holdout).

    Raises:
        MissingManifestError: ``defensive_fix_id`` has no manifest on disk.
        MissingBaselineModelError / MissingDatasetError: propagated from
            the family applier or the judge.
        ValueError: family dispatch failure or invalid manifest contents.
    """
    manifest = load_fix_manifest(defensive_fix_id, outputs_root=outputs_root)

    candidate_model_version, candidate_threshold_version, changed_files = (
        _materialize_candidate(
            manifest=manifest,
            outputs_root=outputs_root,
            data_dir=data_dir,
        )
    )

    # Phase 8: round-state baseline versions, fall through to Phase 7
    # constants when the kwargs are None.
    baseline_model_version = (
        current_model_version
        if current_model_version is not None
        else _BASELINE_MODEL_VERSION
    )
    baseline_threshold_version = (
        current_threshold_version
        if current_threshold_version is not None
        else _BASELINE_THRESHOLD_VERSION
    )

    # Run the judge in-process.
    report = evaluate_fix(
        run_id=manifest.run_id,
        round_id=manifest.round_id,
        defensive_fix_id=manifest.defensive_fix_id,
        baseline_model_version=baseline_model_version,
        candidate_model_version=candidate_model_version,
        baseline_threshold_version=baseline_threshold_version,
        candidate_threshold_version=candidate_threshold_version,
        found_adaptive_set_event_ids=(
            list(found_adaptive_set_event_ids)
            if found_adaptive_set_event_ids
            else None
        ),
        data_dir=data_dir,
        outputs_root=outputs_root,
    )

    _persist_judge_report(report, outputs_root)

    governance_rationale = format_decision(
        judge_report=report, manifest=manifest
    )

    return FixApplyOutcome(
        defensive_fix_id=manifest.defensive_fix_id,
        applied=bool(report["accepted_by_judge"]),
        candidate_model_version=candidate_model_version,
        candidate_threshold_version=candidate_threshold_version,
        changed_files=list(changed_files),
        judge_report_id=str(report["judge_report_id"]),
        governance_rationale=governance_rationale,
    )


__all__ = [
    "FixApplyOutcome",
    "JUDGE_REPORTS_SUBDIR",
    "apply_fix",
    "reports_dir",
]
