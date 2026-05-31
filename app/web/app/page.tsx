// app/web/app/page.tsx
// Phase 9 component 8 — replay-driven five-section page.
//
// The page is an async server component. It calls
// `loadActiveReplay(searchParams)` once. Local development fans out to
// 0–3 per-round `getRunRoundDetail(...)` fetches; Cloudflare static
// export uses embedded `round_details` from the curated replay fixture.
// Phase 9 invariant (a)(5): there is NO silent fixture fallback. When
// the replay is missing, the page renders a clear local-only empty state
// with a remediation hint pointing at the right Make target.
//
// Sections 1 (AgentRoster) and 2 (EnvironmentOverview) are static and
// always render (they don't depend on a particular run). Sections 3,
// 4, 5 are replay-backed.
//
// JudgeDecisionCard is reused from Phase 1 — its data shape aligns
// with the persisted judge report. ModelVulnerabilityCard and
// DefensiveFixCard are NOT reused on the live path: the persisted
// records are intentionally slim (Phase 7 manifest TypedDict) and the
// rich cards expect fields that aren't preserved. Instead, slim
// inline renderers below project ONLY the fields actually present in
// the live records — no invented data, no parallel data contract.

import { AgentRoster } from "../components/AgentRoster";
import { AnimatedCardGrid } from "../components/AnimatedCardGrid";
import { TermNote } from "../components/DualLabel";
import { EnvironmentOverview } from "../components/EnvironmentOverview";
import { JudgeDecisionCard } from "../components/JudgeDecisionCard";
import { LeftSidebar } from "../components/LeftSidebar";
import { NarrativeInterlude } from "../components/NarrativeInterlude";
import { FrictionChart } from "../components/charts/FrictionChart";
import { MissRateChart } from "../components/charts/MissRateChart";
import { RecallRecoveryChart } from "../components/charts/RecallRecoveryChart";
import { SyntheticLossChart } from "../components/charts/SyntheticLossChart";
import { AtlasFooter } from "../components/intro/AtlasFooter";
import { AtlasIntro } from "../components/intro/AtlasIntro";
import { getRunRoundDetail } from "../lib/api";
import { formatRate } from "../lib/formatters";
import { FIX_TYPE_PLAIN, GLOSSARY, VULN_FAMILY_LABELS } from "../lib/glossary";
import { familyLabelFromId } from "../lib/ids";
import { isStaticAtlasBuild, loadActiveReplay } from "../lib/replay";
import type { ReplayPayload, RoundDetail, RoundSummary } from "../lib/replay";
import type { JudgeReport, MetricSnapshot } from "../lib/types";

// ---------------------------------------------------------------------------
// Narrative pages — Bible §8
// ---------------------------------------------------------------------------

const NARRATIVE_BREAKS = {
  agentsAssigned: {
    id: "agents-assigned",
    eyebrow: "Agents assigned",
    title: "Agents are assigned roles.",
    lead:
      "Each agent has a limited task before the run starts.",
    paragraphs: [
      "Agents use generated cases, local mock scores, and public-safe summaries. They do not use real customer data, real controls, or production endpoints.",
      "Red agents search for model vulnerabilities. Defense agents propose defensive fixes. The judge decides which results count."
    ],
    criteria: [
      "synthetic data only",
      "defensive fixes only",
      "judge decides"
    ],
    footer: "Scoped agents · limited tools · recorded outcomes",
    watermark: "Roles"
  },
  agentsDeployed: {
    id: "agents-deployed",
    eyebrow: "Agents deployed",
    title: "Agents enter the demo environment.",
    lead:
      "The run uses generated cases, a local mock scorer, and fixed action-rate limits.",
    paragraphs: [
      "Agents can score generated cases and propose defensive fixes. They cannot change the judge criteria or approve their own work.",
      "Each defensive fix is checked for model miss-rate movement, holdout performance, and action-rate limits."
    ],
    criteria: [
      "model miss-rate reduction",
      "holdout performance",
      "within action-rate limits"
    ],
    footer: "Agents propose · judge evaluates",
    watermark: "Run"
  },
  round1: {
    id: "round-1",
    eyebrow: "Round 1 response",
    title: "Round 1 produces a rejected fix.",
    lead:
      "The red agents identify an under-ranked cohort. Defense proposes a decision-threshold defensive fix, and the judge rejects it.",
    paragraphs: [
      "The fix does not pass the full evaluation. It is not carried forward.",
      "The model vulnerability remains recorded so the next round can test another defensive fix."
    ],
    footer: "Rejected defensive fix",
    watermark: "Round 1"
  },
  round2: {
    id: "round-2",
    eyebrow: "Round 2 response",
    title: "Round 2 tests another defensive fix.",
    lead:
      "Defense proposes a different fix, and the judge evaluates it against holdouts and action-rate limits.",
    paragraphs: [
      "The accepted state improves missed risky activity while staying inside the configured limits.",
      "The result is based on judge output, not an agent summary."
    ],
    footer: "Accepted state updated",
    watermark: "Round 2"
  },
  round3: {
    id: "round-3",
    eyebrow: "Round 3 · final report",
    title: "Round 3 records the final state.",
    lead:
      "The judge reports final metrics, holdout results, and customer-friction rates.",
    paragraphs: [
      "The final report lists the accepted state and the remaining synthetic assumptions.",
      "It is a decision record for review, not a separate agent opinion."
    ],
    footer: "Final metrics · holdouts · action-rate limits",
    watermark: "Round 3"
  }
} as const;

