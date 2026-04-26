---
name: atlas-metrics
description: Project Atlas judge metrics and acceptance criteria. Use when editing src/atlas/judge, metrics, reports, evaluation logic, charts, or defensive fix acceptance.
---

# Atlas metrics

Only `src/atlas/judge/` may produce final metric values. Agent summaries must not invent, overwrite, or accept metrics.

Formulas:

```text
model_miss_rate = accepted_high_risk_events / valid_high_risk_events_tested
miss_rate_lift_vs_random = adaptive_search_model_miss_rate / random_search_model_miss_rate
recall_at_fixed_action_rate = high_risk_events_caught_at_limit / total_high_risk_events
recall_improvement = fixed_recall_at_fixed_action_rate - baseline_recall_at_fixed_action_rate
false_positive_rate_increase = fixed_false_positive_rate - baseline_false_positive_rate
challenge_rate_increase = fixed_challenge_rate - baseline_challenge_rate
decline_rate_increase = fixed_decline_rate - baseline_decline_rate
alert_rate_increase = fixed_alert_rate - baseline_alert_rate
synthetic_loss_allowed = sum(amount_bucket_value for accepted high_risk_synthetic_activity events)
synthetic_loss_prevented = baseline_synthetic_loss_allowed - fixed_synthetic_loss_allowed
```

A defensive fix passes only if recall at the fixed action-rate limit improves, model miss rate decreases, false-positive rate stays within tolerance, challenge/decline/alert limits are not exceeded, locked adaptive holdout improves or stays neutral, and safety scan passes.

Charts must label all loss and performance values as synthetic demo metrics.
