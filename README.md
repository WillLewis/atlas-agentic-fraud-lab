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

## Quickstart for reviewers

**No API keys required.** Every surface is synthetic and local-only. From a
fresh clone:

```bash
git clone <repo-url> atlas-agentic-fraud-lab
cd atlas-agentic-fraud-lab
make setup        # one-time: install Python + Node dependencies
make bootstrap    # idempotent: seed → train → run-rounds → build-replay → safety-scan
```

Then in two terminals:

```bash
# terminal 1
make demo-api     # starts http://127.0.0.1:8000

# terminal 2
make demo-web     # starts http://localhost:3000
```

`make bootstrap` is the one-command reviewer prep. It probes prerequisites
(Python ≥ 3.11, Node ≥ 18), runs only the missing pipeline steps, and finishes
with the next-step printout. The script is in `scripts/bootstrap_demo.py`; pass
`--check-only` to inspect prereqs and artifact presence without running any
make targets.

## 8–10 minute demo flow

The web app's five sections map to Bible §24 checkpoints. A reviewer watching
the page should see, in roughly this order:

1. **Agents assigned (~1 min)** — Red-team, bank-defense, and deterministic
   judge cards from `config/agent_roster.yaml`. Public-safe agent purposes;
   no human photos; no operational fraud language.
2. **Agents deployed (~1 min)** — Synthetic environment summary from
   `data/synthetic/manifest.json`. Customer / event / graph counts only; no
   PII; no production endpoints.
3. **Round 1 — test and response (~2 min)** — Red-team surfaces the first
   under-ranked synthetic cohort (a `model_vulnerability` card). Bank-defense
   proposes a `defensive_fix` candidate. The judge evaluates it on clean +
   adaptive + locked + drifted holdouts and records its decision. The
   `SafeTranscriptPanel` carries a closed-enum, deterministic transcript
   summary — no raw LLM transcripts ever reach the UI.
4. **Round 2 — adaptive pressure (~2 min)** — Red-team adapts; the judge
   demonstrates that fixes which improve only the found set fail the locked
   adaptive holdout. Action-rate limits are enforced, not advisory.
5. **Round 3 — final report (~2 min)** — Round timeline, four trend charts
   (model_miss_rate, recall_at_fixed_action_rate, synthetic_loss_allowed,
   customer-friction rates), the closed-enum final-report summary card, and
   the read-only `RunComparisonMatrix` projecting `config/model_quality_matrix.yaml`
   into the public-safe tier table.

Pause at any section to read the metric cards and the deterministic judge
notes.

## Limitations

- **No real fraud signal.** All entities, events, and labels are synthetic;
  the model and thresholds are demo constants. Results do not transfer to
  production data.
- **No live agents in the demo path.** The reviewer flow runs Phase 4–10 code
  deterministically against pre-generated synthetic data; agentic search is
  exercised via the existing red-team / blue-team modules with closed-enum
  templates. No external LLM call is made on the `make bootstrap` →
  `make demo-web` path.
- **Model-tier comparison is read-only.** `GET /model-quality-matrix` and the
  `RunComparisonMatrix` UI project tier metadata from
  `config/model_quality_matrix.yaml`. Per-cell `average_*` metrics are
  placeholders; live multi-tier comparison runs are not included in this
  local demo.
- **Locked holdouts are gated.** `src/atlas/judge/holdouts.py` blocks runtime
  access from simulation agents; `.claude/settings.json` denies Claude Code
  reads of locked holdout files.
- **Safety scan is necessary, not sufficient.** `make safety-scan` catches
  banned-institution names, internal paths, secret-shaped tokens, PII shapes,
  unsafe red-team phrasing, and legacy terminology, but a clean scan does not
  prove the demo is safe in every reviewer context. Use the scan in addition
  to manual review of generated-text changes.

## What this project proves / does not prove

(Mirrors `PROJECT_ATLAS_BIBLE.md` §25 — the canonical wording.)

**Proves:**

- Synthetic adaptive search can reveal seeded model vulnerabilities.
- Bank-defense agents can propose useful defensive fix families.
- Deterministic evaluation can separate useful fixes from persuasive but bad
  fixes.
- A polished app can make the red-team / defense loop legible to product,
  model risk, and engineering audiences.

**Does not prove:**