// ---------------------------------------------------------------------------
// Page entry
// ---------------------------------------------------------------------------

export default async function HomePage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = isStaticAtlasBuild() ? {} : await searchParams;
  const result = await loadActiveReplay(params);

  return (
    <>
      <AtlasIntro />
      <div className="atlas-demo-shell flex">
        <LeftSidebar />
        <main className="atlas-demo-main min-w-0 flex-1">
          <NarrativeInterlude {...NARRATIVE_BREAKS.agentsAssigned} />
          <AgentRoster sectionId="agents-assigned-details" showHeader={false} />

          {result.kind === "ready" ? (
            <ReadyReplayBody payload={result.payload} />
          ) : (
            <EmptyOrErrorState
              kind={result.kind}
              reason={result.reason}
              remediation={result.remediation}
            />
          )}
        </main>
      </div>
      <AtlasFooter />
    </>
  );
}

// ---------------------------------------------------------------------------
// Ready: replay-driven sections 3–5
// ---------------------------------------------------------------------------

async function ReadyReplayBody({
  payload
}: {
  payload: ReplayPayload;
}) {
  const run_id = payload.run.run_id;
  const rounds = payload.run.rounds ?? [];
  const metrics: MetricSnapshot[] = payload.charts.round_metrics ?? [];

  const detailEntries = await loadRoundDetailEntries(payload, rounds, run_id);
  const detailByRound = new Map<number, RoundDetail | null>(detailEntries);
  const candidateMetrics = buildSelectedCandidateMetrics(metrics, detailByRound);

  return (
    <>
      <NarrativeInterlude {...NARRATIVE_BREAKS.agentsDeployed} />
      <EnvironmentOverview sectionId="agents-deployed-details" showHeader={false} />

      <NarrativeInterlude {...NARRATIVE_BREAKS.round1} />

      {/* Round 1 evidence */}
      <RoundSection
        id="round-1-details"
        round={rounds.find((r) => r.round_id === 1)}
        detail={detailByRound.get(1) ?? null}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
      />

      <NarrativeInterlude {...NARRATIVE_BREAKS.round2} />

      {/* Round 2 evidence */}
      <RoundSection
        id="round-2-details"
        round={rounds.find((r) => r.round_id === 2)}
        detail={detailByRound.get(2) ?? null}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
      />

      <NarrativeInterlude {...NARRATIVE_BREAKS.round3} />

      {/* Round 3 evidence + final report */}
      <FinalReportSection
        id="round-3-details"
        round={rounds.find((r) => r.round_id === 3)}
        detail={detailByRound.get(3) ?? null}
        payload={payload}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
      />

    </>
  );
}

