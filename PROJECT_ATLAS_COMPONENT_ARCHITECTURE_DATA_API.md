# Project Atlas — Component Architecture, Synthetic Data Model, Sample Data, and API Schema

**Project name:** Project Atlas  
**Project folder:** `atlas-agentic-fraud-lab`  
**Default posture:** synthetic-only, defensive, public-safe  
**Primary audience:** Product Managers, AI/ML practitioners, and engineers  

This document uses clear public-facing terminology throughout. Bible §3 is the source of truth; `.claude/skills/atlas-terminology/SKILL.md` is the derived runtime-loaded artifact for Claude Code:

| Older shorthand | Public-facing term used here | Variable naming pattern |
|---|---|---|
| Budget | Action-rate limit, scoring-query limit, or decision threshold | `challenge_rate_limit_pct`, `max_score_queries` |
| Patch | Defensive fix | `defensive_fix_id`, `fix_type` |
| Blind spot | Model vulnerability or under-ranked cohort | `model_vulnerability_id`, `model_miss_rate` |
| Attack | Red-team test or synthetic search | `red_team_search_request` |
| Evasion rate | Model miss rate / accepted high-risk rate | `model_miss_rate` |

---

## 1. Component Architecture Table

The table below is the recommended build map for `atlas-agentic-fraud-lab`. It includes the file or directory, description, purpose, inputs, outputs, and likely failure modes.

### 1.1 Root files

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `CLAUDE.md` | Persistent Claude Code instructions | Gives Claude Code project rules, safety constraints, build order, and naming conventions | Human-written project guidance | Consistent build behavior across sessions | Stale instructions; old terms like `budget`, `patch`, or `blindspot` reappear; missing safety constraints |
| `PROJECT_ATLAS_BIBLE.md` | Main project specification | Defines product goals, safety posture, architecture, synthetic data, agents, metrics, and demo flow | Project goals, safety decisions, technical decisions | Build-ready design reference | Inconsistent names; too much scope; unclear public/internal boundaries |
| `README.md` | Public project overview | Lets reviewers run and understand the demo | Project description, setup commands, disclaimers | Setup guide, demo summary, limitations | Overclaims production relevance; misses synthetic-only disclaimer; broken commands |
| `.gitignore` | Ignore rules | Prevents generated data, secrets, env files, non-project artifacts, and local sensitive files from being committed | Repo layout, output paths | Git exclusion rules | Accidentally allows `.env`, local secrets, non-project artifacts, or generated unsafe transcripts |
| `package.json` | Frontend dependency manifest | Declares Next.js and UI dependencies | Node package names and versions | Installed frontend dependencies | Version mismatch; missing scripts; excessive dependencies slow build |
| `pyproject.toml` | Python dependency and tool manifest | Declares backend/simulation dependencies and formatting/test config | Python package names and versions | Installed backend dependencies | Unpinned risky versions; missing package path; import errors |
| `Makefile` | Unified command surface | Provides single-command workflow for setup, data generation, training, rounds, replay, tests, and safety scan | Scripts, app commands, environment variables | Repeatable CLI commands | Commands point to wrong paths; commands claim success without running checks |
| `.claude/settings.json` | Claude Code project settings | Enforces permissions, safety hooks, and high-risk edit confirmations | Claude Code settings schema, project safety rules | Project-scoped Claude Code behavior | Permissions too loose; hooks not triggered; locked holdout read not blocked |
| `.claude/hooks/` | Claude Code hook scripts | Runs targeted safety scans after relevant writes and before session stop | Hook JSON from Claude Code, changed paths | Safety-scan feedback and blocking decisions | Hook input parsing misses a file; false positives interrupt safe work |
| `.claude/skills/` | Project skills | Stores lazy-loaded operational knowledge derived from the Bible | Bible sections, safety rules, metric formulas, fixture shape | `SKILL.md` files loaded only when relevant | Skill drift vs Bible; descriptions too broad or too narrow |
| `.claude/agents/` | Builder subagents | Optional Claude Code helpers for development work only | Builder task prompts | Development assistance summaries | Confused with runtime simulation agents |
| `.mcp.json` | Project-scoped MCP config | Exposes the local Atlas API wrapper to Claude Code development tooling | Local MCP server command and local API base URL | MCP tools for `/score`, `/judge/evaluate-fix`, `/red-team/search`, and `/safety/scan` | Points to non-local URL; wrapper not running; project approval missing |

