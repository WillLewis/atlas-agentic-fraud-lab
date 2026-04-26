# AGENTS.md
Persistent Codex instructions for **Project Atlas**.

## Agent-file routing
- This file is the OpenAI Codex instruction manifest for Project Atlas.
- Codex reads `AGENTS.md` automatically; use this file as Codex's primary always-loaded context.
- `CLAUDE.md` is the Claude Code instruction manifest and shared cross-agent contract.
- Codex should read `CLAUDE.md` only for major work, architecture or safety changes, cross-agent handoffs, or when the user explicitly asks for Claude/Codex alignment.
- Claude Code should use `CLAUDE.md` and should not read, summarize, or reference this file during normal work.

## Project identity
- Project name: **Project Atlas**
- Project folder: `atlas-agentic-fraud-lab`
- Python package: `src/atlas/`
- Default mode: `DEMO_MODE=public`
- Build goal: a synthetic, defensive red/blue fraud-model evaluation web app.
- Public claim: agents can identify synthetic model vulnerabilities and propose defensive fixes; deterministic code measures recall and customer-friction effects.

## Canonical files
Read the relevant canonical file before major changes:
- `CLAUDE.md` — Claude Code instructions and shared cross-agent contract; Codex reads it only when the task needs Claude/Codex alignment or touches shared architecture/safety rules.
- `PROJECT_ATLAS_BIBLE.md` — product, safety, architecture, and build plan.
- `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md` — file-by-file architecture, synthetic data model, and API summary.
- `project_atlas_sample_data.json` — public-safe sample entities, events, features, labels, model vulnerability cards, defensive fix candidates, judge reports, and ledger records.
- `project_atlas_openapi.yaml` — local-only FastAPI schema.
- `PROJECT_ATLAS_COMPONENT_ARCHITECTURE.xlsx` — spreadsheet version of the component architecture.

## Public terminology standard
Use `.Codex/skills/atlas-terminology/SKILL.md` for the detailed terminology map. In always-loaded context, preserve the core public terms: `model_vulnerability`, `defensive_fix`, `action_rate_limit`, `scoring_query_limit`, `decision_threshold`, `model_miss_rate`, `red_team_test`, `synthetic_search`, and `under_ranked_cohort`. Legacy terms may appear only in safety filters or terminology maps.

## Non-negotiable safety rules
1. Synthetic data only. Never use, request, import, infer, or simulate from real customer data.
2. Local mock APIs only. Never call or configure production endpoints.
3. Never include real institution-specific thresholds, rules, endpoint URLs, credentials, internal repo paths, warehouse tables, model names, or private source identifiers.
4. Public mode must use generic labels such as `RetailBank-X` and `Mock Account-Takeover Risk Scorer`.
5. Do not generate operational fraud guidance. Red-team content stays at the level of synthetic feature-space model vulnerabilities.
6. Do not describe phishing, credential theft, MFA bypass, account takeover steps, SIM swapping, social engineering, or money-movement abuse.
7. Agents may propose; deterministic code decides.
8. Holdouts are locked. Do not expose locked holdout labels or records to simulation agents; `src/atlas/judge/holdouts.py` handles runtime gating and `.Codex/settings.json` denies Codex reads of locked holdout files.
9. Red-team search mutates synthetic event histories, then recomputes features.
10. Direct engineered-feature mutation is debug-only and disabled in public mode.
11. Run `make safety-scan` before demos, commits, generated-text changes, API-response changes, fixture changes, or UI-copy changes. Codex hooks also run targeted scans after relevant writes and before session stop.

## First actions each session
1. Inspect repo state: `pwd`, `git status`, and relevant directory listings.
2. Read this file.
3. For major, safety-sensitive, architecture, or cross-agent work, read `CLAUDE.md` before other project references.
4. For major work, read `PROJECT_ATLAS_BIBLE.md`.
5. For file-level work, read `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md`.
6. For API work, read `project_atlas_openapi.yaml`.
7. For fixture or replay work, inspect `project_atlas_sample_data.json`.
8. Produce a short plan before edits, build the smallest coherent vertical slice, then run targeted tests and safety checks.

## Required repo structure
```text
atlas-agentic-fraud-lab/
  CLAUDE.md
  AGENTS.md
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
  .Codex/
    settings.json
    agents/
    hooks/
      safety_scan_changed_files.py
      safety_scan_pending.py
    skills/
      atlas-terminology/SKILL.md
      atlas-safety-doctrine/SKILL.md
      atlas-metrics/SKILL.md
      atlas-fraud-typologies/SKILL.md
      atlas-fixture-shape/SKILL.md
  app/web/
  app/api/
  config/
  src/atlas/
  data/
  outputs/
  tests/
  scripts/
```

## Key configs
Use `config/demo.yaml`, `config/safety.yaml`, `config/synthetic_schema.yaml`, `config/decision_thresholds.yaml`, `config/agent_roster.yaml`, `config/round_config.yaml`, and `config/model_quality_matrix.yaml`.

## Codex project controls
- `.Codex/settings.json` owns Codex permissions and hooks.
- `.Codex/hooks/` runs targeted safety scans after relevant edits and before session stop.
- `.Codex/skills/` holds derived, lazy-loaded operational knowledge from the Bible.
- `.Codex/agents/` contains builder subagents only; they assist development and never participate in a Project Atlas round.
- `.mcp.json` exposes only the local Atlas development MCP wrapper over the local FastAPI service.

