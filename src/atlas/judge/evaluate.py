"""Phase 5 ``evaluate_fix`` driver.

Ties together holdouts (component 2) + metrics (component 3) + acceptance
(component 5) to produce a deterministic ``JudgeReport`` matching the
OpenAPI shape.

Flow:
  1. Resolve the two ``BaselineModelBundle``s (one per ``model_version``)
     and the two ``DecisionPolicyConfig``s (one per ``threshold_version``).
  2. For each evaluation set the caller wants — clean_holdout always,
     found_adaptive_set if event-ids supplied, locked + drifted always —
     load records, score under each side, and compute a
     ``MetricSnapshotValues``.
  3. Compute per-holdout pass flags using the simple
     "candidate doesn't make it worse" rule (Bible §16.7 "improves or
     stays neutral").
  4. Hand snapshots + pass flags to ``apply_acceptance_rule`` (component 5)
     for the global ``accepted_by_judge`` decision and ``judge_notes``.
  5. Round all surfaced metric floats to 4 decimals at the report-emit
     boundary so display precision never corrupts the §16.7 comparisons.

Headline-set convention:
  ``clean_holdout`` is the headline source for the report's ``baseline``
  and ``fixed`` ``MetricSnapshot``s — it's the operational synthetic
  population. Per-holdout pass flags surface each set's independent
  generalization check.

Caching:
  Process-local dicts keyed by version string. Bundles are loaded once
  per (process, version); same for configs. Tests can call
  ``reset_caches()`` to drop the cached entries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Sequence, TypedDict

from atlas.judge.acceptance import apply_acceptance_rule
from atlas.judge.holdouts import (
    HOLDOUT_NAMES,
    JudgeEvalRecord,
    load_eval_set,
)
from atlas.judge.metrics import (
    MetricSnapshotValues,
    metric_snapshot,
    score_eval_set,
    synthetic_loss_prevented,
)
from atlas.model.loader import DEFAULT_DATA_DIR
from atlas.model.policy import (
    DecisionPolicyConfig,
    UnknownThresholdVersionError,
    resolve_decision_policy_config,
)
from atlas.model.scorer import (
    BaselineModelBundle,
    MissingBaselineModelError,
    load_baseline_bundle,
)

# ---------------------------------------------------------------------------
# Public types — match OpenAPI JudgeReport / MetricSnapshot exactly
# ---------------------------------------------------------------------------


class MetricSnapshot(TypedDict, total=False):
    """OpenAPI ``MetricSnapshot``. Required keys are emitted on every call;
    optional keys are emitted when computable. ``synthetic_loss_prevented``
    is attached to the ``fixed`` side only — it's a baseline-vs-fixed
    diff, undefined for the baseline.
    """

    recall_at_fixed_action_rate: float
    false_positive_rate_at_fixed_action_rate: float
    model_miss_rate: float
    synthetic_loss_allowed: float
    synthetic_loss_prevented: float
    challenge_rate: float
    alert_rate: float
    decline_rate: float


class HoldoutGeneralization(TypedDict, total=False):
    """Per-holdout pass flags. ``found_adaptive_set_pass`` is omitted
    when the caller did not supply ``found_adaptive_set_event_ids``.
    """

    clean_holdout_pass: bool
    found_adaptive_set_pass: bool
    locked_adaptive_holdout_pass: bool
    drifted_holdout_pass: bool


class JudgeReport(TypedDict):
    """OpenAPI ``JudgeReport``. ``judge_report_id`` is derived
    deterministically from ``(run_id, round_id, defensive_fix_id)``.
    """

    judge_report_id: str
    run_id: str
    round_id: int
    defensive_fix_id: str
    accepted_by_judge: bool
    baseline: MetricSnapshot
    fixed: MetricSnapshot
    holdout_generalization: HoldoutGeneralization
    judge_notes: str


# ---------------------------------------------------------------------------
# Path conventions + caches
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUTS_ROOT: Final[Path] = REPO_ROOT / "outputs"
BASELINE_MODELS_ROOT: Final[Path] = REPO_ROOT / "outputs" / "baseline_models"

# Phase 7 candidate threshold versions land here. The Phase 5 judge
# resolves alternate ``threshold_version`` values to
# ``ALTERNATE_THRESHOLDS_ROOT / <version>.yaml`` — same shape as the
# persisted ``config/decision_thresholds.yaml`` so
# ``load_decision_policy_config`` handles it without changes.
ALTERNATE_THRESHOLDS_ROOT: Final[Path] = REPO_ROOT / "outputs" / "decision_thresholds"

# Float rounding precision at the report-emit boundary. Matches Phase 4's
# artifact convention (4dp in calibration.json + baseline_summary.json).
_REPORT_FLOAT_PRECISION: Final[int] = 4

_BUNDLE_CACHE: dict[str, BaselineModelBundle] = {}
_CONFIG_CACHE: dict[str, DecisionPolicyConfig] = {}


def reset_caches() -> None:
    """Test-only — drop cached bundles + configs so the next call reloads."""
    _BUNDLE_CACHE.clear()
    _CONFIG_CACHE.clear()


# ---------------------------------------------------------------------------
# Bundle + config resolution
# ---------------------------------------------------------------------------


def _bundle_for_version(
    model_version: str,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> BaselineModelBundle:
    """Load the trained baseline + calibration for ``model_version``.

    Convention: artifacts live at
    ``outputs/baseline_models/{model_version}/{model.joblib,calibration.json,feature_columns.json}``.
    Raises ``MissingBaselineModelError`` if the directory or required
    artifacts are missing — the route surfaces this as 503.
    """
    cache_key = f"{outputs_root.resolve()}|{model_version}"
    cached = _BUNDLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    local_dir = outputs_root / "baseline_models" / model_version
    out_dir = local_dir if local_dir.exists() else BASELINE_MODELS_ROOT / model_version
    bundle = load_baseline_bundle(out_dir)
    _BUNDLE_CACHE[cache_key] = bundle
    return bundle


def _config_for_version(
    threshold_version: str | None,
    *,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> DecisionPolicyConfig:
    """Resolve a ``DecisionPolicyConfig`` for the requested version."""
    cache_key = (
        f"{outputs_root.resolve()}|{ALTERNATE_THRESHOLDS_ROOT}|"
        f"{threshold_version or '__default__'}"
    )
    cached = _CONFIG_CACHE.get(cache_key)
    if cached is not None:
        return cached

    config = resolve_decision_policy_config(
        threshold_version,
        outputs_root=outputs_root,
        alternate_thresholds_root=ALTERNATE_THRESHOLDS_ROOT,
    )
    _CONFIG_CACHE[cache_key] = config
    return config


# ---------------------------------------------------------------------------
# Per-eval-set scoring
# ---------------------------------------------------------------------------


def _per_set_metrics(
    records: Sequence[JudgeEvalRecord],
    baseline_bundle: BaselineModelBundle,
    candidate_bundle: BaselineModelBundle,
    baseline_config: DecisionPolicyConfig,
    candidate_config: DecisionPolicyConfig,
) -> tuple[MetricSnapshotValues, MetricSnapshotValues]:
    """Score ``records`` under both sides; return ``(baseline, candidate)``."""
    baseline_scored = score_eval_set(records, baseline_bundle, baseline_config)
    candidate_scored = score_eval_set(records, candidate_bundle, candidate_config)
    return metric_snapshot(baseline_scored), metric_snapshot(candidate_scored)


def _holdout_pass(
    baseline: MetricSnapshotValues, fixed: MetricSnapshotValues
) -> bool:
    """Per-holdout generalization check.

    Bible §16.7's "locked adaptive holdout improves or stays neutral"
    rule, applied uniformly to every eval set: the candidate's
    ``model_miss_rate`` must be no worse than the baseline's.
    """
    return fixed["model_miss_rate"] <= baseline["model_miss_rate"]


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _round_floats(values: dict[str, float]) -> dict[str, float]:
    """Round every float in ``values`` to ``_REPORT_FLOAT_PRECISION``."""
    return {k: round(v, _REPORT_FLOAT_PRECISION) for k, v in values.items()}


def _build_metric_snapshot(
    raw: MetricSnapshotValues, *, prevented: float | None = None
) -> MetricSnapshot:
    """Round and shape a per-side ``MetricSnapshot`` for the report.

    ``prevented`` is attached as ``synthetic_loss_prevented`` only when
    provided (i.e. the ``fixed`` side).
    """
    rounded = _round_floats(dict(raw))
    snap: MetricSnapshot = MetricSnapshot(
        recall_at_fixed_action_rate=rounded["recall_at_fixed_action_rate"],
        false_positive_rate_at_fixed_action_rate=rounded[
            "false_positive_rate_at_fixed_action_rate"
        ],
        model_miss_rate=rounded["model_miss_rate"],
        synthetic_loss_allowed=rounded["synthetic_loss_allowed"],
        challenge_rate=rounded["challenge_rate"],
        alert_rate=rounded["alert_rate"],
        decline_rate=rounded["decline_rate"],
    )
    if prevented is not None:
        snap["synthetic_loss_prevented"] = round(prevented, _REPORT_FLOAT_PRECISION)
    return snap


def _judge_report_id(run_id: str, round_id: int, defensive_fix_id: str) -> str:
    return f"judge_{run_id}_{round_id}_{defensive_fix_id}"


def _build_acceptance_safety_scan_text(
    *,
    run_id: str,
    round_id: int,
    defensive_fix_id: str,
    baseline_model_version: str,
    candidate_model_version: str,
    baseline_threshold_version: str | None,
    candidate_threshold_version: str | None,
    found_adaptive_set_event_ids: Sequence[str] | None,
    baseline: MetricSnapshot,
    fixed: MetricSnapshot,
    holdout_generalization: HoldoutGeneralization,
) -> str:
    """Serialize judge-visible context for the acceptance safety gate.

    The payload intentionally includes request identifiers and emitted
    metrics, but never raw holdout records or labels. Sorted compact JSON
    keeps the scan input byte-stable while giving the canonical safety
    scanner a deterministic surface to inspect.
    """
    payload = {
        "run_id": run_id,
        "round_id": int(round_id),
        "defensive_fix_id": defensive_fix_id,
        "baseline_model_version": baseline_model_version,
        "candidate_model_version": candidate_model_version,
        "baseline_threshold_version": baseline_threshold_version,
        "candidate_threshold_version": candidate_threshold_version,
        "found_adaptive_set_event_ids": list(found_adaptive_set_event_ids or []),
        "baseline": dict(baseline),
        "fixed": dict(fixed),
        "holdout_generalization": dict(holdout_generalization),
    }
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_fix(
    *,
    run_id: str,
    round_id: int,
    defensive_fix_id: str,
    baseline_model_version: str,
    candidate_model_version: str,
    baseline_threshold_version: str | None = None,
    candidate_threshold_version: str | None = None,
    found_adaptive_set_event_ids: Sequence[str] | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
    outputs_root: Path = DEFAULT_OUTPUTS_ROOT,
) -> JudgeReport:
    """Evaluate a defensive fix by comparing baseline vs candidate.

    Returns a deterministic ``JudgeReport`` with all metric fields
    rounded to 4 decimals. Same inputs always produce a byte-identical
    response (the Phase 5 acceptance criterion).
    """
    baseline_bundle = _bundle_for_version(
        baseline_model_version, outputs_root=outputs_root
    )
    candidate_bundle = _bundle_for_version(
        candidate_model_version, outputs_root=outputs_root
    )
    baseline_config = _config_for_version(
        baseline_threshold_version, outputs_root=outputs_root
    )
    candidate_config = _config_for_version(
        candidate_threshold_version, outputs_root=outputs_root
    )

    # Per-eval-set snapshots. Headline (baseline / fixed) come from
    # clean_holdout; per-holdout pass flags surface each set's check.
    snapshots: dict[str, tuple[MetricSnapshotValues, MetricSnapshotValues]] = {}

    for name in HOLDOUT_NAMES:
        # found_adaptive_set is only evaluated when the caller supplied IDs.
        if name == "found_adaptive_set":
            if not found_adaptive_set_event_ids:
                continue
            records = load_eval_set(
                name,
                found_adaptive_set_event_ids=found_adaptive_set_event_ids,
                data_dir=data_dir,
            )
        else:
            records = load_eval_set(name, data_dir=data_dir)
        snapshots[name] = _per_set_metrics(
            records,
            baseline_bundle,
            candidate_bundle,
            baseline_config,
            candidate_config,
        )

    # Per-holdout pass flags (uniform "miss rate doesn't get worse" check).
    generalization: HoldoutGeneralization = HoldoutGeneralization(
        clean_holdout_pass=_holdout_pass(*snapshots["clean_holdout"]),
        locked_adaptive_holdout_pass=_holdout_pass(
            *snapshots["locked_adaptive_holdout"]
        ),
        drifted_holdout_pass=_holdout_pass(*snapshots["drifted_holdout"]),
    )
    if "found_adaptive_set" in snapshots:
        generalization["found_adaptive_set_pass"] = _holdout_pass(
            *snapshots["found_adaptive_set"]
        )

    # Headline = clean_holdout. Synthetic_loss_prevented is the diff.
    baseline_clean, fixed_clean = snapshots["clean_holdout"]
    prevented = synthetic_loss_prevented(
        baseline_clean["synthetic_loss_allowed"],
        fixed_clean["synthetic_loss_allowed"],
    )

    baseline_snapshot = _build_metric_snapshot(baseline_clean)
    fixed_snapshot = _build_metric_snapshot(fixed_clean, prevented=prevented)
    safety_scan_text = _build_acceptance_safety_scan_text(
        run_id=run_id,
        round_id=round_id,
        defensive_fix_id=defensive_fix_id,
        baseline_model_version=baseline_model_version,
        candidate_model_version=candidate_model_version,
        baseline_threshold_version=baseline_threshold_version,
        candidate_threshold_version=candidate_threshold_version,
        found_adaptive_set_event_ids=found_adaptive_set_event_ids,
        baseline=baseline_snapshot,
        fixed=fixed_snapshot,
        holdout_generalization=generalization,
    )

    # Component 5 owns the final acceptance + notes. It receives the
    # already-rounded headline snapshots + the per-holdout flags.
    accepted, judge_notes = apply_acceptance_rule(
        baseline=baseline_snapshot,
        fixed=fixed_snapshot,
        holdout_generalization=generalization,
        safety_scan_text=safety_scan_text,
    )

    return JudgeReport(
        judge_report_id=_judge_report_id(run_id, round_id, defensive_fix_id),
        run_id=run_id,
        round_id=round_id,
        defensive_fix_id=defensive_fix_id,
        accepted_by_judge=accepted,
        baseline=baseline_snapshot,
        fixed=fixed_snapshot,
        holdout_generalization=generalization,
        judge_notes=judge_notes,
    )


# Re-export ``MissingBaselineModelError`` so the route handler can catch
# it without needing a separate import from atlas.model.
__all__ = [
    "JudgeReport",
    "MetricSnapshot",
    "HoldoutGeneralization",
    "MissingBaselineModelError",
    "UnknownThresholdVersionError",
    "evaluate_fix",
    "reset_caches",
]
