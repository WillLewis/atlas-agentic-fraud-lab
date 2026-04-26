# Project Atlas Bible

**Project name:** Project Atlas  
**Project folder:** `atlas-agentic-fraud-lab`  
**Python package:** `src/atlas/`  
**Version:** 0.3  
**Status:** Build-ready project bible for a synthetic agentic fraud-model evaluation demo  
**Default posture:** Defensive, synthetic-only, public-safe  
**Primary build surface:** Claude Code, Next.js, FastAPI, Python simulation, deterministic evaluation  
**Primary evaluation claim:** Agentic red-team testing and bank-defense agents can identify synthetic model vulnerabilities and reduce model miss rate while preserving fixed customer-friction limits.

---

## 1. Project definition

**Project Atlas** is a synthetic red/blue fraud-model evaluation arena. Red-team agents run constrained synthetic searches against a mock account-takeover risk scorer. Bank-defense agents propose defensive fixes. A deterministic evaluation harness, not an agent, decides whether each fix improves recall at fixed action-rate limits without increasing false positives beyond configured limits.

The web app tells the story in five public-safe steps:

1. Agents are assigned.
2. Agents are deployed.
3. Round 1: red-team agents test; bank-defense agents respond.
4. Round 2: red-team agents adapt; bank-defense agents respond.
5. Round 3: final evaluation report.

The project is inspired by the agent-assignment, multi-run, scrollytelling structure of Project Deal, but it uses a synthetic fraud-defense setting, abstract visuals, local-only services, and defensive evaluation language.

---

## 2. Companion specification files

These files are part of the Project Atlas source-of-truth set. Claude Code should read the most relevant file before implementation work.

| File | Role |
|---|---|
| `PROJECT_ATLAS_BIBLE.md` | Main product, safety, architecture, and build plan reference |
| `CLAUDE.md` | Root Claude Code instructions, kept short enough for repeated use |
| `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md` | Detailed component architecture, synthetic data model, sample data summary, and API schema summary |
| `PROJECT_ATLAS_COMPONENT_ARCHITECTURE.xlsx` | Spreadsheet version of the component architecture table |
| `project_atlas_sample_data.json` | Public-safe synthetic fixture examples for entities, events, features, labels, model vulnerability cards, defensive fix candidates, judge reports, and ledger records |
| `project_atlas_openapi.yaml` | OpenAPI schema for the local-only FastAPI service |

---

## 3. Public terminology standard

Project Atlas should use clear public terminology in prose, UI copy, API fields, configs, filenames, and variables.

| Avoid in public copy or variables | Use instead | Example variable |
|---|---|---|
| budget | action-rate limit, scoring-query limit, decision threshold | `challenge_rate_limit_pct`, `max_score_queries` |
| patch | defensive fix | `defensive_fix_id`, `fix_type` |
| blind spot | model vulnerability, under-ranked cohort | `model_vulnerability_id` |
| attack | red-team test, synthetic search | `red_team_search_request` |
| evasion rate | model miss rate, accepted high-risk rate | `model_miss_rate` |
| exploit | identify, surface, under-rank | `under_ranked_cohort_count` |
| fraud playbook | synthetic risk pattern | `model_vulnerability_family_id` |

The legacy words above may appear only in an internal terminology map, safety-filter list, or note explaining what not to use. This section is the source of truth; `.claude/skills/atlas-terminology/SKILL.md` is the derived artifact loaded by Claude Code at runtime.

---

## 4. Product goals

### 4.1 Internal funding goal

Show that a Fraud Adversarial System could become a serious product capability by demonstrating a safe workflow:

- Identify synthetic model vulnerabilities before real incidents occur.
- Convert under-ranked cohorts into reproducible model vulnerability cards.
- Propose feature, decision-threshold, or model-calibration defensive fixes.
- Evaluate defensive fixes under fixed customer-friction limits.
- Record every run in a ledger for reproducibility and governance.

### 4.2 External portfolio goal

Show to AI labs, AI safety teams, ML platform teams, and fraud-model practitioners that the builder can design and implement:

- A multi-agent evaluation environment.
- A closed synthetic simulation with useful measurement.
- Agentic red-team testing without unsafe operational guidance.
- A deterministic judge that separates persuasive agent text from measured performance.
- A polished Project Deal-style web narrative.
- A model-tier comparison between stronger and weaker agents.

### 4.3 Viewer takeaway

A practitioner should leave the demo believing:

> Project Atlas is a credible synthetic evaluation harness for measuring whether agentic red-team testing and agentic bank defense can improve fraud-model resilience under realistic customer-friction limits.

---

## 5. Non-goals

Do **not** build or imply any of the following:

- Production bank integration.
- Real customer data.
- Real institution-specific decision thresholds, rules, endpoint URLs, credentials, repositories, tables, model names, or platform names.
- Differential privacy.
- Real phishing, credential-theft, authentication-bypass, account-access, or money-movement instructions.
- Academic research claims.
- Claims that synthetic results prove production exposure.
- Autonomous decisioning for live financial systems.

---

## 6. Safety doctrine

Project Atlas is allowed only because it is closed-loop, synthetic, defensive, and evaluated by deterministic controls.

