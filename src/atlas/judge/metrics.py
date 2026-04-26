"""Phase 5 judge-owned metric primitives.

Pure functions over ``ScoredEvalRecord``s — labeled feature vectors that
have already been scored by the Phase 4 baseline + policy pipeline.

All metrics are deterministic. No randomness, no rounding inside the
math; rounding to 4 decimals happens at the report-emit boundary in
``atlas.judge.evaluate`` so that intermediate comparisons (e.g. "miss
rate decreases") are not corrupted by display precision.

Bible §16 is the source of truth for the formulas; this module is the
single canonical implementation.
"""

from __future__ import annotations

from typing import Final, Sequence, TypedDict

from atlas.judge.holdouts import JudgeEvalRecord
from atlas.model.policy import DecisionPolicyConfig, apply_decision_policy
from atlas.model.scorer import BaselineModelBundle, score_features
from atlas.synthetic.features import FeatureVector

# ---------------------------------------------------------------------------
# Synthetic-loss mapping (demo constants, NOT real-money amounts)
#
# Bible §16.6 defines synthetic_loss_allowed as the sum of "amount for
# accepted high_risk_synthetic_activity events", but persisted transfer
# events store amount_bucket strings, not numerical amounts. This map is
# the single canonical translation. The values are illustrative synthetic
# demo constants; no real-money realism is implied.
# ---------------------------------------------------------------------------

AMOUNT_BUCKET_TO_SYNTHETIC_LOSS: Final[dict[str, int]] = {
    "amount_bucket_01": 500,
    "amount_bucket_02": 1500,
    "amount_bucket_03": 4000,
    "amount_bucket_04": 9000,
    "amount_bucket_05": 18000,
    "amount_bucket_06": 35000,
    "amount_bucket_07": 65000,
    "amount_bucket_08": 120000,
    "amount_bucket_09": 250000,
    "amount_bucket_10": 500000,
}


# ---------------------------------------------------------------------------
# Scored-record shape (what every metric function consumes)
# ---------------------------------------------------------------------------


class ScoredEvalRecord(TypedDict):
    """A ``JudgeEvalRecord`` after the Phase 4 scorer + policy run."""

    event_id: str
    customer_id: str
    feature_vector: FeatureVector
    synthetic_truth_label: str
    binary_label: int
    amount_bucket: str
    score: float
    decision_action: str


def score_eval_set(
    records: Sequence[JudgeEvalRecord],
    bundle: BaselineModelBundle,
    config: DecisionPolicyConfig,
) -> list[ScoredEvalRecord]:
    """Run Phase 4's scorer + policy over an eval set.

    The resulting list is the canonical input to every metric function in
    this module. Order matches ``records`` so byte-stability is preserved
    across runs.
    """
    out: list[ScoredEvalRecord] = []
    for r in records:
        s = score_features(r["feature_vector"], bundle)
        decision = apply_decision_policy(s, r["feature_vector"], config)
        out.append(
            ScoredEvalRecord(
                event_id=r["event_id"],
                customer_id=r["customer_id"],
                feature_vector=r["feature_vector"],
                synthetic_truth_label=r["synthetic_truth_label"],
                binary_label=r["binary_label"],
                amount_bucket=r["amount_bucket"],
                score=s,
                decision_action=decision.decision_action,
            )
        )
    return out


# ---------------------------------------------------------------------------
# §16.1 — model_miss_rate
# §16.3 — recall_at_fixed_action_rate
# §16.5 — false_positive_rate, challenge_rate, alert_rate, decline_rate
# §16.6 — synthetic_loss_allowed, synthetic_loss_prevented
#
# Empty-input convention: every function returns 0.0 on an empty filter.
# This keeps the §16.7 "decreases-or-stays-neutral" comparisons stable
# when an eval set has no high-risk or no normal events. The aggregator
# preserves this so a sparsely-populated holdout doesn't crash the judge.
# ---------------------------------------------------------------------------