async function loadRoundDetailEntries(
  payload: ReplayPayload,
  rounds: RoundSummary[],
  run_id: string
): Promise<Array<readonly [number, RoundDetail | null]>> {
  const embeddedDetails = payload.round_details ?? [];
  if (embeddedDetails.length > 0) {
    const byRound = new Map(
      embeddedDetails.map((detail) => [detail.round_id, detail] as const)
    );
    return rounds.map((round) => [
      round.round_id,
      byRound.get(round.round_id) ?? null
    ] as const);
  }

  // Local-only API path. A 404 on any one round becomes a `null`
  // entry so the section renders the slim round_summary fallback
  // instead of crashing the page.
  return Promise.all(
    rounds.map(async (r) => {
      try {
        const detail = await getRunRoundDetail(run_id, r.round_id);
        return [r.round_id, detail] as const;
      } catch {
        return [r.round_id, null] as const;
      }
    })
  );
}

function buildSelectedCandidateMetrics(
  metrics: MetricSnapshot[],
  detailByRound: Map<number, RoundDetail | null>
): MetricSnapshot[] {
  return metrics.map((snapshot) => {
    if (snapshot.round_id === 0) return snapshot;
    const report = detailByRound.get(snapshot.round_id)?.judge_reports?.[0];
    if (!report) return snapshot;
    return {
      ...snapshot,
      kind: "fixed",
      model_miss_rate: report.fixed.model_miss_rate,
      recall_at_fixed_action_rate: report.fixed.recall_at_fixed_action_rate,
      false_positive_rate_at_fixed_action_rate:
        report.fixed.false_positive_rate_at_fixed_action_rate,
      synthetic_loss_allowed: report.fixed.synthetic_loss_allowed
    };
  });
}

// ---------------------------------------------------------------------------
// Round section (Sections 3 and 4)
// ---------------------------------------------------------------------------