### 6.1 Non-negotiable safety rules

1. **Synthetic data only.** All customers, accounts, devices, locations, transfers, recipients, graph links, labels, transcripts, and losses must be procedurally generated or stored in public-safe fixtures.
2. **Local-only services.** The only scoring API is the local mock scorer. Never call, configure, or describe a production scoring endpoint.
3. **No real controls.** Decision thresholds and action-rate limits are demo constants, not institution-specific controls.
4. **No real PII.** Use synthetic identifiers such as `cust_000123`, `acct_000456`, `dev_000789`, and `recipient_000321`.
5. **No operational fraud guidance.** Red-team outputs describe synthetic feature-space model vulnerabilities, not steps a real person could use.
6. **No credential or authentication abuse content.** Do not produce instructions for phishing, credential theft, MFA bypass, account takeover, SIM swapping, social engineering, or cash-out.
7. **Agents propose; deterministic code decides.** LLM-generated text cannot accept a defensive fix, report a metric, or override the judge.
8. **Holdouts are locked.** Red-team and bank-defense simulation agents may not inspect locked holdout labels or records. Runtime gating in `src/atlas/judge/holdouts.py` prevents round-time exposure, and `.claude/settings.json` denies Claude Code reads of locked holdout records and drifted-holdout labels during development.
9. **Feature generation must be realistic.** Synthetic search mutates event histories, then recomputes features. Direct engineered-feature mutation is allowed only behind an explicit debug flag and must not power the public demo.
10. **Public mode is scrubbed.** Public demos must not show real institution names, internal paths, private source identifiers, real thresholds, or internal platform details.

### 6.2 Safety review checklist before every demo

The safety-scan invariant is enforced automatically through `.claude/hooks/` and remains part of the manual final review.

- [ ] `DEMO_MODE=public`.
- [ ] `make safety-scan` passes.
- [ ] No production domains, auth-token strings, warehouse table names, internal repo URLs, or cloud-storage paths appear in code, UI, fixtures, or outputs.
- [ ] No real institution name appears in the public app.
- [ ] Red-team transcripts use safe synthetic language.
- [ ] Defensive fix cards frame all changes as risk reduction and customer-friction control.
- [ ] All metrics come from `src/atlas/judge/`, not agent summaries.
- [ ] The README states: “Synthetic demo. Not a production fraud system. Not fraud advice.”
- [ ] API responses and browser console logs do not expose unsafe or internal strings.

### 6.3 Unsafe phrasing to rewrite

| Unsafe phrasing | Safe replacement |
|---|---|
| “How the fraudster bypassed the bank” | “Synthetic cohort that the mock scorer under-ranked” |
| “Use a new device and move funds quickly” | “The synthetic sequence has elevated device novelty and money-movement velocity” |
| “Phishing / OTP / credential theft steps” | “Account-access precursor is represented only as a binary synthetic risk marker” |
| “Real thresholds and rules” | “Demo decision thresholds and synthetic action-rate limits” |
| “Real production model” | “Mock account-takeover risk scorer” |

This section is the source of truth; `.claude/skills/atlas-safety-doctrine/SKILL.md` is the derived artifact loaded by Claude Code at runtime.

---

## 7. Demo modes

### 7.1 Public mode

Set:

```bash
DEMO_MODE=public
```

Public mode must use:

- Generic institution label: `RetailBank-X`
- Generic model label: `Mock Account-Takeover Risk Scorer`
- Generic transfer labels: `instant_transfer`, `external_transfer`, `large_transfer`
- Generic decision variables: `decline_rate_limit_bps`, `challenge_rate_limit_pct`, `alert_rate_limit_pct`
- Synthetic records only

### 7.2 Internal funding mode

Set:

```bash
DEMO_MODE=internal
```

Internal mode may discuss business relevance more directly, but the implementation must still use only synthetic data unless a formally approved data-access path exists. The codebase should never require internal files.

### 7.3 Required config behavior

All user-facing labels must be read from config:

```yaml
demo_mode: public
institution_label: RetailBank-X
model_label: Mock Account-Takeover Risk Scorer
disclaimer: Synthetic closed-loop demo. No real customers, no real controls, no production endpoints.
```

---

## 8. Five-step web app narrative

### Step 1 — Agents are assigned

Show abstract red-team, bank-defense, and judge cards. Do not use human photos.

Red-team agents:

- Fraud Scenario Agent
- Evolutionary Search Agent
- Graph Probe Agent
- Model Vulnerability Analyst Agent

Bank-defense agents:

- Bank Strategy Agent
- Feature Fix Agent
- Decision-Threshold Fix Agent
- Model Calibration Fix Agent
- Governance Agent

Deterministic control:

- Evaluation Judge

Main message:

> The agents receive objectives, tools, scoring-query limits, action-rate limits, and safety constraints. No agent can access real customer data or production systems.

### Step 2 — Agents are deployed

Show the synthetic environment:

- Synthetic customer population.
- Synthetic event stream.
- Local mock scoring API.
- Baseline decision-threshold overlay.
- Baseline model metrics.
- Clean, found, locked adaptive, and drifted holdouts.

Main message:

> The mock institution starts with a plausible account-takeover risk scorer and fixed customer-friction limits.