def model_miss_rate(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.1 — accepted_high_risk_events / valid_high_risk_events_tested."""
    high_risk = [r for r in scored if r["binary_label"] == 1]
    if not high_risk:
        return 0.0
    accepted = sum(1 for r in high_risk if r["decision_action"] == "accept")
    return accepted / len(high_risk)


def recall_at_fixed_action_rate(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.3 — high_risk_events_caught_at_limit / total_high_risk_events.

    "Caught" = any non-accept action under the candidate's decision policy
    (challenge / alert / decline). The decision policy already encodes the
    fixed action-rate limits via thresholds in
    ``config/decision_thresholds.yaml``; the judge does not re-derive a
    cutoff from scores.

    Invariant: ``recall_at_fixed_action_rate(s) + model_miss_rate(s) == 1.0``
    when at least one high-risk event is present.
    """
    high_risk = [r for r in scored if r["binary_label"] == 1]
    if not high_risk:
        return 0.0
    caught = sum(1 for r in high_risk if r["decision_action"] != "accept")
    return caught / len(high_risk)


def false_positive_rate_at_fixed_action_rate(
    scored: Sequence[ScoredEvalRecord],
) -> float:
    """§16.5 — normal_events_not_accepted / total_normal_events."""
    normal = [r for r in scored if r["binary_label"] == 0]
    if not normal:
        return 0.0
    fp = sum(1 for r in normal if r["decision_action"] != "accept")
    return fp / len(normal)


def _action_rate(scored: Sequence[ScoredEvalRecord], action: str) -> float:
    if not scored:
        return 0.0
    hits = sum(1 for r in scored if r["decision_action"] == action)
    return hits / len(scored)


def challenge_rate(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.5 — fraction of all events landing in the challenge band."""
    return _action_rate(scored, "challenge")


def alert_rate(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.5 — fraction of all events landing in the alert band."""
    return _action_rate(scored, "alert")


def decline_rate(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.5 — fraction of all events landing in the decline band."""
    return _action_rate(scored, "decline")


def synthetic_loss_allowed(scored: Sequence[ScoredEvalRecord]) -> float:
    """§16.6 — sum of ``AMOUNT_BUCKET_TO_SYNTHETIC_LOSS[bucket]`` over
    accepted high-risk events. Returns a float for arithmetic with
    ``synthetic_loss_prevented``.
    """
    total = 0
    for r in scored:
        if r["binary_label"] == 1 and r["decision_action"] == "accept":
            total += AMOUNT_BUCKET_TO_SYNTHETIC_LOSS[r["amount_bucket"]]
    return float(total)


def synthetic_loss_prevented(
    baseline_loss_allowed: float, fixed_loss_allowed: float
) -> float:
    """§16.6 — baseline_synthetic_loss_allowed - fixed_synthetic_loss_allowed."""
    return float(baseline_loss_allowed) - float(fixed_loss_allowed)


# ---------------------------------------------------------------------------
# Aggregator — fills the eight-field MetricSnapshot in one pass
# ---------------------------------------------------------------------------


class MetricSnapshotValues(TypedDict):
    """Internal — the eight floats the judge surfaces per side.

    Mirrors the OpenAPI ``MetricSnapshot`` schema. Component 4
    (``evaluate_fix``) attaches ``synthetic_loss_prevented`` to the
    ``fixed`` snapshot only (it's a baseline-vs-fixed diff, undefined for
    the baseline side).
    """

    recall_at_fixed_action_rate: float
    false_positive_rate_at_fixed_action_rate: float
    model_miss_rate: float
    synthetic_loss_allowed: float
    challenge_rate: float
    alert_rate: float
    decline_rate: float


def metric_snapshot(scored: Sequence[ScoredEvalRecord]) -> MetricSnapshotValues:
    """Compute all seven per-side metrics in one pass.

    ``synthetic_loss_prevented`` is intentionally NOT in this dict — it's
    a baseline-vs-fixed difference, computed by the caller after both
    snapshots exist.
    """
    return MetricSnapshotValues(
        recall_at_fixed_action_rate=recall_at_fixed_action_rate(scored),
        false_positive_rate_at_fixed_action_rate=false_positive_rate_at_fixed_action_rate(
            scored
        ),
        model_miss_rate=model_miss_rate(scored),
        synthetic_loss_allowed=synthetic_loss_allowed(scored),
        challenge_rate=challenge_rate(scored),
        alert_rate=alert_rate(scored),
        decline_rate=decline_rate(scored),
    )
