"""Phase 5 metric-primitive tests.

Hand-built ``ScoredEvalRecord`` fixtures so every metric is verifiable
by inspection. Plus the judge-never-fits invariant — the judge module
must never invoke ``sklearn.LogisticRegression.fit``.
"""
from __future__ import annotations

from unittest import mock
from typing import Any

import pytest

from atlas.judge.metrics import (
    AMOUNT_BUCKET_TO_SYNTHETIC_LOSS,
    ScoredEvalRecord,
    alert_rate,
    challenge_rate,
    decline_rate,
    false_positive_rate_at_fixed_action_rate,
    metric_snapshot,
    model_miss_rate,
    recall_at_fixed_action_rate,
    score_eval_set,
    synthetic_loss_allowed,
    synthetic_loss_prevented,
)


def _scored(
    label: int,
    action: str,
    *,
    amount_bucket: str = "amount_bucket_03",
    score: float = 0.5,
    eid: str = "tx_x",
) -> ScoredEvalRecord:
    return ScoredEvalRecord(
        event_id=eid,
        customer_id="cust_x",
        feature_vector={},  # type: ignore[typeddict-item]  # not read by metric fns
        synthetic_truth_label=(
            "high_risk_synthetic_activity" if label == 1 else "normal_activity"
        ),
        binary_label=label,
        amount_bucket=amount_bucket,
        score=score,
        decision_action=action,
    )


# ---------------------------------------------------------------------------
# AMOUNT_BUCKET_TO_SYNTHETIC_LOSS
# ---------------------------------------------------------------------------


def test_amount_bucket_map_has_ten_entries():
    assert len(AMOUNT_BUCKET_TO_SYNTHETIC_LOSS) == 10


def test_amount_bucket_map_keys_are_canonical():
    expected = {f"amount_bucket_{i:02d}" for i in range(1, 11)}
    assert set(AMOUNT_BUCKET_TO_SYNTHETIC_LOSS) == expected


def test_amount_bucket_map_strictly_monotonic():
    keys_sorted = sorted(AMOUNT_BUCKET_TO_SYNTHETIC_LOSS)
    vals = [AMOUNT_BUCKET_TO_SYNTHETIC_LOSS[k] for k in keys_sorted]
    assert all(b > a for a, b in zip(vals, vals[1:]))


def test_amount_bucket_values_are_integers():
    for v in AMOUNT_BUCKET_TO_SYNTHETIC_LOSS.values():
        assert isinstance(v, int) and v > 0


# ---------------------------------------------------------------------------
# model_miss_rate (§16.1)
# ---------------------------------------------------------------------------


def test_miss_rate_empty_input_returns_zero():
    assert model_miss_rate([]) == 0.0


def test_miss_rate_no_high_risk_returns_zero():
    rs = [_scored(0, "accept"), _scored(0, "challenge")]
    assert model_miss_rate(rs) == 0.0


def test_miss_rate_all_high_risk_accepted_is_one():
    rs = [_scored(1, "accept"), _scored(1, "accept"), _scored(1, "accept")]
    assert model_miss_rate(rs) == 1.0


def test_miss_rate_all_high_risk_caught_is_zero():
    rs = [_scored(1, "challenge"), _scored(1, "alert"), _scored(1, "decline")]
    assert model_miss_rate(rs) == 0.0


def test_miss_rate_mixed_high_risk():
    # 3 high-risk: 2 accepted, 1 declined → miss = 2/3
    rs = [_scored(1, "accept"), _scored(1, "accept"), _scored(1, "decline")]
    assert model_miss_rate(rs) == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# recall_at_fixed_action_rate (§16.3)
# ---------------------------------------------------------------------------


def test_recall_complementary_to_miss_rate():
    rs = [
        _scored(1, "accept"), _scored(1, "challenge"),
        _scored(1, "alert"),  _scored(1, "decline"),
        _scored(0, "accept"),
    ]
    assert recall_at_fixed_action_rate(rs) + model_miss_rate(rs) == pytest.approx(1.0)


def test_recall_no_high_risk_returns_zero():
    rs = [_scored(0, "challenge")]
    assert recall_at_fixed_action_rate(rs) == 0.0


# ---------------------------------------------------------------------------
# false_positive_rate (§16.5)
# ---------------------------------------------------------------------------


def test_fpr_no_normal_returns_zero():
    rs = [_scored(1, "accept")]
    assert false_positive_rate_at_fixed_action_rate(rs) == 0.0


def test_fpr_known_split():
    # 4 normal events: 1 challenged, 3 accepted → fpr = 1/4 = 0.25
    rs = [
        _scored(0, "challenge"), _scored(0, "accept"),
        _scored(0, "accept"),    _scored(0, "accept"),
    ]
    assert false_positive_rate_at_fixed_action_rate(rs) == 0.25


# ---------------------------------------------------------------------------
# action-rate metrics
# ---------------------------------------------------------------------------


def test_action_rates_sum_to_one_minus_accept():
    rs = [
        _scored(1, "accept"), _scored(0, "challenge"),
        _scored(0, "alert"),  _scored(1, "decline"),
    ]
    total = challenge_rate(rs) + alert_rate(rs) + decline_rate(rs)
    accepts = sum(1 for r in rs if r["decision_action"] == "accept") / len(rs)
    assert total + accepts == pytest.approx(1.0)


def test_per_action_rates_known_split():
    rs = [
        _scored(0, "challenge"), _scored(0, "challenge"),
        _scored(0, "alert"),     _scored(0, "decline"),
        _scored(0, "accept"),    _scored(0, "accept"),
    ]
    assert challenge_rate(rs) == pytest.approx(2 / 6)
    assert alert_rate(rs) == pytest.approx(1 / 6)
    assert decline_rate(rs) == pytest.approx(1 / 6)