### Step 3 — Round 1: red-team test and bank-defense response

Show:

- Scoring-query limit used.
- Under-ranked high-risk synthetic events found.
- First model vulnerability card.
- First defensive fix candidate.
- Judge result.

Main message:

> Red-team agents identify the first synthetic model vulnerability; bank-defense agents propose a fix; the judge checks whether measured improvement is real.

### Step 4 — Round 2: adaptive pressure

Show:

- Red-team agents adapt to the round 1 defensive fix.
- A new model vulnerability family appears.
- Bank-defense agents propose a feature or decision-threshold fix.
- Governance rejects fixes that violate action-rate limits or fail locked holdout.

Main message:

> The value is not one-time testing; it is repeated adaptation with disciplined measurement.

### Step 5 — Round 3: final evaluation report

Show:

- Model miss rate trend across rounds.
- Recall at fixed action-rate limit.
- Synthetic loss allowed vs prevented.
- Customer-friction metrics.
- Defensive fix generalization on locked holdout.
- Model-tier comparison card.
- Run ledger.

Main message:

> Agentic defense improves resilience only when paired with deterministic evaluation and strict customer-friction limits.

---

## 9. System architecture

```text
                                  ┌───────────────────────────────┐
                                  │        Web App / Story         │
                                  │ five steps, charts, cards      │
                                  └───────────────▲───────────────┘
                                                  │
                                  ┌───────────────┴───────────────┐
                                  │           API Layer            │
                                  │ runs, rounds, metrics, cards   │
                                  └───────────────▲───────────────┘
                                                  │
             ┌────────────────────────────────────┼────────────────────────────────────┐
             │                                    │                                    │
┌────────────┴────────────┐          ┌────────────┴────────────┐          ┌────────────┴────────────┐
│ Synthetic Environment    │          │ Agent Orchestration      │          │ Deterministic Judge     │
│ customers/events/graphs  │          │ red-team + defense       │          │ metrics + acceptance    │
└────────────▲────────────┘          └────────────▲────────────┘          └────────────▲────────────┘
             │                                    │                                    │
             └──────────────────────┬─────────────┴─────────────┬──────────────────────┘
                                    │                           │
                         ┌──────────┴──────────┐     ┌──────────┴──────────┐
                         │ Mock Scorer +        │     │ Ledger + Replay      │
                         │ Decision Thresholds  │     │ JSONL + snapshots    │
                         └──────────────────────┘     └─────────────────────┘
```

---

## 10. Recommended repository structure

```text
atlas-agentic-fraud-lab/
  CLAUDE.md
  PROJECT_ATLAS_BIBLE.md
  PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md
  PROJECT_ATLAS_COMPONENT_ARCHITECTURE.xlsx
  project_atlas_sample_data.json
  project_atlas_openapi.yaml
  README.md
  package.json
  pyproject.toml
  Makefile
  .mcp.json

  .claude/
    settings.json
    agents/
    hooks/
      safety_scan_changed_files.py
      safety_scan_pending.py
    skills/
      atlas-terminology/
        SKILL.md
      atlas-safety-doctrine/
        SKILL.md
      atlas-metrics/
        SKILL.md
      atlas-fraud-typologies/
        SKILL.md
      atlas-fixture-shape/
        SKILL.md

  app/
    web/
      app/
      components/
      lib/
      public/
    api/
      main.py
      routes/
      schemas/

  config/
    demo.yaml
    safety.yaml
    synthetic_schema.yaml
    decision_thresholds.yaml
    agent_roster.yaml
    round_config.yaml
    model_quality_matrix.yaml

  src/
    atlas/
      synthetic/
        customers.py
        accounts.py
        devices.py
        recipients.py
        events.py
        graph.py
        features.py
        labels.py
        splits.py
      model/
        train.py
        scorer.py
        policy.py
        calibration.py
      red_team/
        random_search.py
        evolutionary_search.py
        scoring_query_allocator.py
        graph_probe.py
        model_vulnerability_packager.py
      blue_team/
        strategy_agent.py
        feature_fix_agent.py
        policy_fix_agent.py
        model_calibration_fix_agent.py
        governance_agent.py
        fix_applier.py
      judge/
        metrics.py
        holdouts.py
        evaluate.py
        acceptance.py
      ledger/
        ledger.py
        replay.py
        report_builder.py
      safety/
        scanner.py
        text_filters.py
        config_validator.py
      devtools/
        mcp_server.py

  data/
    synthetic/
    fixtures/

  outputs/
    runs/
    ledgers/
    model_vulnerabilities/
    defensive_fixes/
    reports/
    demo_replays/

  tests/
    unit/
    integration/
    safety/
    fixtures/

  scripts/
    bootstrap_demo.py
    generate_synthetic.py
    train_baseline.py
    run_rounds.py
    build_replay.py
    safety_scan.py
```

For the complete file-by-file architecture table, use `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md` and `PROJECT_ATLAS_COMPONENT_ARCHITECTURE.xlsx`.

---

## 11. Synthetic data model

### 11.1 Entities

Use synthetic identifiers only.

