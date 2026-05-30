// app/web/lib/replay.ts
// Phase 9 TypeScript types + replay-loading orchestrators.
//
// Field names are 1:1 with `src/atlas/ledger/replay.py`,
// `app/api/schemas/run.py`, and the OpenAPI definitions in
// `project_atlas_openapi.yaml`. Keep snake_case throughout — DO NOT
// rename to camelCase. Tests in `tests/unit/test_phase8_replay.py`
// pin the contract on the Python side; `npm run typecheck` pins it
// here.

import { AtlasApiError, getDemoCaseSearchReport, getReplay, getRuns } from "./api";
import type {
  DemoMode,
  JudgeReport,
  MetricSnapshot,
} from "./types";

// Re-export so component 6 can `import { MetricSnapshot } from "@/lib/replay"`.
export type { MetricSnapshot };

// ---------------------------------------------------------------------------
// Run / round shapes
// ---------------------------------------------------------------------------

export type RunStatus = "created" | "running" | "completed" | "failed";

export interface RunSummary {
  run_id: string;
  seed: number;
  demo_mode: DemoMode | string;
  status: RunStatus;
  current_round?: number;
  created_at_utc?: string;
}

export interface RoundSummary {
  run_id: string;
  round_id: number;
  status: string;
  model_version_before?: string;
  model_version_after?: string;
  model_miss_rate_before?: number;
  model_miss_rate_after?: number;
  recall_at_fixed_action_rate_before?: number;
  recall_at_fixed_action_rate_after?: number;
}

export interface RunDetail extends RunSummary {
  rounds: RoundSummary[];
  latest_metrics?: MetricSnapshot | null;
}

export interface RoundDetail extends RoundSummary {
  // Persisted slim shapes (Phase 7 ``ModelVulnerabilityRecord`` TypedDict
  // and ``DefensiveFixManifest`` dataclass) — narrower than the OpenAPI
  // ``ModelVulnerabilityCard`` / ``DefensiveFixCandidate`` schemas. The
  // route layer surfaces these records verbatim; the web shell reads
  // only the fields actually present.
  model_vulnerabilities: Record<string, unknown>[];
  defensive_fixes: Record<string, unknown>[];
  // Persisted judge reports DO match the rich JudgeReport schema
  // (Phase 5 writer), so they keep their typed shape here.
  judge_reports: JudgeReport[];
  // Phase 9 (b)#8 reconciliation: closed-enum transcript surfaced via
  // RoundDetail rather than a separate /transcripts endpoint.
  transcript_summary?: string;
  safety_scan_passed?: boolean;
}

// ---------------------------------------------------------------------------
// Five-step story + replay envelope
// ---------------------------------------------------------------------------
//
// `cards` is intentionally a permissive `Record<string, unknown>[]` —
// the per-step card shapes are open and authored by
// `src/atlas/ledger/replay.py:_step1_agents_assigned` /
// `_step2_environment` / `_step_round` / `_step5_final_round_with_report`.
// Component 8 narrows them at the consumer site.

export interface FiveStepStoryStep {
  step_id: number;
  title: string;
  cards: Record<string, unknown>[];
}

export interface ReplayCharts {
  round_metrics: MetricSnapshot[];
  // Open-shaped per Phase 8 contract; component 7 extends if needed.
  [key: string]: unknown;
}

export interface ReplayPayload {
  run: RunDetail;
  five_step_story: FiveStepStoryStep[];
  charts: ReplayCharts;
}

// ---------------------------------------------------------------------------
// Empty-state helpers
// ---------------------------------------------------------------------------
//
// Used by component 6 to render the local-only "no replay yet" UI
// instead of silently falling back to fixture data on the live page.
// Phase 9 invariant (a)(5).

export type ReplayLoadResult =
  | { kind: "ready"; payload: ReplayPayload }
  | { kind: "empty"; reason: string; remediation: string }
  | { kind: "error"; reason: string; remediation: string | null };

export function selectLatestCompletedRun(
  runs: RunSummary[],
): RunSummary | null {
  const completed = runs.filter((r) => r.status === "completed");
  if (completed.length === 0) return null;
  // Stable: caller should already have ordered runs; tie-break on
  // run_id so tests are deterministic regardless of filesystem order.
  completed.sort((a, b) => {
    const ta = a.created_at_utc ?? "";
    const tb = b.created_at_utc ?? "";
    if (ta !== tb) return tb.localeCompare(ta);
    return b.run_id.localeCompare(a.run_id);
  });
  return completed[0] ?? null;
}

