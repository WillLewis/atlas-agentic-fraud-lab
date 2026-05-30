// app/web/lib/modelQualityMatrix.ts
// Server-side, typed loader for config/model_quality_matrix.yaml.
//
// Phase 9 component 8 — RunComparisonMatrix reads from this loader. The
// data is read-only and PUBLIC-SAFE: tier labels only. Concrete model
// identifiers under `tier_models.*` are surfaced ONLY when
// `expose_concrete_model_names: true` (private demo configuration).
// NO live model-tier comparison generation happens here; cells with a
// source_run_id derive display metrics from curated replay artifacts.
//
// Mirrors `app/web/lib/demoConfig.ts` patterns: Node fs/path APIs,
// module-level memoization, schema validation with `<source>: field`
// errors.

import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";

// ---------------------------------------------------------------------------
// Public types — field names mirror the YAML keys exactly.
// ---------------------------------------------------------------------------

export interface MatrixTier {
  id: "frontier" | "compact";
  label: string;
  description: string;
  public_safe_label: string;
}

export interface MatrixRun {
  run_label: string;
  red_team_tier: "frontier" | "compact";
  bank_defense_tier: "frontier" | "compact";
  purpose: string;
  source_run_id: string | null;
  metrics_source: "judge_derived_replay" | "unavailable";
  metrics_status:
    | "loaded"
    | "no_source_run"
    | "source_unavailable"
    | "incomplete_source";
  average_model_miss_rate: number | null;
  average_recall_recovery_points: number | null;
  fixed_action_rate_pass: boolean | null;
}

export interface ModelQualityMatrix {
  model_quality_matrix_version: string;
  tiers: MatrixTier[];
  expose_concrete_model_names: boolean;
  runs: MatrixRun[];
  summary_templates: string[];
}

// ---------------------------------------------------------------------------
// Resolution + validation
// ---------------------------------------------------------------------------

const REPO_ROOT_FROM_APP_WEB = path.resolve("..", "..");
const DEFAULT_CONFIG_PATH = path.join(
  REPO_ROOT_FROM_APP_WEB, "config", "model_quality_matrix.yaml",
);
const DEFAULT_REPLAY_ROOT = path.join(
  REPO_ROOT_FROM_APP_WEB, "outputs", "demo_replays",
);
const DEFAULT_DECISION_THRESHOLDS_PATH = path.join(
  REPO_ROOT_FROM_APP_WEB, "config", "decision_thresholds.yaml",
);

function resolveConfigPath(): string {
  const explicit = process.env.ATLAS_MODEL_QUALITY_MATRIX;
  if (explicit && explicit.length > 0) return path.resolve(explicit);
  return DEFAULT_CONFIG_PATH;
}

function fail(field: string, expected: string, source: string): never {
  throw new Error(
    `config/model_quality_matrix.yaml at ${source}: field "${field}" is missing or not ${expected}.`,
  );
}

function asString(raw: unknown, field: string, source: string): string {
  if (typeof raw !== "string" || raw.length === 0) {
    fail(field, "a non-empty string", source);
  }
  return raw;
}

function asBoolean(raw: unknown, field: string, source: string): boolean {
  if (typeof raw !== "boolean") fail(field, "a boolean", source);
  return raw;
}

function asObject(raw: unknown, field: string, source: string): Record<string, unknown> {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    fail(field, "an object", source);
  }
  return raw as Record<string, unknown>;
}

function asArray(raw: unknown, field: string, source: string): unknown[] {
  if (!Array.isArray(raw)) fail(field, "an array", source);
  return raw;
}

function asTierId(raw: unknown, field: string, source: string): "frontier" | "compact" {
  const v = asString(raw, field, source);
  if (v !== "frontier" && v !== "compact") {
    throw new Error(
      `config/model_quality_matrix.yaml at ${source}: ${field} must be "frontier" or "compact"; got "${v}".`,
    );
  }
  return v;
}

function asOptionalString(raw: unknown, field: string, source: string): string | null {
  if (raw === undefined || raw === null) return null;
  return asString(raw, field, source);
}

function asMetricsSource(
  raw: unknown,
  field: string,
  source: string,
): "judge_derived_replay" | "unavailable" {
  const v = asString(raw, field, source);
  if (v !== "judge_derived_replay" && v !== "unavailable") {
    throw new Error(
      `config/model_quality_matrix.yaml at ${source}: ${field} must be "judge_derived_replay" or "unavailable"; got "${v}".`,
    );
  }
  return v;
}