### 1.2 Frontend files — `app/web/`

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `app/web/app/layout.tsx` | Global web layout | Provides page shell, fonts, metadata, left navigation wrapper, and safety disclaimer area | Static metadata, app config | Rendered application frame | Missing disclaimer; inconsistent title; hydration errors |
| `app/web/app/page.tsx` | Main five-step story page | Renders the full Project Atlas scroll-down demo | Replay API payload or fixture JSON | Five narrative sections | Blank page if replay data missing; sections out of order; unsafe copy displayed |
| `app/web/app/globals.css` | Global styles | Provides base styles, responsive layout, and chart/card spacing | Tailwind config, CSS variables | Consistent UI styling | Accessibility issues; unreadable contrast; broken mobile layout |
| `app/web/components/LeftSidebar.tsx` | Step navigation | Allows users to jump between the five narrative sections | Step metadata | Sidebar links and active section marker | Active state wrong; keyboard navigation broken |
| `app/web/components/DisclaimerBanner.tsx` | Synthetic-only notice | Makes safety posture visible in public mode | Demo config | Persistent disclaimer banner | Missing from pages; copy too vague |
| `app/web/components/AgentRoster.tsx` | Agent assignment cards | Shows red-team test agents, bank defense agents, and deterministic judge | Agent roster API or fixture | Agent cards | Uses human images; unclear roles; unsafe labels like real fraud tactics |
| `app/web/components/EnvironmentOverview.tsx` | Synthetic environment summary | Shows synthetic customers, events, scorer, thresholds, and holdouts | Schema, dataset summary, threshold config | Environment cards | Implies real bank data; displays internal names |
| `app/web/components/MetricCard.tsx` | Single metric display | Displays recall, model miss rate, synthetic loss, and customer-friction metrics | Metric snapshot | Metric cards | Agent-generated values shown instead of judge-derived values |
| `app/web/components/RoundTimeline.tsx` | Round status visualization | Shows rounds 1–3 and before/after metrics | Round summaries | Timeline | Rounds not reproducible; missing failed-round handling |
| `app/web/components/ModelVulnerabilityCard.tsx` | Under-ranked cohort summary | Shows safe evidence for each model vulnerability | Model vulnerability API payload | Public-safe vulnerability card | Uses unsafe operational language; exposes detailed step-by-step behavior |
| `app/web/components/DefensiveFixCard.tsx` | Defensive fix summary | Shows feature, policy, or model-calibration fix proposals | Defensive fix payload | Fix card | Overstates fix success before judge evaluation |
| `app/web/components/JudgeDecisionCard.tsx` | Deterministic evaluation result | Shows whether the fix passed objective checks | Judge report | Accepted/rejected decision card | Lets agent narrative override judge report |
| `app/web/components/SafeTranscriptPanel.tsx` | Sanitized agent summary display | Shows safe, summarized red/blue agent activity | Filtered transcripts | Transcript panel | Raw unsafe text displayed; too much operational detail |
| `app/web/components/RunComparisonMatrix.tsx` | Model-quality comparison | Shows frontier-vs-compact run comparison | Precomputed matrix | Comparison table/chart | Claims statistical proof from exploratory demo |
| `app/web/components/charts/MissRateChart.tsx` | Model miss rate trend | Charts accepted high-risk synthetic events over rounds | Round metrics | Line/bar chart | Uses wrong denominator; chart label says “real fraud” |
| `app/web/components/charts/RecallRecoveryChart.tsx` | Recall improvement trend | Charts recall at fixed action-rate limit | Judge metrics | Trend chart | Shows recall without fixed-rate context |
| `app/web/components/charts/SyntheticLossChart.tsx` | Synthetic loss chart | Shows loss allowed and prevented in the synthetic world | Judge metrics | Chart | Implies real dollars; misses synthetic label |
| `app/web/components/charts/FrictionChart.tsx` | Customer-friction chart | Shows false-positive, challenge, alert, and decline rates | Judge metrics | Chart | Action-rate limits not shown; false-positive rate confused with challenge rate |
| `app/web/lib/api.ts` | API client | Centralizes calls to FastAPI backend | Endpoint URLs, request payloads | Typed API responses | Calls non-local endpoint; no error handling |
| `app/web/lib/types.ts` | Frontend TypeScript types | Keeps UI payloads consistent with API schemas | OpenAPI-derived or hand-written types | Type definitions | Type drift vs backend Pydantic models |
| `app/web/lib/formatters.ts` | Display helpers | Formats rates, bps, percentages, synthetic currency, and labels | Numbers, strings | Human-readable display text | Rounds percentages incorrectly; hides synthetic labels |
| `app/web/public/` | Static assets | Stores abstract icons and public-safe images | SVGs, static JSON if needed | Browser-accessible assets | Human photos or copyrighted source assets included |

### 1.3 API files — `app/api/`

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `app/api/main.py` | FastAPI application entry point | Creates app, mounts routers, configures CORS for localhost | Router modules, config | Local API server | CORS blocks web app; accidentally allows non-local origins |
| `app/api/routes/health.py` | Health route | Confirms API availability and public/internal demo mode | None | Health response | Reports healthy while dependencies unavailable |
| `app/api/routes/config.py` | Demo config route | Returns public-safe labels and disclaimers | `config/demo.yaml` | Demo config JSON | Public mode leaks internal terms |
| `app/api/routes/schema.py` | Synthetic schema route | Returns entity, event, feature, and vulnerability-family metadata | `config/synthetic_schema.yaml` | Schema metadata | Schema drift vs generator/models |
| `app/api/routes/decision_thresholds.py` | Threshold route | Returns score thresholds and action-rate limits | `config/decision_thresholds.yaml` | Threshold JSON | Uses stale thresholds; action-rate limits mislabeled as production values |
| `app/api/routes/synthetic.py` | Synthetic data routes | Generates or previews synthetic data | Generation request, seed, schema config | Synthetic sample or generation summary | Non-deterministic seed; generates PII-like values |
| `app/api/routes/scoring.py` | Scoring routes | Scores one or many synthetic event records | Event record and feature vector | Score, decision action, reason codes | Accepts raw feature mutation when disabled; batch too large |
| `app/api/routes/runs.py` | Run management routes | Creates, lists, and retrieves evaluation runs | Run config, ledger | Run summaries/details | Run state corruption; duplicate run IDs |
| `app/api/routes/rounds.py` | Round execution routes | Runs red-team search, defensive response, judge evaluation | Run ID, round config | Round summaries/details | Partial round writes; failed fix still recorded as accepted |
| `app/api/routes/model_vulnerabilities.py` | Model vulnerability routes | Lists and retrieves under-ranked cohort cards | Run ID, vulnerability ID | Model vulnerability cards | Unsafe card text; missing evidence metrics |
| `app/api/routes/defensive_fixes.py` | Defensive fix routes | Proposes and applies defensive fixes | Vulnerability cards, allowed fix types | Defensive fix candidates/application result | Fix changes files outside allowlist; fix not evaluated |
| `app/api/routes/judge.py` | Judge routes | Evaluates defensive fixes with deterministic metrics | Baseline/fixed model versions, holdouts | Judge report | Uses training set instead of holdout; non-deterministic metrics |
| `app/api/routes/replay.py` | Replay route | Serves complete web replay payload | Run ID, output snapshots | Replay JSON | Replay differs from ledger; missing safety-filtered transcripts |
| `app/api/routes/safety.py` | Safety scan route | Scans text/files for public-demo safety issues | Text or file paths | Safety scan report | False negatives allow unsafe text; false positives block safe labels |
| `app/api/routes/model_quality.py` | Model-quality matrix route | Serves precomputed frontier-vs-compact comparison | Matrix config/output file | Comparison matrix | Overstates exploratory comparison; missing caveat |
| `app/api/schemas/base.py` | Shared Pydantic models | Defines common response and error types | None | Base schemas | Inconsistent error schema |
| `app/api/schemas/scoring.py` | Scoring request/response models | Validates score and batch-score payloads | Event and feature records | Typed API payloads | Missing required features; bad enum values accepted |
| `app/api/schemas/synthetic.py` | Synthetic data schemas | Validates synthetic generation and sample payloads | Generator configs | Typed payloads | Allows PII-like fields |
| `app/api/schemas/run.py` | Run and round schemas | Validates run creation and round execution | Run/round configs | Typed payloads | Bad round state accepted |
| `app/api/schemas/fix.py` | Defensive fix schemas | Validates fix proposals and apply requests | Fix payloads | Typed payloads | “Fix” skipped judge evaluation |
| `app/api/schemas/judge.py` | Judge schemas | Validates metric snapshots and reports | Metrics and holdout status | Typed judge reports | Missing fixed-action-rate context |