- That any real bank model has these vulnerabilities.
- That any real decision threshold is exposed.
- That synthetic model results generalize to production data.
- That agents should make autonomous production fraud decisions.

## Repository layout

See `PROJECT_ATLAS_BIBLE.md` §10 for the full tree. Top-level surfaces:

- `src/atlas/` — Python simulation, judge, safety, synthetic data, mock model
- `app/api/` — local-only FastAPI service (Phases 4–10)
- `app/web/` — Next.js scrollytelling web app, replay-driven (Phase 9)
- `config/` — YAML config for demo, safety, schema, thresholds, agents, rounds
- `scripts/` — bootstrap, generation, training, rounds, safety scan
- `data/` — synthetic data and fixtures (most paths gitignored)
- `outputs/` — runs, ledgers, vulnerability and fix cards, reports, replays
  (gitignored except `outputs/demo_replays/run_4548ebb8.json` — one curated
  public-safe replay packaged for reviewers)
- `tests/` — unit, integration, safety, fixtures
- `.claude/` — Claude Code settings, hooks, skills, builder subagents

## Status

Implementation phases 1–10 are materially present. Phase status:

- **Phase 1** — five-section Next.js shell with public-safe disclaimer.
- **Phase 2/3** — synthetic generators (customers, events, graph, features,
  labels, splits).
- **Phase 4** — calibrated baseline scorer + decision-threshold overlay +
  FastAPI surface (`/score`, `/batch-score`, `/config/demo`, `/schema`,
  `/decision-thresholds`, `/synthetic/sample`).
- **Phase 5** — code-only deterministic judge (`/judge/evaluate-fix`).
- **Phase 6** — deterministic red-team search (`/red-team/search`) emitting
  public-safe `ModelVulnerabilityCard`s.
- **Phase 7** — bank-defense fix lifecycle (`/defensive-fixes/propose`,
  `/defensive-fixes/apply`).
- **Phase 8** — three-round lifecycle, ledger, replay payload, closed-enum
  transcript summaries (`scripts/run_rounds.py`, `scripts/build_replay.py`).
- **Phase 9** — thin public route surface (`/runs`, `/rounds/run`,
  `/replay/{run_id}`, plus per-run artifact routes), MCP wrappers,
  replay-driven web shell.
- **Phase 10** — `src/atlas/safety/` package, `/safety/scan` +
  `/model-quality-matrix` routes, deterministic rewrite + config-validation
  helpers, public-mode smoke test, demo bootstrap, this README.

Phases 11+ (live agentic LLM calls, multi-tier comparison runs, etc.) are
out of scope for the current local-only demo path and are not implemented.

## Commands

```bash
make setup          # install Python and Node deps
make bootstrap      # one-command reviewer prep flow
make seed           # generate synthetic data            (Phase 2)
make train          # train baseline mock scorer         (Phase 4)
make run-rounds     # run three red-team/defense rounds  (Phase 8)
make build-replay   # prepare web app replay JSON        (Phase 8)
make demo-api       # start local FastAPI                (Phases 4–10)
make demo-web       # start Next.js frontend             (Phases 1, 9)
make test           # run pytest
make safety-scan    # run public-mode safety scan
```

## Safety scan

`make safety-scan` invokes `atlas.safety.scanner` (canonical implementation
under `src/atlas/safety/scanner.py`; `scripts/safety_scan.py` is a stable
shim). It fails public-mode builds for real institution names, internal
paths, endpoint-like secrets, real-PII-shaped strings, unsafe red-team
phrasing, and legacy terminology in public copy. Run it before demos,
commits, fixture changes, generated-text changes, and UI-copy changes.
Claude Code hooks under `.claude/hooks/` also run targeted scans
automatically after relevant edits and before session stop. The same
scanner powers the `POST /safety/scan` HTTP route exposed by the local
FastAPI service.

## Canonical specs

- `CLAUDE.md` — persistent Claude Code instructions
- `PROJECT_ATLAS_BIBLE.md` — product, safety, architecture, and build plan
- `PROJECT_ATLAS_COMPONENT_ARCHITECTURE_DATA_API.md` — file-by-file architecture
- `project_atlas_openapi.yaml` — local-only FastAPI schema
- `project_atlas_sample_data.json` — public-safe sample fixtures