function RoundSection({
  id,
  round,
  detail,
  metrics,
  candidateMetrics
}: {
  id: string;
  round: RoundSummary | undefined;
  detail: RoundDetail | null;
  metrics: MetricSnapshot[];
  candidateMetrics: MetricSnapshot[];
}) {
  return (
    <section
      id={id}
      aria-label={round ? `Round ${round.round_id} evidence` : "Round evidence"}
      className="atlas-data-section border-t border-atlas-border/40 px-8 py-16"
    >
      {round === undefined ? (
        <RoundNotRunYet />
      ) : (
        <>
          {/* Slim cards strip — vulnerabilities, fixes, judge */}
          <AnimatedCardGrid
            className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3"
            itemClassNames={[
              "min-w-0",
              "min-w-0",
              "min-w-0 xl:col-span-2 2xl:col-span-1"
            ]}
          >
            <SlimVulnerabilityCard
              records={detail?.model_vulnerabilities ?? []}
              round_id={round.round_id}
            />
            <SlimFixCard
              records={detail?.defensive_fixes ?? []}
              round_id={round.round_id}
            />
            <RoundJudgeCard reports={detail?.judge_reports ?? []} />
          </AnimatedCardGrid>

          {/* Chart strip — focused subset for round-level reading */}
          <AnimatedCardGrid
            className="grid grid-cols-1 gap-4 lg:grid-cols-2"
            itemClassName="min-w-0"
          >
            <ChartCard
              title="Missed risky activity"
              hint="model miss rate · Lower is better. Solid = accepted state; dashed = proposed fix before judge decision."
            >
              <MissRateChart
                metrics={metrics}
                candidate_metrics={candidateMetrics}
              />
            </ChartCard>
            <ChartCard
              title="Risky activity caught"
              hint="recall at fixed action-rate · Higher is better. Solid = accepted state; dashed = proposed fix before judge decision."
            >
              <RecallRecoveryChart
                metrics={metrics}
                candidate_metrics={candidateMetrics}
              />
            </ChartCard>
          </AnimatedCardGrid>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Final report section (Section 5)
// ---------------------------------------------------------------------------

function FinalReportSection({
  id,
  round,
  detail,
  payload,
  metrics,
  candidateMetrics
}: {
  id: string;
  round: RoundSummary | undefined;
  detail: RoundDetail | null;
  payload: ReplayPayload;
  metrics: MetricSnapshot[];
  candidateMetrics: MetricSnapshot[];
}) {
  const finalReportCard = findFinalReportCard(payload);

  return (
    <>
      <section
        id={id}
        aria-label="Round 3 final report evidence"
        className="atlas-data-section border-t border-atlas-border/40 px-8 py-16"
      >
        {round !== undefined ? (
          <>
            {/* Round 3 cards strip */}
            <AnimatedCardGrid
              className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3"
              itemClassNames={[
                "min-w-0",
                "min-w-0",
                "min-w-0 xl:col-span-2 2xl:col-span-1"
              ]}
            >
              <SlimVulnerabilityCard
                records={detail?.model_vulnerabilities ?? []}
                round_id={round.round_id}
              />
              <SlimFixCard
                records={detail?.defensive_fixes ?? []}
                round_id={round.round_id}
              />
              <RoundJudgeCard reports={detail?.judge_reports ?? []} />
            </AnimatedCardGrid>

          </>
        ) : (
          <div className="mb-8">
            <RoundNotRunYet />
          </div>
        )}

        <AnimatedCardGrid className="mb-4 grid grid-cols-1" itemClassName="min-w-0">
          <ChartReadingGuide />
        </AnimatedCardGrid>

        {/* All four charts in a 2x2 grid */}
        <AnimatedCardGrid
          className="mb-10 grid grid-cols-1 gap-4 lg:grid-cols-2"
          itemClassName="min-w-0"
        >
          <ChartCard
            title="Missed risky activity"
            hint="model miss rate · Lower is better. Solid = accepted state; dashed = proposed fix before judge decision."
          >
            <MissRateChart
              metrics={metrics}
              candidate_metrics={candidateMetrics}
            />
          </ChartCard>
          <ChartCard
            title="Risky activity caught"
            hint="recall at fixed action-rate · Higher is better. Solid = accepted state; dashed = proposed fix before judge decision."
          >
            <RecallRecoveryChart
              metrics={metrics}
              candidate_metrics={candidateMetrics}
            />
          </ChartCard>
          <ChartCard
            title={GLOSSARY.synthetic_loss_allowed.plain}
            hint="synthetic loss allowed · Lower is better. Solid = accepted state; dashed = proposed fix. SYN $ is scaled play-money only."
          >
            <SyntheticLossChart
              metrics={metrics}
              candidate_metrics={candidateMetrics}
            />
          </ChartCard>
          <ChartCard
            title="How often we interrupt customers"
            hint="customer-friction rates · Lower interruption is better when risk capture holds. Lines track action-rate limits."
          >
            <FrictionChart metrics={metrics} />
          </ChartCard>
        </AnimatedCardGrid>
      </section>

      {finalReportCard ? (
        <FinalReportNarrativePage
          card={finalReportCard}
          payload={payload}
          metrics={metrics}
        />
      ) : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Slim renderers — work directly off persisted records (no invented fields)
// ---------------------------------------------------------------------------

function SlimVulnerabilityCard({
  records,
  round_id
}: {
  records: Record<string, unknown>[];
  round_id: number;
}) {
  const filtered = records.filter((r) => r.round_id === round_id);
  if (filtered.length === 0) {
    return (
      <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-5 text-xs text-atlas-muted">
        <header title={GLOSSARY.model_vulnerabilities.definition}>
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
            {GLOSSARY.model_vulnerabilities.plain}
          </p>
          <TermNote>{GLOSSARY.model_vulnerabilities.term}</TermNote>
        </header>
        <p className="mt-3 italic">No vulnerabilities recorded for this round.</p>
      </article>
    );
  }

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-danger/40 bg-atlas-panel/60 p-5">
      <header className="border-b border-atlas-border/60 pb-3" title={GLOSSARY.model_vulnerabilities.definition}>
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-danger">
          {GLOSSARY.model_vulnerabilities.plain} · Round {round_id}
        </p>
        <TermNote>{GLOSSARY.model_vulnerabilities.term}</TermNote>
        <p className="mt-1 font-mono text-[11px] text-atlas-muted">
          {filtered.length} record{filtered.length === 1 ? "" : "s"} persisted
        </p>
      </header>
      <ul className="mt-3 space-y-3">
        {filtered.map((r, i) => {
          const id = String(r.model_vulnerability_id ?? "");
          const family = String(r.family_id ?? "");
          const summary = String(r.summary ?? "");
          const missRate = typeof r.model_miss_rate === "number" ? r.model_miss_rate : null;
          const recommended = Array.isArray(r.recommended_defensive_fix_types)
            ? (r.recommended_defensive_fix_types as string[])
            : [];
          return (
            <li
              key={slimRecordKey(r, i, "model_vulnerability_id")}
              className="rounded-md border border-atlas-border/60 bg-atlas-surface/40 p-3"
              title={id}
            >
              <p className="text-sm font-semibold text-atlas-text">
                {VULN_FAMILY_LABELS[family] ?? family}
              </p>
              <p className="font-mono text-[10px] text-atlas-muted">family · {family}</p>
              {summary ? (
                <p className="mt-2 text-xs leading-relaxed text-atlas-text/90">{summary}</p>
              ) : null}
              {missRate !== null ? (
                <div className="mt-2" title={GLOSSARY.model_miss_rate.definition}>
                  <p className="font-mono text-[11px] text-atlas-muted">
                    Missed risky activity ·{" "}
                    <span className="text-atlas-text">{(missRate * 100).toFixed(1)}%</span>
                  </p>
                  <TermNote>{GLOSSARY.model_miss_rate.term}</TermNote>
                </div>
              ) : null}
              {recommended.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {recommended.map((t) => (
                    <span
                      key={t}
                      title={t}
                      className="rounded-full border border-atlas-accent/40 bg-atlas-accent/10 px-2 py-0.5 text-[10px] text-atlas-accent"
                    >
                      {FIX_TYPE_PLAIN[t] ?? t}
                    </span>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </article>
  );
}

function slimRecordKey(
  r: Record<string, unknown>,
  index: number,
  primaryField: "model_vulnerability_id" | "defensive_fix_id"
): string {
  return [
    r.run_id,
    r.round_id,
    r[primaryField],
    r.fix_type,
    r.vulnerability_id,
    JSON.stringify(r.proposed_threshold_overrides ?? {}),
    JSON.stringify(r.expected_rate_limit_claim ?? {}),
    index
  ]
    .map((part) => String(part ?? ""))
    .join("|");
}

function SlimFixCard({
  records,
  round_id
}: {
  records: Record<string, unknown>[];
  round_id: number;
}) {
  const filtered = records.filter((r) => r.round_id === round_id);
  if (filtered.length === 0) {
    return (
      <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-5 text-xs text-atlas-muted">
        <header title={GLOSSARY.defensive_fix_candidates.definition}>
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
            {GLOSSARY.defensive_fix_candidates.plain}
          </p>
          <TermNote>{GLOSSARY.defensive_fix_candidates.term}</TermNote>
        </header>
        <p className="mt-3 italic">No defensive fixes proposed for this round.</p>
      </article>
    );
  }

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-accent/40 bg-atlas-panel/60 p-5">
      <header className="border-b border-atlas-border/60 pb-3" title={GLOSSARY.defensive_fix_candidates.definition}>
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-accent">
          {GLOSSARY.defensive_fix_candidates.plain} · Round {round_id}
        </p>
        <TermNote>{GLOSSARY.defensive_fix_candidates.term}</TermNote>
        <p className="mt-1 font-mono text-[11px] text-atlas-muted">
          {filtered.length} fix option{filtered.length === 1 ? "" : "s"} persisted
        </p>
      </header>
      <ul className="mt-3 space-y-3">
        {filtered.map((r, i) => {
          const id = String(r.defensive_fix_id ?? "");
          const fixType = String(r.fix_type ?? "");
          const vulnerabilityId = String(r.vulnerability_id ?? "");
          const targetFamilyLabel = familyLabelFromId(vulnerabilityId);
          const overrides = (r.proposed_threshold_overrides ?? {}) as Record<
            string,
            number
          >;
          return (
            <li
              key={slimRecordKey(r, i, "defensive_fix_id")}
              className="rounded-md border border-atlas-border/60 bg-atlas-surface/40 p-3"
              title={id}
            >
              <p className="text-sm font-semibold text-atlas-text">
                {FIX_TYPE_PLAIN[fixType] ?? fixType}
              </p>
              <p className="font-mono text-[10px] text-atlas-muted">fix_type · {fixType}</p>
              {vulnerabilityId ? (
                <>
                  <p className="mt-1 text-[11px] text-atlas-text/90">
                    Addresses model vulnerability{targetFamilyLabel ? `: ${targetFamilyLabel}` : ""}
                  </p>
                  <p className="font-mono text-[10px] text-atlas-muted" title={vulnerabilityId}>
                    targets · model vulnerability
                  </p>
                </>
              ) : null}
              {Object.keys(overrides).length > 0 ? (
                <div className="mt-2 font-mono text-[11px] text-atlas-muted">
                  overrides:
                  <ul className="mt-1 space-y-0.5">
                    {Object.entries(overrides).map(([k, v]) => (
                      <li key={k}>
                        <span className="text-atlas-muted">{k}: </span>
                        <span className="text-atlas-text">{v}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </article>
  );
}

function RoundJudgeCard({ reports }: { reports: JudgeReport[] }) {
  const report = reports[0];
  if (!report) {
    return (
      <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-5 text-xs text-atlas-muted">
        <header title={GLOSSARY.judge_decision.definition}>
          <p className="text-xs font-medium text-atlas-text">
            {GLOSSARY.judge_decision.plain}
          </p>
          <TermNote>{GLOSSARY.judge_decision.term}</TermNote>
        </header>
        <p className="mt-3 italic">No judge report recorded for this round.</p>
      </article>
    );
  }
  // One fix is evaluated per round — render the first report.
  return <JudgeDecisionCard report={report} />;
}

// ---------------------------------------------------------------------------
// Final-report narrative page
// ---------------------------------------------------------------------------

function findFinalReportCard(
  payload: ReplayPayload
): Record<string, unknown> | null {
  const step5 = payload.five_step_story.find((s) => s.step_id === 5);
  if (!step5) return null;
  const card = step5.cards.find((c) => c.category === "final_report");
  return card ?? null;
}

function FinalReportNarrativePage({
  card,
  payload,
  metrics
}: {
  card: Record<string, unknown>;
  payload: ReplayPayload;
  metrics: MetricSnapshot[];
}) {
  const acceptedCount = typeof card.accepted_count === "number" ? card.accepted_count : null;
  const trend = finalReportMissRateTrend(card, metrics);
  const firstMissRate = finiteMetricOrNull(trend[0]);
  const finalMissRate = finiteMetricOrNull(trend[trend.length - 1]);
  const missRateDelta =
    firstMissRate !== null && finalMissRate !== null
      ? firstMissRate - finalMissRate
      : null;
  const completedRounds =
    payload.run.rounds.filter((r) => r.status === "completed").length ||
    payload.run.current_round ||
    metrics.filter((m) => m.round_id > 0).length;
  const safetyOk = card.safety_scan_passed === true;
  const trendSummary =
    firstMissRate !== null && finalMissRate !== null && missRateDelta !== null
      ? `Model miss rate changed from ${formatRate(firstMissRate, { digits: 1 })} to ${formatRate(finalMissRate, { digits: 1 })}, a ${formatPercentagePointChange(missRateDelta)}.`
      : "The final report shows judge-derived metrics without extra run metadata.";
  const acceptedSummary =
    acceptedCount !== null
      ? `The judge accepted ${acceptedCount} defensive fix${acceptedCount === 1 ? "" : "es"} after checking holdouts and action-rate limits.`
      : "The judge records which defensive fixes pass holdout checks and action-rate limits.";

  return (
    <NarrativeInterlude
      id="final-report-narrative"
      eyebrow="Final report"
      title="Final report summary."
      lead="This section summarizes the accepted run state and removes run metadata that is not needed for review."
      paragraphs={[
        trendSummary,
        acceptedSummary,
        "The record uses synthetic data, local mock scoring, locked holdout checks, and the safety scan result."
      ]}
      criteria={[
        `${completedRounds} synthetic rounds completed`,
        acceptedCount !== null
          ? `${acceptedCount} defensive fixes accepted`
          : "defensive fixes judged",
        firstMissRate !== null && finalMissRate !== null
          ? `${formatRate(firstMissRate, { digits: 1 })} to ${formatRate(finalMissRate, { digits: 1 })} model miss rate`
          : "model miss rate recorded",
        safetyOk ? "safety scan passed" : "safety scan recorded"
      ]}
      footer="Judge metrics · synthetic assumptions · action-rate limits"
      watermark="Final"
    />
  );
}

function finalReportMissRateTrend(
  card: Record<string, unknown>,
  metrics: MetricSnapshot[]
): number[] {
  if (Array.isArray(card.miss_rate_trend)) {
    return card.miss_rate_trend.filter(
      (value): value is number => typeof value === "number" && Number.isFinite(value)
    );
  }
  return metrics
    .map((snapshot) => snapshot.model_miss_rate)
    .filter((value) => Number.isFinite(value));
}

function formatPercentagePointChange(delta: number): string {
  const direction = delta >= 0 ? "reduction" : "increase";
  return `${Math.abs(delta * 100).toFixed(1)} percentage-point ${direction}`;
}

function finiteMetricOrNull(value: number | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

// ---------------------------------------------------------------------------
// Empty / error state
// ---------------------------------------------------------------------------

function EmptyOrErrorState({
  kind,
  reason
}: {
  kind: "empty" | "error";
  reason: string;
  remediation: string | null;
}) {
  const tone = kind === "empty" ? "muted" : "danger";
  const displayReason = standaloneLoadReason(kind, reason);
  return (
    <section
      id="empty-state"
      aria-label={kind === "empty" ? "No demo data available" : "Demo load error"}
      className="atlas-data-section scroll-mt-16 border-t border-atlas-border/40 px-8 py-24"
    >
      <div className="mx-auto max-w-2xl rounded-lg border border-atlas-border bg-atlas-panel/60 p-8 text-center">
        <p
          className={[
            "font-mono text-[10px] uppercase tracking-widest",
            tone === "danger" ? "text-atlas-danger" : "text-atlas-muted"
          ].join(" ")}
        >
          {kind === "empty" ? "Nothing to show yet" : "Couldn't load the demo"}
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-atlas-text">
          {kind === "empty"
            ? "This demo hasn't loaded its data yet."
            : "Couldn't load the demo data."}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">{displayReason}</p>
        <p className="mt-6 text-[11px] text-atlas-muted/80">
          This is a self-contained demo.
        </p>
      </div>
    </section>
  );
}

function standaloneLoadReason(kind: "empty" | "error", reason: string): string {
  if (/No completed run found/i.test(reason)) {
    return "No completed demo run is available yet.";
  }
  if (/No completed demo run currently meets the publish criteria/i.test(reason)) {
    return "No completed demo run currently meets the publish criteria.";
  }
  if (/No replay artifacts found/i.test(reason)) {
    return "The selected demo run does not have display data yet.";
  }
  if (kind === "error" && /(Failed to list runs|fetch failed|ATLAS API)/i.test(reason)) {
    return "The demo data service is not responding yet.";
  }
  return reason
    .replace(/\brun_[a-z0-9_]+/gi, "the selected run")
    .replace(/\breplay artifacts\b/gi, "demo data");
}

function RoundNotRunYet() {
  return (
    <div className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-6 text-sm text-atlas-muted">
      <p className="font-mono text-[10px] uppercase tracking-widest">
        This round hasn&apos;t run yet
      </p>
      <p className="mt-2">Run the demo to populate this round.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

function ChartReadingGuide() {
  return (
    <aside className="mb-4 rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        Chart reading key
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 text-xs leading-relaxed text-atlas-muted md:grid-cols-2 xl:grid-cols-4">
        <div className="flex gap-2">
          <span
            aria-hidden="true"
            className="mt-2 inline-block h-0 w-8 shrink-0 border-t-2 border-solid border-atlas-text"
          />
          <span>
            Solid line shows the accepted state carried forward after each judge
            decision.
          </span>
        </div>
        <div className="flex gap-2">
          <span
            aria-hidden="true"
            className="mt-2 inline-block h-0 w-8 shrink-0 border-t-2 border-dashed border-atlas-accent"
          />
          <span>
            Dashed blue line shows the proposed defensive fix before the judge
            decision.
          </span>
        </div>
        <div>
          Dots are judge-derived replay snapshots from baseline through the
          synthetic rounds.
        </div>
        <div>
          Each chart header states whether moving up or down is the better
          outcome.
        </div>
      </div>
    </aside>
  );
}

function ChartCard({
  title,
  hint,
  children
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <article className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <header>
        <h3 className="text-sm font-semibold text-atlas-text">{title}</h3>
        {hint ? <p className="mt-0.5 text-[11px] text-atlas-muted">{hint}</p> : null}
      </header>
      <div className="mt-4">{children}</div>
    </article>
  );
}