### 1.4 Configuration files — `config/`

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `config/demo.yaml` | Public/internal labels | Controls public-safe naming and disclaimers | Demo mode | Labels shown in UI/API | Real institution labels leak in public mode |
| `config/safety.yaml` | Safety scanner rules | Defines banned strings, URL patterns, unsafe copy patterns, and file allowlists | Banned patterns, allowlists | Safety scan behavior | Too permissive; blocks all useful terms |
| `config/synthetic_schema.yaml` | Synthetic schema | Defines allowed entities, events, fields, and feature names | Schema definitions | Generator/API validation | Generator produces fields not in schema |
| `config/decision_thresholds.yaml` | Decision thresholds and action-rate limits | Defines synthetic score-to-action thresholds and max action rates | Threshold constants | Policy behavior | Thresholds treated as real; inconsistent with judge |
| `config/agent_roster.yaml` | Simulation agent roles | Defines safe runtime red-team, bank-defense, and judge-facing roles for the Round Engine | Simulation agent names, model tiers, role prompts | Runtime simulation agent roster | Runtime roles are confused with Claude Code builder subagents; agents receive unsafe or overbroad instructions |
| `config/round_config.yaml` | Round settings | Defines number of rounds, max score queries, allowed families, and allowed fixes | Experiment parameters | Round engine config | Max query limit ignored; holdout exposed |
| `config/model_quality_matrix.yaml` | Model-tier comparison setup | Defines frontier/compact comparison cells | Precomputed run IDs or fixtures | Comparison matrix | Claims live comparison when replay is precomputed |

### 1.5 Core Python package — `src/atlas/`