def test_action_rates_empty_input_zero():
    assert challenge_rate([]) == 0.0
    assert alert_rate([]) == 0.0
    assert decline_rate([]) == 0.0


# ---------------------------------------------------------------------------
# synthetic_loss (§16.6)
# ---------------------------------------------------------------------------


def test_synthetic_loss_only_counts_accepted_high_risk():
    rs = [
        # accepted high-risk → counts (bucket 05 = 18000)
        _scored(1, "accept", amount_bucket="amount_bucket_05"),
        # caught high-risk → does NOT count
        _scored(1, "challenge", amount_bucket="amount_bucket_10"),
        # accepted normal → does NOT count
        _scored(0, "accept", amount_bucket="amount_bucket_10"),
    ]
    assert synthetic_loss_allowed(rs) == 18000.0


def test_synthetic_loss_uses_canonical_map():
    # Sum of buckets 01..10 if all were accepted high-risk
    rs = [
        _scored(1, "accept", amount_bucket=f"amount_bucket_{i:02d}")
        for i in range(1, 11)
    ]
    expected = sum(AMOUNT_BUCKET_TO_SYNTHETIC_LOSS.values())
    assert synthetic_loss_allowed(rs) == float(expected)


def test_synthetic_loss_prevented_arithmetic():
    assert synthetic_loss_prevented(5000, 3000) == 2000.0
    assert synthetic_loss_prevented(100, 200) == -100.0
    assert synthetic_loss_prevented(0, 0) == 0.0


# ---------------------------------------------------------------------------
# metric_snapshot
# ---------------------------------------------------------------------------


def test_metric_snapshot_emits_seven_keys():
    rs = [_scored(1, "challenge"), _scored(0, "accept")]
    snap = metric_snapshot(rs)
    assert set(snap) == {
        "recall_at_fixed_action_rate",
        "false_positive_rate_at_fixed_action_rate",
        "model_miss_rate",
        "synthetic_loss_allowed",
        "challenge_rate",
        "alert_rate",
        "decline_rate",
    }
    # All values are numeric
    for v in snap.values():
        assert isinstance(v, (int, float))


# ---------------------------------------------------------------------------
# score_eval_set + judge-never-fits invariant
# ---------------------------------------------------------------------------


def test_score_eval_set_produces_unit_interval_scores(trained_baseline_dir):
    from atlas.judge.holdouts import load_eval_set
    from atlas.model.policy import load_decision_policy_config
    from atlas.model.scorer import load_baseline_bundle

    bundle = load_baseline_bundle(trained_baseline_dir)
    config = load_decision_policy_config()
    records = load_eval_set("clean_holdout")
    scored = score_eval_set(records, bundle, config)
    assert len(scored) == len(records)
    for r in scored:
        assert 0.0 <= r["score"] <= 1.0
        assert r["decision_action"] in {"accept", "challenge", "alert", "decline"}


def test_judge_never_calls_logistic_regression_fit(trained_baseline_dir):
    """Bible §13.3 + Phase 5 invariant: the judge never refits.

    Patch ``sklearn.linear_model.LogisticRegression.fit`` and run a full
    evaluate_fix; assert ``fit`` was never called by the judge code path.
    The bundle on disk was produced by Phase 4's trainer and is loaded
    via ``joblib`` — the load path doesn't call ``fit`` either.
    """
    from sklearn.linear_model import LogisticRegression
    from atlas.judge.evaluate import evaluate_fix, reset_caches

    reset_caches()
    with mock.patch.object(
        LogisticRegression, "fit", autospec=True
    ) as fit_mock:
        # Patch the judge's BASELINE_MODELS_ROOT to the test fixture so
        # version-keyed lookup resolves to the trained baseline.
        import atlas.judge.evaluate as evaluate_mod
        original_root = evaluate_mod.BASELINE_MODELS_ROOT
        evaluate_mod.BASELINE_MODELS_ROOT = trained_baseline_dir.parent
        try:
            evaluate_fix(
                run_id="r", round_id=1, defensive_fix_id="f",
                baseline_model_version="baseline_v1",
                candidate_model_version="baseline_v1",
            )
        finally:
            evaluate_mod.BASELINE_MODELS_ROOT = original_root
            reset_caches()

    assert fit_mock.call_count == 0, (
        f"judge invoked LogisticRegression.fit {fit_mock.call_count} time(s); "
        "the judge must never refit."
    )


def test_score_eval_set_does_not_pass_synthetic_truth_label_to_scorer(
    trained_baseline_dir,
):
    """No-label-leakage: ``score_features`` is called with a FeatureVector
    that does NOT contain ``synthetic_truth_label``.
    """
    from atlas.judge.holdouts import load_eval_set
    from atlas.model.policy import load_decision_policy_config
    from atlas.model.scorer import load_baseline_bundle
    import atlas.judge.metrics as metrics_mod

    bundle = load_baseline_bundle(trained_baseline_dir)
    config = load_decision_policy_config()
    records = load_eval_set("clean_holdout")[:5]

    seen_payloads: list[dict[str, Any]] = []

    def _wrap(fv, b):
        seen_payloads.append(dict(fv))
        return 0.1  # arbitrary

    with mock.patch.object(metrics_mod, "score_features", side_effect=_wrap):
        # apply_decision_policy still runs; pass a low score so it
        # accepts (band thresholds in policy.py).
        score_eval_set(records, bundle, config)

    assert seen_payloads, "score_features was never called"
    for payload in seen_payloads:
        assert "synthetic_truth_label" not in payload
        assert "binary_label" not in payload