```text
Customer
Account
Device
Recipient
ExternalAccount
GraphEdge
LoginSession
SecurityEvent
TransferEvent
FeatureVector
LabelGenerationRecord
ModelVulnerabilityFamily
ModelVulnerabilityCard
DefensiveFixCandidate
JudgeReport
LedgerRecord
```

### 11.2 Event types

Safe event types:

```text
login_success
login_challenge_required
challenge_passed
challenge_failed
password_recovery_completed
username_recovery_completed
profile_update
recipient_added
external_account_link_attempt
instant_transfer_attempt
external_transfer_attempt
large_transfer_attempt
```

### 11.3 Feature families

Public-safe feature examples:

```text
login_count_72h
login_count_30d
login_velocity_ratio
challenge_count_72h
challenge_pass_ratio_30d
password_recovery_count_72h
username_recovery_count_72h
device_count_72h
current_device_tenure_days
geo_consistency_flag
region_change_count_72h
transfer_count_72h
cash_movement_velocity_score
recipient_tenure_days
new_recipient_indicator
shared_device_degree
shared_recipient_degree
entity_graph_risk_score
account_age_days
```

### 11.4 Label generation

Labels must be generated from synthetic latent drivers, not real data.

```text
base_customer_risk
account_access_change_marker
device_novelty_marker
security_recovery_marker
cash_movement_velocity_marker
entity_reuse_marker
ring_membership_marker
label_noise
```

### 11.5 Synthetic model vulnerability families

Use abstract families, not operational playbooks.

| Family ID | Public description |
|---|---|
| `low_velocity_high_graph_risk` | Individual activity looks moderate, but synthetic relationship graph risk is high. |
| `recent_change_feature_delay` | Recent synthetic behavior changes are underweighted when delayed features lag. |
| `score_boundary_cluster` | High-risk synthetic events cluster just below a decision threshold. |
| `activity_channel_shift` | A synthetic channel mix shift causes one activity channel to be under-ranked. |
| `current_device_mismatch` | Current-device context differs from a most-recent-login assumption. |
| `label_noise_mislearned` | Noisy labels produce fixes that do not generalize. |
| `overfit_fix_failure` | A defensive fix improves found examples but fails locked adaptive holdout. |

This section is the source of truth; `.claude/skills/atlas-fraud-typologies/SKILL.md` is the derived artifact loaded by Claude Code at runtime.

---

## 12. Mock scorer and decision-threshold overlay

### 12.1 Local API endpoints

The full schema is in `project_atlas_openapi.yaml`. The same local FastAPI service is additionally exposed through a project-scoped MCP wrapper for development tooling; it remains local-only, synthetic-only, and disconnected from production systems.

```http
GET  /health
GET  /config/demo
GET  /schema
GET  /decision-thresholds
POST /synthetic/generate
GET  /synthetic/sample
POST /score
POST /batch-score
POST /runs
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/rounds
GET  /runs/{run_id}/rounds/{round_id}
POST /rounds/run
POST /red-team/search
GET  /runs/{run_id}/model-vulnerabilities
GET  /model-vulnerabilities/{model_vulnerability_id}
POST /defensive-fixes/propose
POST /defensive-fixes/apply
POST /judge/evaluate-fix
GET  /runs/{run_id}/judge-reports/{judge_report_id}
GET  /replay/{run_id}
POST /safety/scan
GET  /model-quality-matrix
```

### 12.2 Score response

```json
{
  "event_id": "evt_000123",
  "score": 0.0842,
  "decision_action": "challenge",
  "decision_band": "challenge_threshold_band",
  "model_version": "baseline_v1",
  "decision_threshold_version": "thresholds_v1",
  "reason_codes": ["recent_activity_change", "entity_graph_risk"]
}
```

### 12.3 Decision actions

```text
accept
challenge
alert
decline
```

### 12.4 Decision-threshold configuration

All values are synthetic demo constants.

```yaml
decision_thresholds:
  decline_score_threshold: 0.92
  challenge_score_threshold: 0.74
  alert_score_threshold: 0.86

action_rate_limits:
  decline_rate_limit_bps: 25
  challenge_rate_limit_pct: 8.0
  alert_rate_limit_pct: 15.0
  review_rate_limit_pct: 3.0
```

The decision overlay maps score and safe context features into actions:

```text
score + context + decision thresholds + action-rate limits -> decision_action
```

Do not create rules that reveal or approximate a real institution’s controls.

---

## 13. Simulation agent roster

Simulation agents are runtime Python modules invoked by the Round Engine. They are separate from Claude Code builder subagents under `.claude/agents/`, which assist development only and never participate in a round.

### 13.1 Red-team simulation agents

#### Fraud Scenario Agent

Purpose: proposes abstract synthetic model vulnerability hypotheses.

Allowed:

- Choose a configured vulnerability family.
- Propose which search method should receive more scoring-query capacity.
- Explain model-risk intuition in safe terms.

Not allowed:

- Real fraud tactics.
- Production controls.
- Credential, phishing, MFA, account-access, or money-movement instructions.

#### Evolutionary Search Agent

Purpose: optimizes synthetic event histories to find under-ranked high-risk examples.

Allowed:

- Mutate event timing, counts, synthetic graph links, and synthetic activity combinations within config constraints.
- Call the local mock scorer.
- Return candidate batches.