Files under `src/atlas/red_team/` and `src/atlas/blue_team/` are runtime simulation-agent modules or deterministic workers invoked by the Round Engine. They are not Claude Code builder subagents; builder subagents live only under `.claude/agents/` and assist development.

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `src/atlas/__init__.py` | Package marker | Makes `atlas` importable | None | Python package | Import path mismatch |
| `src/atlas/synthetic/customers.py` | Customer generator | Creates synthetic customer profiles | Seed, schema config | Customer records | Generates PII-like fields; non-deterministic output |
| `src/atlas/synthetic/accounts.py` | Account generator | Creates synthetic accounts linked to customers | Customer records, seed | Account records | Orphan accounts; invalid account states |
| `src/atlas/synthetic/devices.py` | Device generator | Creates synthetic devices and device histories | Customer records, seed | Device records | Device IDs reused incorrectly; missing current device |
| `src/atlas/synthetic/recipients.py` | Recipient generator | Creates synthetic recipients and external accounts | Customer records, seed | Recipient/external account records | Relationship degree not reproducible |
| `src/atlas/synthetic/events.py` | Event generator | Creates login, security, and transfer events | Entities, schema, seed | Event stream | Event order invalid; missing timestamps; unsafe event names |
| `src/atlas/synthetic/graph.py` | Relationship graph builder | Builds customer-device-recipient graph | Entities, events | Graph edges and graph metrics | Self-loops not handled; graph leakage across splits |
| `src/atlas/synthetic/features.py` | Feature calculator | Recomputes features from event histories | Events, graph, config | Feature vectors | Direct feature mutation; divide-by-zero; lag windows wrong |
| `src/atlas/synthetic/labels.py` | Label generator | Creates synthetic truth labels from latent drivers | Events, features, latent config | Label records | Labels equal model features too directly; no label noise control |
| `src/atlas/synthetic/splits.py` | Dataset splitter | Splits train/validation/holdout by customer | Labeled records, seed | Split files | Customer leakage across train/holdout |
| `src/atlas/model/train.py` | Baseline model trainer | Trains mock risk scorer | Training features/labels | Model artifact, training metrics | Overfits; class imbalance not handled; no fixed seed |
| `src/atlas/model/scorer.py` | Score calculation | Produces risk score for feature vectors | Model artifact, features | Scores | Model artifact missing; feature order mismatch |
| `src/atlas/model/policy.py` | Decision policy | Maps score + context to accept/challenge/alert/decline | Scores, thresholds, action-rate limits | Decision actions | Action-rate limits exceeded; wrong threshold order |
| `src/atlas/model/calibration.py` | Score calibration | Calibrates scores and threshold curves | Validation set, model scores | Calibration metadata | Calibration fit on holdout; unstable thresholds |
| `src/atlas/red_team/random_search.py` | Runtime simulation-agent search worker | Provides simple benchmark search | Search config, scorer | Candidate results | Random baseline too weak or unseeded |
| `src/atlas/red_team/evolutionary_search.py` | Runtime simulation-agent search worker | Finds under-ranked high-risk synthetic event histories | Search config, scorer, constraints | Candidate event histories | Direct feature mutation; invalid event sequences |
| `src/atlas/red_team/scoring_query_allocator.py` | Runtime simulation-agent allocator | Allocates scoring-query limit across search methods | Round config, intermediate results | Query allocation plan | Starves useful method; exceeds max score queries |
| `src/atlas/red_team/graph_probe.py` | Runtime simulation-agent graph probe | Finds relationship-risk under-ranked cohorts | Graph, scorer, features | Candidate cohorts | Uses graph features unavailable to model in unfair way unless disclosed |
| `src/atlas/red_team/model_vulnerability_packager.py` | Runtime simulation-agent evidence packager | Converts search results into safe model vulnerability cards | Candidate results, metrics | Model vulnerability cards | Unsafe wording; missing denominator/evidence |
| `src/atlas/blue_team/strategy_agent.py` | Runtime simulation-agent defensive strategy selector | Chooses allowed fix approach from vulnerability cards | Vulnerability cards, judge history | Fix plan | Chooses unsupported fix type; overreacts to noisy result |
| `src/atlas/blue_team/feature_fix_agent.py` | Runtime simulation-agent feature fix proposer | Adds defensive feature candidates from synthetic histories | Feature schema, vulnerability cards | Feature fix candidate | Uses unavailable or unsafe feature; leaks holdout labels |
| `src/atlas/blue_team/policy_fix_agent.py` | Runtime simulation-agent decision-threshold fix proposer | Adjusts synthetic decision thresholds within action-rate limits | Thresholds, metrics | Policy fix candidate | Increases customer friction beyond limit |
| `src/atlas/blue_team/model_calibration_fix_agent.py` | Runtime simulation-agent model calibration proposer | Retrains or recalibrates the mock scorer | Training data, allowed adversarial examples | Candidate model version | Trains on locked holdout; overfits found examples |
| `src/atlas/blue_team/governance_agent.py` | Runtime simulation-agent governance summarizer | Blocks unsafe, overfit, or action-rate limit violating fixes | Fix candidate, judge report, safety scan | Approval/rejection rationale | Agent text overrides judge; misses safety issue |
| `src/atlas/blue_team/fix_applier.py` | Runtime fix application worker | Applies allowed defensive fixes to model/policy/feature code | Fix candidate | Candidate model/policy version | Writes outside allowed files; cannot rollback |
| `src/atlas/judge/metrics.py` | Metric functions | Computes model miss rate, recall, false positives, loss, action rates | Labels, scores, decisions | Metric snapshots | Wrong denominators; agent-derived metrics accepted |
| `src/atlas/judge/holdouts.py` | Holdout manager | Loads clean, found, locked adaptive, and drifted holdouts | Split files, run state | Holdout datasets | Runtime holdout gating fails; `.claude/settings.json` read-deny backstop missing; split leakage |
| `src/atlas/judge/evaluate.py` | Deterministic evaluation | Compares baseline vs fixed model/policy | Model versions, thresholds, holdouts | Judge report | Non-deterministic evaluation; missing baseline |
| `src/atlas/judge/acceptance.py` | Fix acceptance rules | Applies pass/fail criteria | Judge metrics, limits | Accepted/rejected flag | Allows fix with higher friction or worse locked holdout |
| `src/atlas/ledger/ledger.py` | Run ledger writer | Records run/round/fix/judge metadata | Run state, file paths, metrics | JSONL ledger | Duplicate records; partial writes; unverified file paths |
| `src/atlas/ledger/replay.py` | Replay builder | Creates web-ready replay payloads | Ledger, cards, reports, metrics | Replay JSON | Replay differs from judge source data |
| `src/atlas/ledger/report_builder.py` | Report generator | Builds human-readable summaries | Ledger, judge reports, cards | Markdown/JSON reports | Overclaims; includes raw unsafe transcript |
| `src/atlas/safety/scanner.py` | Safety scanner orchestrator | Runs banned-string, secret, PII-like, and unsafe-copy checks | Text/files/config | Safety scan report | False negatives on unsafe generated content |
| `src/atlas/safety/text_filters.py` | Text rewrite and block rules | Rewrites or blocks unsafe generated copy | Agent summaries, UI text | Safe text | Removes too much useful detail; misses sensitive terms |
| `src/atlas/safety/config_validator.py` | Config validation | Ensures public mode uses safe labels and local-only endpoints | Config files | Validation result | Config drift; public mode with internal labels |
| `src/atlas/devtools/mcp_server.py` | Local MCP wrapper | Exposes selected local FastAPI endpoints as project-scoped MCP tools for development | Local API base URL, OpenAPI schema, synthetic request payloads | MCP tool responses for score, judge, search, and safety scan | Connects to non-local URL; wraps endpoints that are not public-safe; server unavailable |

### 1.6 Data, outputs, tests, and scripts