function finiteNumber(raw: unknown): number | null {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  return raw;
}

function roundTo(value: number, places: number): number {
  const scale = 10 ** places;
  return Math.round(value * scale) / scale;
}

function safeSourceRunId(raw: string | null): string | null {
  if (raw === null || raw.length === 0) return null;
  if (raw.includes("/") || raw.includes("\\") || raw.startsWith(".")) return null;
  return raw;
}

interface DerivedRunMetrics {
  metrics_source: "judge_derived_replay" | "unavailable";
  metrics_status:
    | "loaded"
    | "no_source_run"
    | "source_unavailable"
    | "incomplete_source";
  average_model_miss_rate: number | null;
  average_recall_recovery_points: number | null;
  fixed_action_rate_pass: boolean | null;
}

interface ReplayMetricSnapshot {
  round_id?: unknown;
  kind?: unknown;
  model_miss_rate?: unknown;
  recall_at_fixed_action_rate?: unknown;
  challenge_rate?: unknown;
  alert_rate?: unknown;
  decline_rate?: unknown;
}

function unavailableMetrics(
  status: DerivedRunMetrics["metrics_status"],
): DerivedRunMetrics {
  return {
    metrics_source: "unavailable",
    metrics_status: status,
    average_model_miss_rate: null,
    average_recall_recovery_points: null,
    fixed_action_rate_pass: null,
  };
}

function loadActionRateLimits(): Record<string, number> | null {
  if (!fs.existsSync(DEFAULT_DECISION_THRESHOLDS_PATH)) return null;
  const parsed = parseYaml(
    fs.readFileSync(DEFAULT_DECISION_THRESHOLDS_PATH, "utf8"),
  ) as Record<string, unknown>;
  const limits = parsed.action_rate_limits as Record<string, unknown> | undefined;
  if (limits === undefined || limits === null || typeof limits !== "object") {
    return null;
  }
  const challenge = finiteNumber(limits.challenge_rate_limit_pct);
  const alert = finiteNumber(limits.alert_rate_limit_pct);
  const declineBps = finiteNumber(limits.decline_rate_limit_bps);
  if (challenge === null || alert === null || declineBps === null) return null;
  return {
    challenge_rate: challenge / 100,
    alert_rate: alert / 100,
    decline_rate: declineBps / 10000,
  };
}

function loadReplaySnapshots(source_run_id: string): ReplayMetricSnapshot[] | null {
  const replayPath = path.join(DEFAULT_REPLAY_ROOT, `${source_run_id}.json`);
  if (!fs.existsSync(replayPath)) return null;
  const parsed = JSON.parse(fs.readFileSync(replayPath, "utf8")) as {
    charts?: { round_metrics?: unknown };
  };
  const snapshots = parsed.charts?.round_metrics;
  if (!Array.isArray(snapshots)) return null;
  return snapshots.filter(
    (snapshot): snapshot is ReplayMetricSnapshot =>
      snapshot !== null && typeof snapshot === "object",
  );
}

function deriveReplayMetrics(source_run_id: string | null): DerivedRunMetrics {
  if (source_run_id === null) return unavailableMetrics("no_source_run");
  const snapshots = loadReplaySnapshots(source_run_id);
  if (snapshots === null || snapshots.length === 0) {
    return unavailableMetrics("source_unavailable");
  }
  const baseline = snapshots.find(
    (s) => s.kind === "baseline" || s.round_id === 0,
  );
  const fixed = snapshots.filter(
    (s) => s.kind === "fixed" && (finiteNumber(s.round_id) ?? 0) > 0,
  );
  if (baseline === undefined || fixed.length === 0) {
    return unavailableMetrics("incomplete_source");
  }

  const missValues = fixed.map((s) => finiteNumber(s.model_miss_rate));
  const baselineRecall = finiteNumber(baseline.recall_at_fixed_action_rate);
  const finalRecall = finiteNumber(
    fixed[fixed.length - 1]?.recall_at_fixed_action_rate,
  );
  const limits = loadActionRateLimits();
  if (
    missValues.some((v) => v === null) ||
    baselineRecall === null ||
    finalRecall === null ||
    limits === null
  ) {
    return unavailableMetrics("incomplete_source");
  }

  const actionRatesComplete = fixed.every((snapshot) =>
    Object.keys(limits).every((rateName) =>
      finiteNumber(snapshot[rateName as keyof ReplayMetricSnapshot]) !== null,
    ),
  );
  if (!actionRatesComplete) return unavailableMetrics("incomplete_source");

  const fixedActionRatePass = fixed.every((snapshot) =>
    Object.entries(limits).every(([rateName, limit]) => {
      const value = finiteNumber(snapshot[rateName as keyof ReplayMetricSnapshot]);
      return value !== null && value <= limit + 1e-12;
    }),
  );

  const numericMissValues = missValues.filter((v): v is number => v !== null);
  const averageMissRate =
    numericMissValues.reduce((sum, value) => sum + value, 0) /
    numericMissValues.length;
  return {
    metrics_source: "judge_derived_replay",
    metrics_status: "loaded",
    average_model_miss_rate: roundTo(averageMissRate, 4),
    average_recall_recovery_points: roundTo(
      (finalRecall - baselineRecall) * 100,
      4,
    ),
    fixed_action_rate_pass: fixedActionRatePass,
  };
}