Not allowed:

- Mutate labels.
- Mutate engineered features directly except for debug-only baseline.
- Access locked holdout labels or records.

#### Graph Probe Agent

Purpose: explores safe synthetic relationship-risk vulnerabilities.

Allowed:

- Analyze synthetic recipient/device/account graph structure.
- Propose graph features.
- Identify cohorts with elevated graph risk but low model score.

#### Model Vulnerability Analyst Agent

Purpose: turns discovered misses into model vulnerability cards.

Allowed:

- Summarize accepted high-risk synthetic candidates.
- Generate safe cohort definitions.
- Recommend defensive fix families.

### 13.2 Bank-defense simulation agents

#### Bank Strategy Agent

Purpose: triages model vulnerability cards and selects a defensive fix approach.

#### Feature Fix Agent

Purpose: proposes defensive features derived from synthetic event histories or graph relationships.

#### Decision-Threshold Fix Agent

Purpose: proposes synthetic decision-threshold changes while preserving action-rate limits.

#### Model Calibration Fix Agent

Purpose: retrains or recalibrates the mock scorer using allowed synthetic training data.

#### Governance Agent

Purpose: blocks unsafe, overfit, limit-violating, or non-generalizing defensive fixes.

### 13.3 Deterministic Judge

The judge is code, not an LLM. It owns:

- Metrics.
- Holdout evaluation.
- Defensive fix acceptance.
- Action-rate limit enforcement.
- Ledger validation.

---

## 14. Round protocol

Each round follows this sequence:

1. Load the current model and decision-threshold overlay.
2. Load scoring-query limits and safety constraints.
3. Red-team simulation agents produce a safe synthetic search plan.
4. Search workers generate candidate event histories.
5. The feature calculator recomputes features from those histories.
6. The local mock scorer returns score and decision action.
7. The Model Vulnerability Analyst packages under-ranked high-risk candidates.
8. Bank-defense simulation agents propose one or more defensive fixes.
9. The fix applier creates a candidate model, feature, or decision-threshold version.
10. The deterministic judge evaluates clean holdout, found adaptive set, locked adaptive holdout, and drifted holdout.
11. The Governance Agent summarizes accept/reject rationale using judge output.
12. The ledger records run metadata, metrics, fix versions, and safe transcript summaries.

---

## 15. Core schemas

### 15.1 Red-team search request

```json
{
  "round_id": 1,
  "objective": "identify under-ranked high-risk synthetic candidates under a fixed scoring-query limit",
  "allowed_family_id": "low_velocity_high_graph_risk",
  "max_score_queries": 1200,
  "max_runtime_seconds": 180,
  "search_methods": ["random", "evolutionary", "graph_probe"],
  "safety_notes": ["synthetic only", "no operational details", "feature recomputation required"]
}
```

### 15.2 Candidate event history

```json
{
  "candidate_id": "cand_000123",
  "customer_id": "cust_000456",
  "events": [
    {"event_type": "login_success", "timestamp_offset_min": -180, "device_id": "dev_001"},
    {"event_type": "password_recovery_completed", "timestamp_offset_min": -120, "device_id": "dev_002"},
    {"event_type": "instant_transfer_attempt", "timestamp_offset_min": 0, "recipient_id": "recipient_009"}
  ],
  "synthetic_truth_label": "high_risk_synthetic_activity",
  "family_id": "low_velocity_high_graph_risk"
}
```

### 15.3 Model vulnerability card

```json
{
  "model_vulnerability_id": "mv_round1_001",
  "round_id": 1,
  "family_id": "low_velocity_high_graph_risk",
  "summary": "Synthetic high-risk events with moderate individual activity but elevated relationship risk are under-ranked by the baseline mock scorer.",
  "valid_high_risk_events_tested": 1200,
  "accepted_high_risk_events": 92,
  "model_miss_rate": 0.0767,
  "miss_rate_lift_vs_random": 3.4,
  "estimated_synthetic_loss_allowed": 184000,
  "affected_decision_action": "accept",
  "safe_cohort_definition": {
    "entity_graph_risk_score": "> synthetic_p90",
    "model_score": "below_challenge_threshold",
    "recipient_tenure_days": "low"
  },
  "recommended_defensive_fix_types": ["feature_fix", "policy_fix"]
}
```

### 15.4 Defensive fix candidate

```json
{
  "defensive_fix_id": "fix_round1_graph_risk_feature",
  "round_id": 1,
  "fix_type": "feature_fix",
  "description": "Add a synthetic relationship-risk feature and recalibrate the mock scorer under fixed action-rate limits.",
  "files_changed": [
    "src/atlas/synthetic/features.py",
    "src/atlas/model/train.py"
  ],
  "expected_benefit": "Reduce accepted high-risk synthetic events in the relationship-risk cohort.",
  "rate_limit_claim": {
    "max_false_positive_rate_increase": 0.001,
    "max_challenge_rate_increase": 0.0
  },
  "requires_judge_evaluation": true
}
```

### 15.5 Judge report

