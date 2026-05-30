// app/web/lib/fixtures.ts
// Typed fixture loader for project_atlas_sample_data.json.
//
// Phase 1 only: every safe placeholder value rendered by the web shell flows
// through one of the accessors below. There are no API calls and no other
// data sources in this phase. When Phase 9 wires the FastAPI replay endpoint
// in, these accessors will keep their signatures and switch their bodies
// from JSON-import to typed `fetch` results.
//
// Field names mirror project_atlas_sample_data.json one-for-one (snake_case),
// so the same shapes can be reused once Pydantic schemas land in
// app/api/schemas/. Do not rename fields here.

import sampleData from "../../../project_atlas_sample_data.json";

import type {
  AtlasSampleData,
  DefensiveFixCandidate,
  FixtureProject,
  JudgeMetricSet,
  JudgeReport,
  LedgerRecord,
  MetricSnapshot,
  ModelVulnerabilityCard,
  SnapshotKind
} from "./types";

// The JSON import is structurally typed by the JSON module loader, but we
// assert against our hand-written interface so the rest of the file gets
// proper field types. tsconfig has resolveJsonModule + strict on; the cast
// is the documented bridge between JSON import shape and our types.
const data = sampleData as unknown as AtlasSampleData;

// ---------------------------------------------------------------------------
// Direct fixture accessors
// ---------------------------------------------------------------------------

export function getFixtureProject(): FixtureProject {
  return data.project;
}

// Entity-count summary for Step 2 environment cards. Counts come from the
// fixture envelope so they update in lockstep when the fixture grows. Phase
// 4 will replace the customer/event counts with totals served by the
// FastAPI /synthetic/sample route; the keys stay stable.
export interface EntityCounts {
  customers: number;
  accounts: number;
  devices: number;
  recipients: number;
  external_accounts: number;
  graph_edges: number;
  login_sessions: number;
  security_events: number;
  transfer_events: number;
}

export function getEntityCounts(): EntityCounts {
  return {
    customers: data.entities.customers.length,
    accounts: data.entities.accounts.length,
    devices: data.entities.devices.length,
    recipients: data.entities.recipients.length,
    external_accounts: data.entities.external_accounts.length,
    graph_edges: data.entities.graph_edges.length,
    login_sessions: data.events.login_sessions.length,
    security_events: data.events.security_events.length,
    transfer_events: data.events.transfer_events.length
  };
}

export function getModelVulnerabilityCards(): ModelVulnerabilityCard[] {
  return data.model_vulnerability_cards;
}

export function getDefensiveFixCandidates(): DefensiveFixCandidate[] {
  return data.defensive_fix_candidates;
}

export function getJudgeReports(): JudgeReport[] {
  return data.judge_reports;
}

export function getLedgerRecords(): LedgerRecord[] {
  return data.ledger_records;
}

// ---------------------------------------------------------------------------
// MetricSnapshot derivation (Phase 1 placeholder)
//
// The fixture contains exactly ONE judge report (round 1). To populate the
// placeholder charts and the round timeline, we derive a four-point series:
//
//   round_id=0, kind="baseline"      — REAL: judge_reports[0].baseline
//   round_id=1, kind="fixed"         — REAL: judge_reports[0].fixed
//   round_id=2, kind="interpolated"  — PLACEHOLDER: dampened continuation
//   round_id=3, kind="interpolated"  — PLACEHOLDER: dampened continuation
//
// The interpolation rule is intentionally trivial (50% diminishing returns
// on each metric's "improvement direction") so it's obvious to a reader of
// the chart code that round 2 and round 3 are not judge-derived. Phase 9
// will replace this whole function with replay data served by FastAPI; the
// MetricSnapshot shape and round_label conventions stay stable so the swap
// is mechanical.
//
// Friction proxies (challenge_rate, alert_rate, decline_rate) are NOT in
// the fixture's judge report — Phase 5+ will compute them from the decision
// overlay against the holdout. Phase 1 fills them with safe constants well
// below the action-rate limits in config/decision_thresholds.yaml so the
// FrictionChart renders with correct shape, and the safety scanner sees
// fixed labels rather than synthesized text. Each value is annotated below.
// ---------------------------------------------------------------------------

const ROUND_LABELS: Record<number, string> = {
  0: "Baseline",
  1: "Round 1",
  2: "Round 2",
  3: "Round 3"
};