| File / path | Short description | Purpose | Inputs | Outputs | Failure modes |
|---|---|---|---|---|---|
| `data/synthetic/` | Generated synthetic data directory | Stores generated datasets, usually gitignored | Generator outputs | Parquet/CSV/JSON synthetic records | Accidentally committed; stale generated files |
| `data/fixtures/` | Curated small demo fixtures | Stores public-safe examples for tests and UI placeholders | Manually reviewed fixtures | Tiny fixture files | Fixture contains unsafe copy or real-looking values |
| `outputs/runs/` | Run snapshots | Stores state per evaluation run | Round engine | Run state JSON | Partial snapshots; unbounded disk growth |
| `outputs/ledgers/` | Ledger files | Stores JSONL run ledger | Ledger writer | Reproducibility records | Ledger inconsistency; missing safety scan status |
| `outputs/model_vulnerabilities/` | Model vulnerability cards | Stores under-ranked cohort evidence cards | Packager | JSON/Markdown cards | Unsafe details; missing judge link |
| `outputs/defensive_fixes/` | Defensive fix cards | Stores proposed and applied fix records | Blue-team modules | Fix records | Fix accepted without judge report |
| `outputs/reports/` | Judge and run reports | Stores evaluation reports | Judge/report builder | JSON/Markdown reports | Reports not traceable to metrics |
| `outputs/demo_replays/` | Web replay data | Stores public-safe replay payloads | Replay builder | Replay JSON | Unsafe copy; replay not reproducible |
| `tests/unit/test_features.py` | Feature tests | Validates feature computation | Fixture events | Test results | Ratio/lag/window errors |
| `tests/unit/test_policy.py` | Decision policy tests | Validates threshold and action-rate behavior | Scores, thresholds | Test results | Wrong decision action assignment |
| `tests/unit/test_metrics.py` | Metric tests | Validates model miss, recall, false-positive, and loss formulas | Known small arrays | Test results | Incorrect denominator or rounding |
| `tests/unit/test_safety_filters.py` | Safety filter tests | Ensures unsafe examples are blocked or rewritten | Unsafe/safe text fixtures | Test results | Unsafe copy passes |
| `tests/integration/test_score_flow.py` | Score flow integration test | Tests generate -> features -> score -> action | Synthetic fixture | Test results | Feature/model/API mismatch |
| `tests/integration/test_round_flow.py` | Round flow integration test | Tests search -> vulnerability card -> fix -> judge | Seeded run | Test results | Round engine state breaks |
| `tests/integration/test_replay.py` | Replay integration test | Tests ledger -> replay -> frontend payload | Completed run | Test results | Replay data missing cards/charts |
| `tests/safety/test_public_mode.py` | Public-mode safety test | Ensures public demo has no internal or unsafe text | Config, UI copy, outputs | Test results | Public app leaks internal terms |
| `scripts/bootstrap_demo.py` | Bootstrap script | Runs setup flow for demo artifacts | Config, seed | Synthetic data, baseline model, replay | Partial bootstrap; missing dependencies |
| `scripts/generate_synthetic.py` | Data generation script | Creates synthetic datasets | Seed, schema config | Data files | Non-determinism; bad schema |
| `scripts/train_baseline.py` | Model training script | Trains baseline mock scorer | Training features/labels | Model artifact | Overfit model; failed calibration |
| `scripts/run_rounds.py` | Round execution script | Runs three red-team/blue-team rounds | Run config | Ledger, cards, reports | State conflict; no rollback |
| `scripts/build_replay.py` | Replay builder script | Builds public-safe web replay | Ledger, outputs | Replay JSON | Unsafe text or missing chart data |
| `scripts/safety_scan.py` | CLI safety scan | Runs safety scanner over repo/app/output files or explicit `--paths` from hooks | File paths, config | Scan result | Skips important paths; warnings ignored; hook-provided paths not parsed |


### 1.7 Claude Code skills — `.claude/skills/`

The Bible remains the human-readable source of truth. These skill files are derived artifacts that Claude Code loads only when relevant, preserving context economy while keeping detailed operational guidance available.

| Skill path | Source section | Trigger / use case | Key content | Failure modes |
|---|---|---|---|---|
| `.claude/skills/atlas-terminology/SKILL.md` | Bible §3 | UI copy, agent prompts, generated text, API field names | Public-term standard and legacy-to-safe map | Skill drifts from Bible; legacy terms leak into public copy |
| `.claude/skills/atlas-safety-doctrine/SKILL.md` | Bible §6.3 plus safety rules | Red-team text, transcripts, fixtures, copy work, safety scanner updates | Unsafe phrasing rewrites, banned categories, scanner expectations | Over-blocking useful explanations; missing unsafe phrasing |
| `.claude/skills/atlas-metrics/SKILL.md` | Bible §16 | `src/atlas/judge/`, metrics, evaluation, acceptance criteria | Metric formulas, fixed action-rate context, acceptance gates | Agent summaries treated as metrics; wrong denominators |
| `.claude/skills/atlas-fraud-typologies/SKILL.md` | Bible §11.5 | `src/atlas/red_team/`, `src/atlas/blue_team/`, model vulnerability cards | Model vulnerability families, expected detectors, recommended defensive fix types | Operational detail creep; family IDs drift from fixtures |
| `.claude/skills/atlas-fixture-shape/SKILL.md` | Sample data and component data model | Fixtures, replay, ledger, demo payloads | ID naming schemes, sample object shapes, public-safe records | Fixture shape drifts from API schemas; generated records look real |

---

## 2. Synthetic Data Model Tables

### 2.1 Entity model

| Entity | Description | Key fields | Generated by | Consumed by | Example ID | Failure modes |
|---|---|---|---|---|---|---|
| `Customer` | Synthetic person-level profile with no PII | `customer_id`, `customer_segment`, `home_region_bucket`, `account_age_days`, `normal_login_frequency_30d`, `synthetic_base_risk` | `synthetic/customers.py` | Event generator, label generator, splitter | `cust_000001` | PII-like fields; customer leakage across train/holdout |
| `Account` | Synthetic bank account attached to a customer | `account_id`, `customer_id`, `account_type`, `opened_days_ago`, `available_balance_bucket`, `account_status` | `synthetic/accounts.py` | Event generator, transfer events | `acct_000001` | Orphan account; invalid status |
| `Device` | Synthetic device or browser/app identifier | `device_id`, `customer_id`, `device_channel`, `first_seen_days_ago`, `login_count_30d` | `synthetic/devices.py` | Login sessions, features, graph | `dev_000001` | Current device mismatch; unrealistic device reuse |
| `Recipient` | Synthetic transfer recipient | `recipient_id`, `first_seen_days_ago`, `recipient_reuse_degree`, `recipient_risk_bucket` | `synthetic/recipients.py` | Transfer events, graph features | `recip_000077` | Relationship degree not aligned with graph |
| `ExternalAccount` | Synthetic linked external account | `external_account_id`, `customer_id`, `linked_days_ago`, `verification_method`, `external_account_risk_bucket` | `synthetic/recipients.py` | Events, graph | `extacct_000021` | Unsafe real-bank naming; invalid link state |
| `LoginSession` | Synthetic authentication session | `session_id`, `customer_id`, `device_id`, `event_time_utc`, `channel`, `challenge_required`, `challenge_result` | `synthetic/events.py` | Feature calculator, scorer | `sess_000001` | Impossible challenge states; missing device |
| `SecurityEvent` | Synthetic account-access or profile event | `security_event_id`, `customer_id`, `session_id`, `event_type`, `safe_risk_marker` | `synthetic/events.py` | Features, label generator | `sec_000001` | Unsafe event description; missing session linkage |
| `TransferEvent` | Synthetic transfer scoring event | `transfer_event_id`, `customer_id`, `account_id`, `event_type`, `amount_bucket`, `recipient_id`, `synthetic_truth_label` | `synthetic/events.py` | Scorer, judge | `tx_000002` | Amount looks real/too specific; label mismatch |
| `GraphEdge` | Relationship between synthetic nodes | `edge_id`, `source_node_id`, `target_node_id`, `relationship_type`, `event_count` | `synthetic/graph.py` | Graph probe, graph features | `edge_000002` | Graph leakage across splits; self-loops mishandled |
| `FeatureVector` | Engineered features recomputed from events | `event_id`, velocity, challenge, device, geo, transfer, graph features | `synthetic/features.py` | Model, policy, judge | `tx_000002` | Direct mutation; stale feature windows |
| `LabelGenerationRecord` | Synthetic truth-label explanation | `event_id`, latent drivers, `synthetic_risk_probability`, `synthetic_truth_label` | `synthetic/labels.py` | Trainer, judge | `label_tx_000002` | Label equals model score too directly; no noise |
| `ModelVulnerabilityCard` | Evidence that baseline under-ranked a synthetic cohort | `model_vulnerability_id`, `family_id`, `model_miss_rate`, `safe_cohort_definition` | Red-team packager | Web app, blue team, judge | `mv_round1_001` | Unsafe text; missing denominator |
| `DefensiveFixCandidate` | Proposed defensive model/policy/feature change | `defensive_fix_id`, `fix_type`, `description`, `rate_limit_claim` | Blue-team agents | Fix applier, judge | `fix_round1_graph_risk_feature` | Changes outside allowlist; bypasses judge |
| `JudgeReport` | Deterministic evaluation result | `judge_report_id`, baseline/fixed metrics, holdout pass/fail | Judge | Web app, ledger | `judge_round1_fix_graph_risk` | Agent-generated metrics; missing fixed-rate context |
| `LedgerRecord` | Reproducibility record | `run_id`, `round_id`, versions, paths, safety status | Ledger | Replay/report builder | `run_2026_001` | Partial write; invalid paths |