```json
{
  "judge_report_id": "judge_round1_fix_graph_risk",
  "round_id": 1,
  "defensive_fix_id": "fix_round1_graph_risk_feature",
  "accepted_by_judge": true,
  "baseline": {
    "recall_at_fixed_action_rate": 0.44,
    "false_positive_rate_at_fixed_action_rate": 0.01,
    "model_miss_rate": 0.0767,
    "synthetic_loss_allowed": 184000
  },
  "fixed": {
    "recall_at_fixed_action_rate": 0.58,
    "false_positive_rate_at_fixed_action_rate": 0.01,
    "model_miss_rate": 0.0312,
    "synthetic_loss_allowed": 91000
  },
  "holdout_generalization": {
    "clean_holdout_pass": true,
    "locked_adaptive_holdout_pass": true,
    "drifted_holdout_pass": true
  },
  "judge_notes": "Fix accepted because recall improved at the same action-rate limit and clean-customer friction stayed within tolerance."
}
```

### 15.6 Ledger record

```json
{
  "run_id": "run_2026_001",
  "round_id": 1,
  "seed": 42,
  "demo_mode": "public",
  "model_version_before": "baseline_v1",
  "decision_threshold_version_before": "thresholds_v1",
  "model_version_after": "model_v2_graph_feature",
  "decision_threshold_version_after": "thresholds_v1",
  "agent_roster_version": "agents_v1",
  "safety_scan_passed": true,
  "judge_report_path": "outputs/reports/run_2026_001_round1_judge.json",
  "model_vulnerability_card_path": "outputs/model_vulnerabilities/mv_round1_001.json"
}
```

---

## 16. Metrics

This section is the source of truth; `.claude/skills/atlas-metrics/SKILL.md` is the derived artifact loaded by Claude Code at runtime.

### 16.1 Model miss rate

```text
model_miss_rate = accepted_high_risk_events / valid_high_risk_events_tested
```

### 16.2 Miss-rate lift vs random search

```text
miss_rate_lift_vs_random = adaptive_search_model_miss_rate / random_search_model_miss_rate
```

### 16.3 Recall at fixed action-rate limit

```text
recall_at_fixed_action_rate = high_risk_events_caught_at_limit / total_high_risk_events
```

### 16.4 Recall improvement

```text
recall_improvement = fixed_recall_at_fixed_action_rate - baseline_recall_at_fixed_action_rate
```

### 16.5 Customer-friction metrics

```text
false_positive_rate_increase = fixed_false_positive_rate - baseline_false_positive_rate
challenge_rate_increase = fixed_challenge_rate - baseline_challenge_rate
decline_rate_increase = fixed_decline_rate - baseline_decline_rate
alert_rate_increase = fixed_alert_rate - baseline_alert_rate
```

### 16.6 Synthetic loss metrics

```text
synthetic_loss_allowed = sum(amount for accepted high_risk_synthetic_activity events)
synthetic_loss_prevented = baseline_synthetic_loss_allowed - fixed_synthetic_loss_allowed
```

### 16.7 Defensive fix acceptance criteria

A defensive fix passes only if:

```text
recall_at_fixed_action_rate improves
AND model_miss_rate decreases
AND false_positive_rate stays within tolerance
AND challenge/decline/alert rate limits are not exceeded
AND locked adaptive holdout improves or stays neutral
AND safety scanner passes
```

---

## 17. Model-tier comparison

Use precomputed runs for reliability.

| Run | Red-team agent tier | Bank-defense agent tier | Purpose |
|---|---|---|---|
| A | Frontier | Frontier | Best-case agentic loop |
| B | Compact | Frontier | Strong defense, weaker red-team testing |
| C | Frontier | Compact | Stress case: strong red-team testing, weaker defense |
| D | Compact | Compact | Low-cost baseline |

In the public app, use labels such as `Frontier` and `Compact` unless model names are explicitly configured for a private demo.

Illustrative findings to show:

```text
Stronger red-team agents identify more model vulnerabilities.
Stronger bank-defense agents reduce model miss rate faster and overfit less.
Compact bank-defense agents may produce plausible explanations that fail locked holdout.
```

---

## 18. Build plan

### Phase 0 — Bootstrap repo

1. Create repo `atlas-agentic-fraud-lab`.
2. Add `CLAUDE.md` and `PROJECT_ATLAS_BIBLE.md`.
3. Add `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md`, `PROJECT_ATLAS_COMPONENT_ARCHITECTURE.xlsx`, `project_atlas_sample_data.json`, and `project_atlas_openapi.yaml`.
4. Add `.gitignore` for generated data, env files, outputs, non-project artifacts, and local secrets.
5. Add `README.md` with the synthetic-only disclaimer.
6. Add `Makefile`, Python manifest, and Node manifest.
7. Add `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/`, and `.mcp.json`.
8. Add `config/demo.yaml`, `config/safety.yaml`, `config/synthetic_schema.yaml`, and `config/decision_thresholds.yaml`.
9. Add `scripts/safety_scan.py` with a `--paths` argument before implementing any agent logic.

Acceptance criteria:

- `make safety-scan` exists.
- `DEMO_MODE=public` is the default.
- The README clearly states the project is synthetic and defensive.

### Phase 1 — Web app shell

