---
name: atlas-fixture-shape
description: Project Atlas fixture, replay, ledger, and sample-data shape. Use when editing fixtures, replay payloads, ledgers, or generated synthetic records.
---

# Atlas fixture shape

Use `project_atlas_sample_data.json` as the fixture-shape guide. Records must be synthetic and deterministic from seed.

ID patterns:

```text
cust_000001
acct_000001
dev_000001
recip_000001
extacct_000001
sess_000001
sec_000001
tx_000001
label_tx_000001
mv_round1_001
fix_round1_graph_risk_feature
judge_round1_fix_graph_risk
run_2026_001
```

Required top-level fixture sections:

```text
project
entities
events
features
label_generation
model_vulnerability_families
model_vulnerability_cards
defensive_fix_candidates
judge_reports
ledger_records
```

Public-safe label values:

```text
normal_activity
high_risk_synthetic_activity
```

Do not create PII-like names, exact addresses, real account numbers, real institution labels, real endpoint URLs, real tables, or exact transaction amounts. Use buckets such as `region_03`, `amount_bucket_02`, and `balance_bucket_04`.