### 2.2 Event type model

| Event type | Safe description | Required fields | Main feature families affected | Label relevance | Failure modes |
|---|---|---|---|---|---|
| `login_success` | Synthetic successful login event | `customer_id`, `device_id`, `event_time_utc`, `channel`, `region_bucket` | Login velocity, device history, geo consistency | Normal or high-risk context depending surrounding events | Missing device; impossible timestamp order |
| `login_challenge_required` | Synthetic login required additional verification | `customer_id`, `session_id`, `event_time_utc`, `challenge_type_bucket` | Challenge behavior | Raises risk only as part of pattern, not alone | Unsafe description of challenge method |
| `challenge_passed` | Synthetic challenge completed | `customer_id`, `session_id`, `event_time_utc` | Challenge pass ratio | Can appear in normal or high-risk scenarios | Multiple contradictory results for same session |
| `challenge_failed` | Synthetic challenge not completed | `customer_id`, `session_id`, `event_time_utc` | Challenge behavior | May indicate increased synthetic risk | Treated as fraud by itself without context |
| `password_recovery_completed` | Synthetic account-access recovery event | `customer_id`, `device_id`, `event_time_utc` | Recovery behavior, login velocity | Higher risk when recent/unusual | Unsafe wording around credential access |
| `username_recovery_completed` | Synthetic username recovery event | `customer_id`, `device_id`, `event_time_utc` | Recovery behavior | Higher risk when recent/unusual | Unsafe account-access instructions |
| `profile_update` | Synthetic customer profile change | `customer_id`, `event_time_utc`, `update_type_bucket` | Recent change indicators | Contextual signal only | Includes real PII fields |
| `recipient_added` | Synthetic recipient added to customer profile | `customer_id`, `recipient_id`, `event_time_utc` | Recipient tenure, graph linkage | Risk increases when paired with transfer and graph risk | Looks like operational playbook if over-described |
| `external_account_link_attempt` | Synthetic external-account link attempt | `customer_id`, `external_account_id`, `event_time_utc` | External account tenure, graph linkage | Contextual signal | Uses real institution names |
| `instant_transfer_attempt` | Synthetic fast transfer scoring event | `customer_id`, `account_id`, `recipient_id`, `amount_bucket`, `event_time_utc` | Transfer velocity, recipient tenure, graph risk | Scored event | Amount too specific; unsafe flow description |
| `external_transfer_attempt` | Synthetic external transfer scoring event | `customer_id`, `account_id`, `external_account_id`, `amount_bucket`, `event_time_utc` | Transfer velocity, external account age | Scored event | Timestamp/processing semantics inconsistent |
| `large_transfer_attempt` | Synthetic high-amount transfer scoring event | `customer_id`, `account_id`, `recipient_id`, `amount_bucket`, `event_time_utc` | Transfer velocity, amount bucket, graph risk | Scored event | User-facing copy says real transfer or real fraud |

### 2.3 Feature-family model

| Feature family | Public feature examples | Derived from | Purpose | Used by | Failure modes |
|---|---|---|---|---|---|
| Login velocity | `login_count_72h`, `login_count_30d`, `login_velocity_ratio` | Login sessions | Compare recent vs historical login behavior | Model, judge | Divide-by-zero; stale 30-day window |
| Challenge behavior | `challenge_count_72h`, `challenge_pass_ratio_30d` | Challenge events | Track recent verification friction patterns | Model, blue-team fixes | Treats challenge outcomes as definitive fraud proof |
| Recovery behavior | `password_recovery_count_72h`, `username_recovery_count_72h` | Security events | Capture recent account-access changes | Model, labels | Unsafe copy; overweights one event |
| Device novelty | `device_count_72h`, `current_device_tenure_days` | Devices, login sessions | Detect unfamiliar synthetic device context | Model, graph probe | Current device identification mismatch |
| Geo consistency | `geo_consistency_flag`, `region_change_count_72h` | Login sessions, customer region bucket | Compare current region bucket with synthetic baseline | Model | Real location/PII leakage if not bucketed |
| Transfer velocity | `transfer_count_72h`, `cash_movement_velocity_score` | Transfer events | Capture recent synthetic money-movement intensity | Model, judge | Operational wording; amount buckets too detailed |
| Recipient tenure | `recipient_tenure_days`, `new_recipient_indicator` | Recipient records, transfer events | Compare transfer context to recipient history | Model, fixes | Uses exact personal recipient data instead of synthetic IDs |
| Relationship graph risk | `shared_device_degree`, `shared_recipient_degree`, `entity_graph_risk_score` | Graph edges | Identify repeated synthetic entity reuse | Graph probe, feature fix | Graph leakage across train/holdout |
| Account age/context | `account_age_days`, `account_activity_segment` | Customer/account records | Provide coarse account context | Model | Too correlated with protected or sensitive traits if poorly designed |
| Channel context | `channel`, `channel_change_indicator` | Login/transfer events | Distinguish synthetic web vs app contexts | Model | Device type proxies sensitive attributes if over-specific |
| Sequence timing | `minutes_since_login`, `minutes_since_recovery_event` | Ordered events | Represent temporal order without playbook detail | Model, red-team search | Provides operational narrative if displayed raw |