1. Create a Next.js app under `app/web`.
2. Add the five-section page and left sidebar.
3. Add abstract agent cards; no human photos.
4. Add placeholder charts for model miss rate, recall, synthetic loss, and customer-friction metrics.
5. Add a persistent synthetic-only disclaimer.

Acceptance criteria:

- App runs locally.
- Five sections are visible.
- Placeholder data loads from safe fixture JSON.
- No real institution name appears.

### Phase 2 — Synthetic environment

1. Implement synthetic customer, account, device, recipient, external account, graph, and event generators.
2. Implement latent-label generation.
3. Split train/validation/holdout by synthetic customer.
4. Create locked adaptive holdout and drifted holdout.
5. Add deterministic seed tests.

Acceptance criteria:

- Same seed produces same dataset.
- No PII-like fields are generated.
- Customer-level split prevents leakage.

### Phase 3 — Feature calculator

1. Implement login, challenge, recovery, device, geo, transfer, recipient, and relationship-graph features.
2. Add safe divide-by-zero handling.
3. Add tests that event mutations change recomputed features.
4. Block direct feature mutation unless `DEBUG_DIRECT_FEATURE_MUTATION=true`.

Acceptance criteria:

- Features are derived from event histories.
- Feature calculator passes tests.
- Debug-only direct mutation cannot run in public demo mode.

### Phase 4 — Baseline model and local mock scorer

1. Train a baseline tree-based or logistic mock scorer.
2. Calibrate score distribution.
3. Implement decision-threshold overlay.
4. Implement local FastAPI scoring endpoints.
5. Implement the local MCP wrapper over the same endpoints for Claude Code development tooling.
6. Add deterministic reason codes.
7. Store baseline metrics.

Acceptance criteria:

- API returns score, decision action, decision band, model version, threshold version, and reason codes.
- Decision thresholds and action-rate limits are configurable.
- Baseline metrics appear in the web app.

### Phase 5 — Deterministic judge

1. Implement model miss rate.
2. Implement recall at fixed action-rate limit.
3. Implement false-positive, challenge, decline, and alert rate checks.
4. Implement synthetic loss allowed and prevented.
5. Evaluate clean, found adaptive, locked adaptive, and drifted holdouts.
6. Implement defensive fix acceptance logic.

Acceptance criteria:

- Judge compares baseline vs fixed version.
- Judge output is JSON and reproducible.
- Agent text cannot override judge results.

### Phase 6 — Red-team synthetic search

1. Implement random search baseline.
2. Implement evolutionary search over event histories.
3. Implement relationship graph probe.
4. Implement scoring-query allocator across search methods.
5. Validate candidate constraints.
6. Package model vulnerability cards.
7. Safety-filter generated summaries.

Acceptance criteria:

- Adaptive search beats random search on at least one seeded model vulnerability family.
- All outputs are synthetic.
- Model vulnerability cards use safe cohort descriptions.

### Phase 7 — Bank-defense fixes

1. Implement defensive fix schemas.
2. Implement feature fix candidate.
3. Implement decision-threshold fix candidate.
4. Implement model calibration fix candidate.
5. Implement fix applier.
6. Run judge on each candidate.
7. Reject fixes that improve found examples but fail locked holdout.

Acceptance criteria:

- At least two fix families work.
- Defensive fixes are evaluated by judge.
- Overfit or limit-violating fixes are visibly rejected.

### Phase 8 — Round engine and ledger

1. Implement round state object.
2. Implement three-round lifecycle.
3. Save metrics snapshots per round.
4. Save model vulnerability cards and defensive fix cards.
5. Save safe transcript summaries.
6. Add replay support.

Acceptance criteria:

- Three rounds run from seed.
- Ledger can reproduce the same metrics.
- Web app can load `outputs/demo_replays`.

### Phase 9 — Web integration

1. Add API routes for runs, rounds, metrics, model vulnerability cards, defensive fix cards, judge reports, and transcripts.
2. Replace placeholder charts with replay data.
3. Add trend charts and decision cards.
4. Add model-tier comparison card.

Acceptance criteria:

- Five sections tell a complete story.
- Charts reflect actual judge metrics.
- App remains safe in public mode.

### Phase 10 — Safety hardening and demo package

1. Implement string scanner for banned internal terms, URL patterns, secrets, and unsafe copy.
2. Add safety tests.
3. Add public-mode smoke test.
4. Add demo script.
5. Add limitations and “what this proves / does not prove.”
6. Prepare one reliable precomputed replay.

Acceptance criteria:

- `make test` passes.
- `make safety-scan` passes.
- A reviewer can run the demo without API keys.
- The narrative is understandable in 8–10 minutes.

---

## 19. Commands to implement

```bash
make setup
make seed
make train
make run-rounds
make build-replay
make test
make safety-scan
make demo-api
make demo-web
```

Expected behavior:

```bash
make seed          # generate synthetic data
make train         # train baseline mock scorer
make run-rounds    # run three red-team/defense rounds
make build-replay  # prepare web app replay JSON
make demo-api      # start FastAPI backend
make demo-web      # start Next.js frontend
```

---

## 20. Claude Code workflow