// ---------------------------------------------------------------------------
// Run-selection + replay-loading orchestrators
// ---------------------------------------------------------------------------
//
// The page-level server component in component 8 calls
// ``loadActiveReplay(searchParams)`` and renders one of three states:
//   * kind="ready"  — render the five-step story + charts.
//   * kind="empty"  — local-only "no replay yet" UI when there is no
//                     completed replay to review. NEVER fall back to
//                     fixture data.
//   * kind="error"  — surface the upstream error (e.g. dev forgot to
//                     run ``make demo-api``).

type SearchParams = Record<string, string | string[] | undefined>;

type PromotedRunSelection =
  | { kind: "selected"; run_id: string }
  | { kind: "none" }
  | { kind: "unavailable" };

async function readPromotedRunSelection(): Promise<PromotedRunSelection> {
  try {
    const report = await getDemoCaseSearchReport();
    if (report.selected === null) {
      return { kind: "none" };
    }
    const run_id = report.selected?.run_id;
    if (typeof run_id === "string" && run_id.length > 0) {
      return { kind: "selected", run_id };
    }
  } catch {
    // Fall back to latest-completed-run selection for local development
    // when the API does not expose a search report.
  }

  return { kind: "unavailable" };
}

/** Pick the run_id for the live page.
 *
 * Precedence:
 *   1. ``searchParams.run_id`` (string or first element of array).
 *   2. ``selectLatestCompletedRun(runs)``.
 *   3. ``null`` — caller should render an empty state.
 */
export function selectActiveRun(
  searchParams: SearchParams,
  runs: RunSummary[],
): string | null {
  const param = searchParams.run_id;
  const candidate = Array.isArray(param) ? param[0] : param;
  if (typeof candidate === "string" && candidate.length > 0) {
    return candidate;
  }
  const latest = selectLatestCompletedRun(runs);
  return latest?.run_id ?? null;
}

/** Load a single run's replay payload, mapping 404s to ``{kind:"empty"}``
 * so callers don't have to catch ``AtlasApiError`` themselves.
 */
export async function loadReplayForRun(
  run_id: string,
): Promise<ReplayLoadResult> {
  try {
    const payload = await getReplay(run_id);
    return { kind: "ready", payload };
  } catch (err) {
    if (err instanceof AtlasApiError && err.status === 404) {
      return {
        kind: "empty",
        reason: `No replay artifacts found for run ${run_id}.`,
        remediation: "make run-rounds && make build-replay",
      };
    }
    return {
      kind: "error",
      reason: err instanceof Error ? err.message : String(err),
      remediation:
        err instanceof AtlasApiError ? err.remediation : "make demo-api",
    };
  }
}

/** Top-level entry point for the live page. Pulls the run list, picks
 * the active run, and loads its replay. Returns a discriminated
 * ``ReplayLoadResult`` the page renders directly.
 */
export async function loadActiveReplay(
  searchParams: SearchParams,
): Promise<ReplayLoadResult> {
  let runs: RunSummary[];
  try {
    const out = await getRuns();
    runs = out.runs;
  } catch (err) {
    return {
      kind: "error",
      reason:
        err instanceof Error
          ? `Failed to list runs: ${err.message}`
          : String(err),
      remediation: "make demo-api",
    };
  }

  const param = searchParams.run_id;
  const explicitRunId = Array.isArray(param) ? param[0] : param;
  if (typeof explicitRunId === "string" && explicitRunId.length > 0) {
    return loadReplayForRun(explicitRunId);
  }

  const promoted = await readPromotedRunSelection();
  if (promoted.kind === "selected") {
    return loadReplayForRun(promoted.run_id);
  }

  const run_id = selectActiveRun(searchParams, runs);
  if (run_id === null) {
    return {
      kind: "empty",
      reason:
        promoted.kind === "none"
          ? "No completed demo run currently meets the publish criteria."
          : "No completed run found.",
      remediation:
        promoted.kind === "none"
          ? "make search-demo-case"
          : "make seed && make train && make run-rounds && make build-replay",
    };
  }
  return loadReplayForRun(run_id);
}