## Architecture invariants
- `simulation_agents` are runtime Python modules under `src/atlas/red_team/`, `src/atlas/blue_team/`, and related orchestration code. They may call the Anthropic API during a round and must return structured Pydantic-compatible outputs.
- `builder_subagents` are Codex helpers under `.Codex/agents/`. They assist the human developer only and never participate in a Project Atlas round.
- `src/atlas/judge/` owns metrics and defensive fix acceptance.
- `src/atlas/safety/` owns scanning, config validation, and unsafe-output filtering.
- `src/atlas/synthetic/` owns generated data, event histories, features, labels, splits, and graph records.
- `src/atlas/model/` owns training, scoring, calibration, and decision-threshold overlay.
- `src/atlas/red_team/` owns synthetic candidate search only.
- `src/atlas/blue_team/` owns defensive fix proposal and application.
- `src/atlas/ledger/` owns run records, replay data, and reports.
- `outputs/` is generated and should be gitignored except curated public-safe replay fixtures.
- Never mix private source identifiers or non-project artifacts into app code, fixtures, outputs, or prompts.

## Build order
1. Repo skeleton, configs, `.Codex/settings.json`, `.Codex/hooks/`, `.Codex/skills/`, `.mcp.json`, and `scripts/safety_scan.py`.
2. Five-section web shell.
3. Synthetic customer/event/graph generator.
4. Feature calculator.
5. Baseline mock model and decision-threshold overlay.
6. FastAPI local mock scorer.
7. Deterministic judge.
8. Red-team random/evolutionary/graph search.
9. Model vulnerability cards.
10. Bank-defense feature/threshold/model-calibration fixes.
11. Three-round engine and ledger.
12. Web integration with replay data.
13. Model-tier comparison.
14. Safety hardening and demo polish.

## Commands to implement
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
If a command does not exist, create it or add a Makefile TODO. Do not claim it works until it runs.

## Safety scanner must fail public-mode builds for
- Real institution names in public-facing generated text.
- Private/internal filenames, internal repo paths, internal domains, cloud-storage paths, warehouse-style table names, auth-token strings, or endpoint-like secrets.
- Text that reads like real phishing, credential theft, MFA bypass, account takeover, social engineering, or money-movement abuse.
- Generated records that look like real PII.
- Public copy using legacy terms where clearer terms are required.

## Red-team rules
Allowed: generate synthetic event histories, search configured model vulnerability families, use local mock scorer outputs, measure accepted high-risk synthetic events, and package safe model vulnerability cards.
Disallowed: real tactics, production controls, credential or account-access instructions, real decision thresholds, real customer identifiers, and direct engineered-feature mutation as the main algorithm.

## Bank-defense rules
Allowed defensive fix families: decision-threshold fix under fixed action-rate limits; feature fix from synthetic event histories or relationship graph features; model calibration or retraining fix using allowed synthetic data.
Every defensive fix must be evaluated by `src/atlas/judge/` on clean holdout, found adaptive set, locked adaptive holdout, and drifted holdout. Reject fixes that improve found examples but fail locked holdout or exceed customer-friction limits.

## Metrics must be code-derived
Use only judge-derived values for `model_miss_rate`, `miss_rate_lift_vs_random`, `recall_at_fixed_action_rate`, `false_positive_rate_at_fixed_action_rate`, `challenge_rate`, `alert_rate`, `decline_rate`, `synthetic_loss_allowed`, `synthetic_loss_prevented`, and `fix_generalization_score`.
Agent summaries must not invent or overwrite metrics.

## Web app requirements
The frontend tells five steps: agents assigned, agents deployed, round 1 response, round 2 response, round 3 final report. Use a left sidebar, abstract icons only, synthetic loss charts, agent cards, model vulnerability cards, defensive fix cards, judge cards, ledger cards, and public-safe copy.

## API requirements
Follow `project_atlas_openapi.yaml`. Keep all endpoints local-only. The project-scoped MCP wrapper in `.mcp.json` may invoke the same local-only endpoints for development tooling. Important groups: `/config/demo`, `/schema`, `/decision-thresholds`, `/synthetic/generate`, `/score`, `/batch-score`, `/runs`, `/rounds/run`, `/red-team/search`, `/model-vulnerabilities/{model_vulnerability_id}`, `/defensive-fixes/propose`, `/defensive-fixes/apply`, `/judge/evaluate-fix`, `/replay/{run_id}`, `/safety/scan`, and `/model-quality-matrix`.

## Coding and fixture standards
Prefer typed Python with small functions. Use Pydantic models for API schemas. Use deterministic seeds in tests and replay. Keep config in YAML or JSON. Avoid hidden randomness in judge or replay logic. Write tests for metric formulas, decision thresholds, holdout handling, and safety filters. Keep UI copy in structured data so safety scan can inspect it.
Use `project_atlas_sample_data.json` as the fixture shape and naming guide. Synthetic IDs should look like `cust_000001`, `acct_000001`, `dev_000001`, `recipient_000001`, `mv_round1_001`, and `fix_round1_graph_risk_feature`.

## Commit and demo hygiene
Before suggesting a commit or demo:
```bash
make test
make safety-scan
git status
```
Never commit `.env`, API keys, local sensitive notebooks, real source artifacts, or generated data that has not passed safety scan.

## Ambiguous requests
If asked for more red-team detail, implement only the safe synthetic abstraction.
Unsafe: “show how the fraud agent gets around controls.”
Safe: “show that the red-team agent found a synthetic under-ranked cohort and how the bank-defense agent reduced model miss rate at a fixed action-rate limit.”

## Final invariant
Project Atlas succeeds only if it is useful to fraud and ML practitioners while remaining safe to show externally. Preserve this in every file, route, fixture, chart, agent prompt, and transcript.
