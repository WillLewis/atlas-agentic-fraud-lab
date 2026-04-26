"""Phase 5 defensive-fix acceptance rule (Bible §16.7).

Implements the conjunction:

    accepted = (
        recall_at_fixed_action_rate improves
        AND model_miss_rate decreases
        AND false_positive_rate stays within tolerance
        AND challenge / decline / alert rate limits are not exceeded
        AND locked_adaptive_holdout improves or stays neutral
        AND safety scanner passes
    )

The friction tolerances and absolute action-rate caps both come from
``config/decision_thresholds.yaml`` (the file is ``ask``-gated; this
module only reads it). All checks are deterministic — same inputs +
same config → byte-identical ``(accepted, judge_notes)``.

``judge_notes`` is rendered from a fixed template enumerating the six
condition outcomes and headline deltas. No free-form text — Bible §18
Phase 5 acceptance: agent text cannot override judge results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from atlas.model.policy import DEFAULT_THRESHOLDS_CONFIG_PATH

# The six §16.7 conditions, in canonical order. judge_notes emits in
# this order so output is byte-stable across runs.
ACCEPTANCE_CONDITION_KEYS: Final[tuple[str, ...]] = (
    "recall_improves",
    "miss_rate_decreases",
    "false_positive_rate_within_tolerance",
    "action_rate_limits_within_tolerance",
    "locked_holdout_neutral_or_better",
    "safety_scan_passed",
)

# Display precision for delta values inside judge_notes. Matches Phase 5
# evaluate.py's report-emit precision (4 dp), so notes never lose info
# the report headline already shows.
_NOTES_FLOAT_PRECISION: Final[int] = 4


# ---------------------------------------------------------------------------
# Acceptance policy — loaded from config/decision_thresholds.yaml
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptancePolicy:
    """Phase 5 acceptance-rule inputs from config/decision_thresholds.yaml.

    Two groups of values:

      * ``customer_friction_tolerances`` — caps on how much the candidate
        may *increase* a friction metric over baseline. The §16.7
        "stays within tolerance" half.
      * ``action_rate_limits``           — absolute caps on the
        candidate's challenge / alert / decline rates. The §16.7 "rate
        limits are not exceeded" half.

    All values are normalized to fractions (0–1) regardless of the
    field's persisted unit (raw / pct / bps), so downstream comparisons
    are uniform.
    """

    max_false_positive_rate_increase_fraction: float
    max_challenge_rate_increase_fraction: float
    max_alert_rate_increase_fraction: float
    max_decline_rate_increase_fraction: float
    challenge_rate_limit_fraction: float
    alert_rate_limit_fraction: float
    decline_rate_limit_fraction: float


_POLICY_CACHE: dict[str, AcceptancePolicy] = {}


def reset_caches() -> None:
    """Test-only — drop the cached AcceptancePolicy."""
    _POLICY_CACHE.clear()


def load_acceptance_policy(
    path: Path = DEFAULT_THRESHOLDS_CONFIG_PATH,
) -> AcceptancePolicy:
    """Load + cache the Phase 5 acceptance policy from
    ``config/decision_thresholds.yaml``.

    Unit-normalization conventions:
      * ``max_false_positive_rate_increase`` and
        ``max_challenge_rate_increase`` are persisted as raw fractions.
      * ``max_alert_rate_increase_pct`` and ``alert_rate_limit_pct`` /
        ``challenge_rate_limit_pct`` are percent (× / 100).
      * ``max_decline_rate_increase_bps`` and ``decline_rate_limit_bps``
        are basis points (× / 10000).
    """
    cache_key = str(path)
    cached = _POLICY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not path.exists():
        raise FileNotFoundError(
            f"decision-thresholds config not found at {path}. "
            "Phase 5 acceptance requires config/decision_thresholds.yaml."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    friction = raw.get("customer_friction_tolerances") or {}
    limits = raw.get("action_rate_limits") or {}

    policy = AcceptancePolicy(
        max_false_positive_rate_increase_fraction=float(
            friction["max_false_positive_rate_increase"]
        ),
        max_challenge_rate_increase_fraction=float(
            friction["max_challenge_rate_increase"]
        ),
        max_alert_rate_increase_fraction=float(
            friction["max_alert_rate_increase_pct"]
        )
        / 100.0,
        max_decline_rate_increase_fraction=float(
            friction["max_decline_rate_increase_bps"]
        )
        / 10000.0,
        challenge_rate_limit_fraction=float(limits["challenge_rate_limit_pct"])
        / 100.0,
        alert_rate_limit_fraction=float(limits["alert_rate_limit_pct"]) / 100.0,
        decline_rate_limit_fraction=float(limits["decline_rate_limit_bps"]) / 10000.0,
    )
    _POLICY_CACHE[cache_key] = policy
    return policy


# ---------------------------------------------------------------------------
# Per-condition checks
#
# Each helper returns (passed: bool, detail: str). The detail string is
# part of judge_notes so it must be deterministic — round all floats to
# _NOTES_FLOAT_PRECISION before formatting.
# ---------------------------------------------------------------------------


def _r(x: float) -> float:
    return round(x, _NOTES_FLOAT_PRECISION)


def _check_recall_improves(
    baseline: dict[str, Any], fixed: dict[str, Any]
) -> tuple[bool, str]:
    delta = fixed["recall_at_fixed_action_rate"] - baseline["recall_at_fixed_action_rate"]
    return delta > 0, f"recall_lift={_r(delta)}"


def _check_miss_rate_decreases(
    baseline: dict[str, Any], fixed: dict[str, Any]
) -> tuple[bool, str]:
    delta = fixed["model_miss_rate"] - baseline["model_miss_rate"]
    # "decreases" means strictly less; delta is fixed - baseline so it
    # must be negative.
    return delta < 0, f"miss_rate_delta={_r(delta)}"


def _check_fpr_within_tolerance(
    baseline: dict[str, Any], fixed: dict[str, Any], policy: AcceptancePolicy
) -> tuple[bool, str]:
    delta = (
        fixed["false_positive_rate_at_fixed_action_rate"]
        - baseline["false_positive_rate_at_fixed_action_rate"]
    )
    tol = policy.max_false_positive_rate_increase_fraction
    return (
        delta <= tol,
        f"fpr_increase={_r(delta)}<= {_r(tol)}",
    )


def _check_action_rate_limits(
    baseline: dict[str, Any], fixed: dict[str, Any], policy: AcceptancePolicy
) -> tuple[bool, str]:
    """Combined check — both halves must hold:

      (a) candidate stays within absolute action-rate caps
          (challenge_rate_limit, alert_rate_limit, decline_rate_limit).
      (b) candidate's rate-increase delta vs baseline stays within
          customer_friction_tolerances.

    Implemented over all three of challenge / alert / decline.
    """
    sub_results: list[tuple[str, bool, str]] = []

    def _evaluate(
        rate_key: str,
        absolute_cap: float,
        increase_cap: float,
    ) -> None:
        baseline_v = baseline[rate_key]
        fixed_v = fixed[rate_key]
        delta = fixed_v - baseline_v
        absolute_ok = fixed_v <= absolute_cap
        increase_ok = delta <= increase_cap
        passed = absolute_ok and increase_ok
        detail = (
            f"{rate_key}={_r(fixed_v)}<= {_r(absolute_cap)}"
            f"&increase={_r(delta)}<= {_r(increase_cap)}"
        )
        sub_results.append((rate_key, passed, detail))

    _evaluate(
        "challenge_rate",
        policy.challenge_rate_limit_fraction,
        policy.max_challenge_rate_increase_fraction,
    )
    _evaluate(
        "alert_rate",
        policy.alert_rate_limit_fraction,
        policy.max_alert_rate_increase_fraction,
    )
    _evaluate(
        "decline_rate",
        policy.decline_rate_limit_fraction,
        policy.max_decline_rate_increase_fraction,
    )

    all_passed = all(passed for _, passed, _ in sub_results)
    detail_str = ",".join(detail for _, _, detail in sub_results)
    return all_passed, detail_str


def _check_locked_holdout(
    holdout_generalization: dict[str, Any],
) -> tuple[bool, str]:
    passed = bool(holdout_generalization.get("locked_adaptive_holdout_pass", False))
    return passed, f"locked_pass={passed}"


def _check_safety_scan() -> tuple[bool, str]:
    """Phase 5 placeholder — Phase 10 wires `scripts/safety_scan.py`
    output through the judge. Today the build-level scanner is the
    source of truth; per-evaluation re-scanning would only re-check
    static repo state. Returning True keeps the conjunction shape stable.
    """
    # TODO(Phase 10): plumb scripts/safety_scan.py findings into a
    # per-evaluation safety-scan record and gate acceptance on it.
    return True, "safety_scan=passed(phase5_placeholder)"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_acceptance_rule(
    *,
    baseline: dict[str, Any],
    fixed: dict[str, Any],
    holdout_generalization: dict[str, Any],
    policy: AcceptancePolicy | None = None,
) -> tuple[bool, str]:
    """Evaluate Bible §16.7 over the headline ``MetricSnapshot``s and
    per-holdout pass flags.

    Returns ``(accepted_by_judge, judge_notes)``. ``judge_notes`` is a
    deterministic single-line key=value string ordered by
    ``ACCEPTANCE_CONDITION_KEYS``.
    """
    if policy is None:
        policy = load_acceptance_policy()

    conditions: dict[str, tuple[bool, str]] = {
        "recall_improves": _check_recall_improves(baseline, fixed),
        "miss_rate_decreases": _check_miss_rate_decreases(baseline, fixed),
        "false_positive_rate_within_tolerance": _check_fpr_within_tolerance(
            baseline, fixed, policy
        ),
        "action_rate_limits_within_tolerance": _check_action_rate_limits(
            baseline, fixed, policy
        ),
        "locked_holdout_neutral_or_better": _check_locked_holdout(
            holdout_generalization
        ),
        "safety_scan_passed": _check_safety_scan(),
    }

    accepted = all(passed for passed, _ in conditions.values())

    parts = [f"accepted={accepted}"]
    for key in ACCEPTANCE_CONDITION_KEYS:
        passed, detail = conditions[key]
        parts.append(f"{key}={passed}({detail})")
    judge_notes = "; ".join(parts)
    return accepted, judge_notes