### 2.4 Label generation model

| Label component | Field name | Description | Example value | Safety constraint | Failure modes |
|---|---|---|---|---|---|
| Base customer risk | `base_customer_risk` | Synthetic prior generated from segment and history | `0.31` | Must not come from real data | Too deterministic by segment |
| Account-access change marker | `account_access_change_marker` | Abstract marker for recent synthetic access change | `1` | No credential or authentication-abuse detail | Becomes operationally specific |
| Device novelty marker | `device_novelty_marker` | Indicates current device differs from synthetic history | `1` | Device IDs are synthetic | Overweights new devices for all customers |
| Security recovery marker | `security_recovery_marker` | Recent synthetic recovery event marker | `1` | Avoid real recovery instructions | Unsafe explanation text |
| Cash-movement velocity marker | `cash_movement_velocity_marker` | Recent transfer intensity marker | `1` | Use amount buckets, not real amounts | Too deterministic; operational wording |
| Entity reuse marker | `entity_reuse_marker` | Relationship graph reuse marker | `1` | Synthetic graph only | Leaks across train/holdout |
| Ring membership marker | `ring_membership_marker` | Hidden synthetic cluster membership for data generation | `0` or `1` | Never show as real-world claim | Model learns hidden label directly |
| Label noise | `label_noise` | Controlled randomness | `0.02` | Seeded and reproducible | Non-reproducible labels |
| Output probability | `synthetic_risk_probability` | Generated risk probability before label threshold | `0.83` | Labeled synthetic | Confused with model score |
| Output label | `synthetic_truth_label` | `normal_activity` or `high_risk_synthetic_activity` | `high_risk_synthetic_activity` | Must never claim production truth | Incorrect class balance |

### 2.5 Synthetic model vulnerability families

| Family ID | Public name | Safe description | How generated | Expected defensive fix | Main metric |
|---|---|---|---|---|---|
| `low_velocity_high_graph_risk` | Low individual activity, high relationship risk | Event looks moderate in isolation, but synthetic graph risk is high | Low velocity features + high relationship degree | Add relationship-risk feature or threshold rule | `model_miss_rate` |
| `recent_change_feature_delay` | Recent change not reflected quickly enough | Recent synthetic behavior change is underweighted by lagged aggregates | Recent events with stale aggregate features | Add streaming recent-change feature | `recall_at_fixed_action_rate` |
| `score_boundary_cluster` | High-risk events near action threshold | High-risk synthetic events cluster just below a decision threshold | Candidate scores near threshold | Adjust thresholding under action-rate limit | `accepted_high_risk_events` |
| `activity_channel_shift` | Under-ranked channel distribution shift | A synthetic activity channel has drifted relative to training | Shift channel mix in holdout | Recalibrate model by channel | `locked_adaptive_holdout_pass` |
| `current_device_mismatch` | Current-device context gap | Current device differs from most-recent login assumption | Generate multi-device session contexts | Add explicit current-device features | `feature_consistency_error_rate` |
| `label_noise_mislearned` | Noisy labels drive poor generalization | Found examples improve but locked holdout does not | Add label noise and duplicate patterns | Governance rejection or retraining with regularization | `drifted_holdout_pass` |
| `overfit_fix_failure` | Fix works only on found examples | Defensive fix improves found set but fails locked holdout | Reuse exact search pattern in found set only | Reject fix; require generalizing feature | `fix_generalization_score` |

---

## 3. Sample Data

A complete sample fixture is saved separately as:

```text
project_atlas_sample_data.json
```

The fixture contains examples for:

- Customers
- Accounts
- Devices
- Recipients
- External accounts
- Graph edges
- Login sessions
- Security events
- Transfer events
- Feature vectors
- Label generation records
- Model vulnerability families
- Model vulnerability cards
- Defensive fix candidates
- Judge reports
- Ledger records

Example excerpt:

```json
{
  "project": {
    "project_name": "Project Atlas",
    "project_folder": "atlas-agentic-fraud-lab",
    "demo_mode": "public",
    "disclaimer": "Synthetic closed-loop demo. No real customers, no real controls, no production endpoints."
  },
  "model_vulnerability_cards": [
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
      "affected_decision_action": "accept"
    }
  ]
}
```

---

## 4. API Schema Summary

A complete OpenAPI 3.1 schema is saved separately as:

```text
project_atlas_openapi.yaml
```

### 4.1 Endpoint inventory