function validateTiers(raw: unknown, source: string): MatrixTier[] {
  const tiersObj = asObject(raw, "tiers", source);
  const out: MatrixTier[] = [];
  for (const id of ["frontier", "compact"] as const) {
    const tier = asObject(tiersObj[id], `tiers.${id}`, source);
    out.push({
      id,
      label: asString(tier.label, `tiers.${id}.label`, source),
      description: asString(tier.description, `tiers.${id}.description`, source),
      public_safe_label: asString(
        tier.public_safe_label, `tiers.${id}.public_safe_label`, source,
      ),
    });
  }
  return out;
}

function validateRuns(raw: unknown, source: string): MatrixRun[] {
  const runsArr = asArray(raw, "runs", source);
  return runsArr.map((rawRun, i) => {
    const run = asObject(rawRun, `runs[${i}]`, source);
    const configuredSource = asMetricsSource(
      run.metrics_source, `runs[${i}].metrics_source`, source,
    );
    const source_run_id = safeSourceRunId(
      asOptionalString(run.source_run_id, `runs[${i}].source_run_id`, source),
    );
    const derived =
      configuredSource === "judge_derived_replay"
        ? deriveReplayMetrics(source_run_id)
        : unavailableMetrics("no_source_run");
    return {
      run_label: asString(run.run_label, `runs[${i}].run_label`, source),
      red_team_tier: asTierId(
        run.red_team_tier, `runs[${i}].red_team_tier`, source,
      ),
      bank_defense_tier: asTierId(
        run.bank_defense_tier, `runs[${i}].bank_defense_tier`, source,
      ),
      purpose: asString(run.purpose, `runs[${i}].purpose`, source),
      source_run_id,
      ...derived,
    };
  });
}

function validateSummaryTemplates(raw: unknown, source: string): string[] {
  if (raw === undefined || raw === null) return [];
  const arr = asArray(raw, "summary_templates", source);
  return arr.map((line, i) =>
    asString(line, `summary_templates[${i}]`, source),
  );
}

function validate(raw: unknown, source: string): ModelQualityMatrix {
  const root = asObject(raw, "<root>", source);
  return {
    model_quality_matrix_version: asString(
      root.model_quality_matrix_version,
      "model_quality_matrix_version",
      source,
    ),
    tiers: validateTiers(root.tiers, source),
    expose_concrete_model_names: asBoolean(
      root.expose_concrete_model_names, "expose_concrete_model_names", source,
    ),
    runs: validateRuns(root.runs, source),
    summary_templates: validateSummaryTemplates(root.summary_templates, source),
  };
}

// ---------------------------------------------------------------------------
// Public API — module-level memoization mirrors demoConfig.ts.
// ---------------------------------------------------------------------------

let cached: ModelQualityMatrix | null = null;

export function getModelQualityMatrix(): ModelQualityMatrix {
  if (cached !== null) return cached;
  const configPath = resolveConfigPath();
  const raw = fs.readFileSync(configPath, "utf8");
  const parsed = parseYaml(raw) as unknown;
  cached = validate(parsed, configPath);
  return cached;
}

export function clearModelQualityMatrixCache(): void {
  cached = null;
}