// Placeholder friction levels per round.
// All values stay well under config/decision_thresholds.yaml action-rate
// limits (challenge ≤ 8.0%, alert ≤ 15.0%, decline ≤ 25 bps = 0.0025).
// See PROJECT_ATLAS_BIBLE.md §12.4. Real values come from Phase 5 metrics.
interface FrictionTuple {
  challenge_rate: number;
  alert_rate: number;
  decline_rate: number;
}

const PLACEHOLDER_FRICTION: Record<number, FrictionTuple> = {
  0: { challenge_rate: 0.062, alert_rate: 0.104, decline_rate: 0.0014 },
  1: { challenge_rate: 0.065, alert_rate: 0.108, decline_rate: 0.0015 },
  2: { challenge_rate: 0.067, alert_rate: 0.110, decline_rate: 0.0016 },
  3: { challenge_rate: 0.068, alert_rate: 0.111, decline_rate: 0.0017 }
};

// Diminishing-returns extrapolation toward the metric's bounded direction.
// `factor` is the fraction of remaining headroom consumed each round.
function extrapolateToward(current: number, target: number, factor: number): number {
  return current + (target - current) * factor;
}

function buildSnapshot(
  round_id: number,
  kind: SnapshotKind,
  metrics: JudgeMetricSet,
  friction: FrictionTuple
): MetricSnapshot {
  return {
    round_id,
    round_label: ROUND_LABELS[round_id] ?? `Round ${round_id}`,
    kind,
    model_miss_rate: metrics.model_miss_rate,
    recall_at_fixed_action_rate: metrics.recall_at_fixed_action_rate,
    false_positive_rate_at_fixed_action_rate: metrics.false_positive_rate_at_fixed_action_rate,
    synthetic_loss_allowed: metrics.synthetic_loss_allowed,
    challenge_rate: friction.challenge_rate,
    alert_rate: friction.alert_rate,
    decline_rate: friction.decline_rate
  };
}

export function getRoundMetrics(): MetricSnapshot[] {
  const judge = data.judge_reports[0];
  if (!judge) {
    throw new Error(
      "fixtures.ts: project_atlas_sample_data.json is missing judge_reports[0]; " +
        "cannot derive placeholder MetricSnapshot series."
    );
  }

  // Anchors — the only "real" judge-derived numbers on the chart.
  const round0: MetricSnapshot = buildSnapshot(
    0,
    "baseline",
    judge.baseline,
    PLACEHOLDER_FRICTION[0]!
  );
  const round1: MetricSnapshot = buildSnapshot(
    1,
    "fixed",
    judge.fixed,
    PLACEHOLDER_FRICTION[1]!
  );

  // Interpolated continuations. Each metric is pushed toward its natural
  // bound by half the remaining headroom every round:
  //   model_miss_rate, synthetic_loss_allowed, FPR  → toward 0
  //   recall_at_fixed_action_rate                   → toward 1
  // FPR stays flat (no headroom in the fixture); we keep it at the round-1
  // value so the friction story doesn't drift.
  const round2Metrics: JudgeMetricSet = {
    model_miss_rate: extrapolateToward(round1.model_miss_rate, 0, 0.5),
    recall_at_fixed_action_rate: extrapolateToward(round1.recall_at_fixed_action_rate, 1, 0.3),
    false_positive_rate_at_fixed_action_rate: round1.false_positive_rate_at_fixed_action_rate,
    synthetic_loss_allowed: extrapolateToward(round1.synthetic_loss_allowed, 0, 0.5)
  };
  const round2: MetricSnapshot = buildSnapshot(
    2,
    "interpolated",
    round2Metrics,
    PLACEHOLDER_FRICTION[2]!
  );

  const round3Metrics: JudgeMetricSet = {
    model_miss_rate: extrapolateToward(round2.model_miss_rate, 0, 0.5),
    recall_at_fixed_action_rate: extrapolateToward(round2.recall_at_fixed_action_rate, 1, 0.3),
    false_positive_rate_at_fixed_action_rate: round2.false_positive_rate_at_fixed_action_rate,
    synthetic_loss_allowed: extrapolateToward(round2.synthetic_loss_allowed, 0, 0.5)
  };
  const round3: MetricSnapshot = buildSnapshot(
    3,
    "interpolated",
    round3Metrics,
    PLACEHOLDER_FRICTION[3]!
  );

  return [round0, round1, round2, round3];
}