1. Start in plan mode.
2. Read `CLAUDE.md`.
3. Read the relevant section of this bible.
4. For file-level architecture details, read `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md`.
5. For API changes, read `project_atlas_openapi.yaml`.
6. For fixture expectations, read `project_atlas_sample_data.json`.
7. Build in vertical slices: web shell, synthetic data, scorer, judge, red-team search, defensive fixes, round engine, web integration.
8. After every slice, run targeted tests and safety scan.
9. Commit only public-safe code and curated synthetic fixtures.
10. Never commit generated data that has not passed safety scan or non-project artifacts that are irrelevant to the demo.

---

## 21. Builder subagents (Claude Code helpers)

Builder subagents are optional Claude Code development helpers. They do not call the Atlas runtime APIs as round participants, do not coordinate red→judge→blue protocol, and do not replace simulation agents implemented under `src/atlas/`.

```text
.claude/agents/frontend-scrollytelling.md
.claude/agents/backend-api.md
.claude/agents/synthetic-data.md
.claude/agents/ml-judge.md
.claude/agents/red-team-search.md
.claude/agents/defensive-fixes.md
.claude/agents/safety-reviewer.md
.claude/agents/demo-polish.md
```

Recommended constraints:

| Subagent | Scope |
|---|---|
| safety-reviewer | Read-only review plus tests and safety scan |
| frontend-scrollytelling | Frontend files only |
| backend-api | `app/api/` and API tests |
| synthetic-data | `src/atlas/synthetic/` and synthetic tests |
| ml-judge | `src/atlas/judge/` and metric tests |
| red-team-search | Synthetic search modules and tests, no public copy |
| defensive-fixes | Bank-defense modules and tests |

---

## 22. Testing strategy

### Unit tests

- Synthetic data reproducibility.
- Feature calculations.
- Decision-threshold overlay.
- Metric formulas.
- Defensive fix acceptance.
- Safety filters.

### Integration tests

- Generate data -> calculate features -> train scorer -> score batch.
- Search -> model vulnerability card -> defensive fix -> judge.
- Three-round replay.
- API -> web fixture loading.

### Safety tests

- No real institution names in public mode.
- No internal path patterns.
- No real endpoint URL patterns.
- No secrets.
- No unsafe red-team transcript language.
- No non-project artifacts or unsafe generated data included in the public demo package.

---

## 23. Acceptance criteria for the 7–9 day build

| Area | Acceptance criterion |
|---|---|
| Web app | Five-step Project Deal-style scrollytelling demo works locally. |
| Synthetic world | Data is generated from seed, not imported from real sources. |
| Baseline scorer | Local mock scorer produces score, decision action, and reason codes. |
| Red-team search | Adaptive search beats random search on seeded model vulnerability families. |
| Bank defense | At least two defensive fix types are implemented. |
| Judge | Defensive fixes are evaluated on clean, found adaptive, locked adaptive, and drifted holdouts. |
| Metrics | Model miss rate, synthetic loss, recall at fixed action-rate limit, false-positive rate, and customer-friction metrics are visible. |
| Rounds | Three red-team/defense rounds are replayable. |
| Model-tier comparison | Four precomputed run cells show Frontier vs Compact differences. |
| Safety | Public-mode safety scan passes. |
| Reproducibility | Same seed recreates the same ledger metrics. |
| Story | A practitioner can understand the demo in 8–10 minutes. |

---

## 24. Recommended demo script

### Opening

> This is Project Atlas, a synthetic red/blue fraud-model evaluation arena. It asks whether AI agents can help identify and reduce model vulnerabilities under fixed customer-friction limits.

### Step 1

> We assign red-team agents to run synthetic tests and bank-defense agents to propose defensive fixes. The agents are constrained: synthetic data only, no production endpoints, no real controls, and no operational fraud guidance.

### Step 2

> We deploy them into a mock account-takeover scoring environment. The scorer rank-orders synthetic events, and a decision-threshold overlay maps scores to accept, challenge, alert, or decline.

### Step 3

> In round 1, red-team agents identify an under-ranked high-risk cohort that random search missed. Bank-defense agents propose a feature fix. The judge evaluates whether the fix improves recall at the same action-rate limit.

### Step 4

> In round 2, red-team agents adapt. One plausible fix is rejected because it fails locked holdout. A better fix balances detection and customer friction.

### Step 5

> By round 3, model miss rate declines, recall at the fixed action-rate limit improves, synthetic loss allowed falls, and customer-friction metrics remain within limits. The ledger records the full process.

### Closing

> This does not prove production exposure. It proves a workflow: identify, package, fix, evaluate, and replay under safety constraints.

---

## 25. What this project proves and does not prove

### Proves

- Synthetic adaptive search can reveal seeded model vulnerabilities.
- Bank-defense agents can propose useful defensive fix families.
- Deterministic evaluation can separate useful fixes from persuasive but bad fixes.
- A polished app can make the red-team/defense loop legible to product, model risk, and engineering audiences.

### Does not prove

- That any real bank model has these vulnerabilities.
- That any real decision threshold is exposed.
- That synthetic model results generalize to production data.
- That agents should make autonomous production fraud decisions.

---

## 26. Final implementation principle

Build every component around this invariant:

> Agents may generate hypotheses, candidates, defensive fix proposals, and explanations. Only deterministic code can score, evaluate, accept, reject, or report final metrics.
