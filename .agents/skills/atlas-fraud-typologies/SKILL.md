---
name: atlas-fraud-typologies
description: Project Atlas model vulnerability families and defensive fix mapping. Use when editing red_team, blue_team, model vulnerability cards, defensive fix proposals, or vulnerability-family config.
---

# Atlas synthetic model vulnerability families

Use these abstract families only. Do not turn them into operational narratives.

| Family ID | Public name | Safe description | Expected defensive fix | Main metric |
|---|---|---|---|---|
| `low_velocity_high_graph_risk` | Low individual activity, high relationship risk | Event looks moderate in isolation, but synthetic graph risk is high. | Add relationship-risk feature or threshold rule | `model_miss_rate` |
| `recent_change_feature_delay` | Recent change not reflected quickly enough | Recent synthetic behavior change is underweighted by lagged aggregates. | Add streaming recent-change feature | `recall_at_fixed_action_rate` |
| `score_boundary_cluster` | High-risk events near action threshold | High-risk synthetic events cluster just below a decision threshold. | Adjust thresholding under action-rate limit | `accepted_high_risk_events` |
| `activity_channel_shift` | Under-ranked channel distribution shift | A synthetic activity channel has drifted relative to training. | Recalibrate model by channel | `locked_adaptive_holdout_pass` |
| `current_device_mismatch` | Current-device context gap | Current device differs from a most-recent-login assumption. | Add explicit current-device features | `feature_consistency_error_rate` |
| `label_noise_mislearned` | Noisy labels drive poor generalization | Found examples improve but locked holdout does not. | Governance rejection or retraining with regularization | `drifted_holdout_pass` |
| `overfit_fix_failure` | Fix works only on found examples | Defensive fix improves found set but fails locked holdout. | Reject fix; require generalizing feature | `fix_generalization_score` |

Safe model vulnerability cards include denominator counts, model miss rate, lift versus random search, affected decision action, and a cohort definition using synthetic feature predicates only.
