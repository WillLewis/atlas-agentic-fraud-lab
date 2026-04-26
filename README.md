# Project Atlas

**Synthetic demo. Not a production fraud system. Not fraud advice.**

Project Atlas is a closed-loop, synthetic red/blue fraud-model evaluation arena.
Red-team simulation agents run constrained synthetic searches against a local
mock account-takeover risk scorer. Bank-defense simulation agents propose
defensive fixes. A deterministic judge — not an agent — decides whether each
fix improves recall at fixed action-rate limits without exceeding configured
customer-friction limits.

The web app tells the story in five public-safe steps: agents assigned, agents
deployed, round 1 response, round 2 response, round 3 final report.

## What this project is

- A synthetic, defensive evaluation harness for studying agentic red-team
  testing and agentic bank defense against a mock fraud model.
- A reproducible, seeded simulation: same seed, same ledger.
- A demonstration that agents may propose, but only deterministic code
  decides.

## What this project is not

- Not a production fraud system.
- Not a source of operational fraud guidance.
- Not connected to any real bank, customer, account, or scoring endpoint.
- Not a claim that any specific institution has the modeled vulnerabilities.

See `PROJECT_ATLAS_BIBLE.md` §5 (non-goals) and §6 (safety doctrine) for the
full safety contract.

## Default mode

```bash
DEMO_MODE=public
```

Public mode uses generic labels (`RetailBank-X`, `Mock Account-Takeover Risk
Scorer`), synthetic identifiers only, and demo-constant decision thresholds.
Internal mode (`DEMO_MODE=internal`) may discuss business relevance but must
still use only synthetic data.

## Repository layout

See `PROJECT_ATLAS_BIBLE.md` §10 for the full tree. Top-level surfaces:

- `src/atlas/` — Python simulation, judge, safety, synthetic data, mock model
- `app/api/` — local-only FastAPI service
- `app/web/` — Next.js scrollytelling web app
- `config/` — YAML config for demo, safety, schema, thresholds, agents, rounds
- `scripts/` — bootstrap, generation, training, rounds, safety scan
- `data/` — synthetic data and fixtures (most paths gitignored)
- `outputs/` — runs, ledgers, vulnerability and fix cards, reports, replays
- `tests/` — unit, integration, safety, fixtures
- `.claude/` — Claude Code settings, hooks, skills, builder subagents

## Status

Phase 0 — repo skeleton, configs, and safety scan stub. Implementation phases
1–10 are scoped in `PROJECT_ATLAS_BIBLE.md` §18.

## Commands

```bash
make setup          # install Python and Node deps
make seed           # generate synthetic data            (Phase 2)
make train          # train baseline mock scorer         (Phase 4)
make run-rounds     # run three red-team/defense rounds  (Phase 8)
make build-replay   # prepare web app replay JSON        (Phase 8)
make demo-api       # start local FastAPI                (Phase 4)
make demo-web       # start Next.js frontend             (Phase 1)
make test           # run pytest
make safety-scan    # run public-mode safety scan
```

Targets that depend on later phases print a `TODO` notice until those phases
land.

## Safety scan

`make safety-scan` runs `scripts/safety_scan.py`, which fails public-mode
builds for real institution names, internal paths, endpoint-like secrets,
real-PII-shaped strings, unsafe red-team phrasing, and legacy terminology in
public copy. Run it before demos, commits, fixture changes, generated-text
changes, and UI-copy changes. Claude Code hooks under `.claude/hooks/` also
run targeted scans automatically after relevant edits and before session
stop.

## Canonical specs

- `CLAUDE.md` — persistent Claude Code instructions
- `PROJECT_ATLAS_BIBLE.md` — product, safety, architecture, and build plan
- `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md` — file-by-file architecture
- `project_atlas_openapi.yaml` — local-only FastAPI schema
- `project_atlas_sample_data.json` — public-safe sample fixtures