| Endpoint | Method | Purpose | Request body | Response body | Failure modes |
|---|---:|---|---|---|---|
| `/health` | GET | Confirms local API is available | None | `HealthResponse` | API reports healthy while downstream files missing |
| `/config/demo` | GET | Returns public-safe demo labels | None | `DemoConfig` | Public mode leaks internal labels |
| `/schema` | GET | Returns synthetic entity/event/feature schema | None | `SyntheticSchemaResponse` | Schema drift between API and generator |
| `/decision-thresholds` | GET | Returns synthetic thresholds and action-rate limits | None | `DecisionThresholds` | Thresholds mislabeled as production values |
| `/synthetic/generate` | POST | Generates synthetic data from seed | `SyntheticGenerateRequest` | `SyntheticGenerateResponse` | Non-deterministic data; PII-like values |
| `/synthetic/sample` | GET | Returns small public-safe sample | Query `limit` | `SyntheticSampleResponse` | Fixture contains unsafe copy |
| `/score` | POST | Scores one synthetic event | `ScoreRequest` | `ScoreResponse` | Feature order mismatch; invalid event type |
| `/batch-score` | POST | Scores many synthetic events | `BatchScoreRequest` | `BatchScoreResponse` | Batch too large; inconsistent model version |
| `/runs` | POST | Creates a run | `RunCreateRequest` | `RunSummary` | Duplicate run ID; invalid demo mode |
| `/runs` | GET | Lists runs | Query `limit` | `{ runs: RunSummary[] }` | Missing pagination; stale state |
| `/runs/{run_id}` | GET | Returns run detail | Path `run_id` | `RunDetail` | Run not found; corrupt ledger |
| `/runs/{run_id}/rounds` | GET | Lists rounds for a run | Path `run_id` | `{ rounds: RoundSummary[] }` | Round state missing |
| `/runs/{run_id}/rounds/{round_id}` | GET | Returns one round detail | Path `run_id`, `round_id` | `RoundDetail` | Partial round output |
| `/rounds/run` | POST | Executes one or more rounds | `RoundRunRequest` | `RoundRunResponse` | State conflict; failed fix treated as accepted |
| `/red-team/search` | POST | Runs synthetic red-team search | `RedTeamSearchRequest` | `RedTeamSearchResponse` | Exceeds max score queries; invalid event histories |
| `/runs/{run_id}/model-vulnerabilities` | GET | Lists model vulnerability cards | Path `run_id` | `{ model_vulnerabilities: ModelVulnerabilityCard[] }` | Unsafe card text; missing metrics |
| `/model-vulnerabilities/{model_vulnerability_id}` | GET | Returns one model vulnerability card | Path `model_vulnerability_id` | `ModelVulnerabilityCard` | Card not found; stale card version |
| `/defensive-fixes/propose` | POST | Proposes defensive fixes | `DefensiveFixProposalRequest` | `DefensiveFixProposalResponse` | Unsupported fix type; unsafe agent text |
| `/defensive-fixes/apply` | POST | Applies a defensive fix candidate | `DefensiveFixApplyRequest` | `DefensiveFixApplyResponse` | Writes outside allowed files; no rollback |
| `/judge/evaluate-fix` | POST | Deterministically evaluates fix | `JudgeEvaluationRequest` | `JudgeReport` | Uses wrong holdout; metrics not reproducible |
| `/runs/{run_id}/judge-reports/{judge_report_id}` | GET | Returns judge report | Path IDs | `JudgeReport` | Report not found or not linked to ledger |
| `/replay/{run_id}` | GET | Returns web replay payload | Path `run_id` | `ReplayPayload` | Replay differs from judge metrics |
| `/safety/scan` | POST | Runs public-demo safety scan | `SafetyScanRequest` | `SafetyScanResponse` | False negatives on unsafe copy |
| `/model-quality-matrix` | GET | Returns precomputed model-tier comparison | None | `ModelQualityMatrix` | Overclaims exploratory results |

### 4.2 Core API objects

| Object | Description | Required fields | Notes |
|---|---|---|---|
| `ScoreRequest` | One synthetic event plus recomputed features | `event`, `features` | Direct engineered-feature mutation should be rejected outside debug mode |
| `ScoreResponse` | Model score and decision action | `event_id`, `score`, `decision_action`, `model_version`, `threshold_version` | Reason codes must be safe and generic |
| `RedTeamSearchRequest` | Synthetic search request | `run_id`, `round_id`, `max_score_queries`, `search_methods` | Uses `max_score_queries`, not “budget” |
| `ModelVulnerabilityCard` | Evidence card for under-ranked cohort | `model_vulnerability_id`, `family_id`, `model_miss_rate` | Must include denominator and safe cohort definition |
| `DefensiveFixCandidate` | Proposed fix | `defensive_fix_id`, `fix_type`, `description`, `requires_judge_evaluation` | Valid fix types: `feature_fix`, `policy_fix`, `model_calibration_fix` |
| `JudgeReport` | Deterministic fix evaluation | `baseline`, `fixed`, `accepted_by_judge` | Only source of truth for pass/fail |
| `MetricSnapshot` | Metrics at fixed action-rate limit | `recall_at_fixed_action_rate`, `false_positive_rate_at_fixed_action_rate`, `model_miss_rate` | Do not allow agent text to supply these values |
| `SafetyScanResponse` | Safety scan result | `passed`, `findings` | Public mode should fail on internal or unsafe text |

---

## 5. Recommended Build Order for These Components

1. Normalize names: `atlas-agentic-fraud-lab`, `Project Atlas`, `src/atlas/`, `model_vulnerability`, `defensive_fix`, `action_rate_limit`.
2. Create config files first: `demo.yaml`, `safety.yaml`, `synthetic_schema.yaml`, `decision_thresholds.yaml`.
3. Implement safety scanner before agent text generation.
4. Implement synthetic data generator and sample fixture.
5. Implement feature recomputation from events.
6. Implement scorer and decision thresholds.
7. Implement deterministic judge.
8. Implement red-team synthetic search.
9. Implement model vulnerability cards.
10. Implement blue-team defensive fixes.
11. Implement round engine and ledger.
12. Wire API endpoints to real outputs.
13. Connect web app to replay data.
14. Run `make test` and `make safety-scan` before demo.

---

## 6. Safety Requirements Embedded in This Architecture

- All sample records use synthetic IDs only.
- No real bank names, endpoints, credentials, or internal paths are required.
- Red-team simulation-agent modules search synthetic event histories and cannot inspect locked holdout labels.
- Defensive fixes are proposals until the deterministic judge evaluates them.
- Model vulnerability cards must describe under-ranked synthetic cohorts, not real-world instructions.
- Public demo copy must use generic names and a synthetic-only disclaimer.
- API server is local-only by design. The MCP wrapper is local-only by design and calls the same synthetic API surface.
