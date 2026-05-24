// app/web/app/page.tsx
// Phase 9 component 8 — replay-driven five-section page.
//
// The page is an async server component. It calls
// `loadActiveReplay(searchParams)` once and fans out to 0–3 per-round
// `getRunRoundDetail(...)` fetches in parallel for the rich
// JudgeDecisionCard + slim vulnerability/fix renderings. Phase 9
// invariant (a)(5): there is NO silent fixture fallback. When the
// replay is missing, the page renders a clear local-only empty state
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
import { TermNote } from "../components/DualLabel";
import { EnvironmentOverview } from "../components/EnvironmentOverview";
import { JudgeDecisionCard } from "../components/JudgeDecisionCard";
import { LeftSidebar } from "../components/LeftSidebar";
import { RoundTimeline } from "../components/RoundTimeline";
import { RunComparisonMatrix } from "../components/RunComparisonMatrix";
import { SafeTranscriptPanel } from "../components/SafeTranscriptPanel";
import { FrictionChart } from "../components/charts/FrictionChart";
import { MissRateChart } from "../components/charts/MissRateChart";
import { RecallRecoveryChart } from "../components/charts/RecallRecoveryChart";
import { SyntheticLossChart } from "../components/charts/SyntheticLossChart";
import { getRunRoundDetail } from "../lib/api";
import { FIX_TYPE_PLAIN, GLOSSARY, VULN_FAMILY_LABELS } from "../lib/glossary";
import { getModelQualityMatrix } from "../lib/modelQualityMatrix";
import { loadActiveReplay } from "../lib/replay";
import type { ReplayPayload, RoundDetail, RoundSummary } from "../lib/replay";
import type { JudgeReport, MetricSnapshot } from "../lib/types";

// ---------------------------------------------------------------------------
// Section narrative — Bible §8
// ---------------------------------------------------------------------------

interface SectionNarrative {
  eyebrow: string;
  term: string;
  title: string;
  subtitle: string;
}

const ROUND_NARRATIVE: Record<1 | 2 | 3, SectionNarrative> = {
  1: {
    eyebrow: "Step 3",
    term: "Round 1 — Test and Response",
    title: "Round 1 — Find it, fix it, check it",
    subtitle:
      "The stress-test agents find the model's first weak spot; the defense agents propose a fix; the code referee checks the improvement is real, not memorized."
  },
  2: {
    eyebrow: "Step 4",
    term: "Round 2 — Adaptive Pressure",
    title: "Round 2 — Turn up the pressure",
    subtitle:
      "The agents adapt; the defense responds; the hidden stress test is now the pass/fail gate."
  },
  3: {
    eyebrow: "Step 5",
    term: "Round 3 — Final Report",
    title: "Round 3 — Final scorecard",
    subtitle:
      "Final numbers, the run record, and a side-by-side comparison across AI model tiers."
  }
};

// ---------------------------------------------------------------------------
// Page entry
// ---------------------------------------------------------------------------

export default async function HomePage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const result = await loadActiveReplay(params);
  const matrix = getModelQualityMatrix();

  return (
    <div className="flex">
      <LeftSidebar />
      <main className="min-w-0 flex-1">
        <AgentRoster />
        <EnvironmentOverview />

        {result.kind === "ready" ? (
          <ReadyReplayBody payload={result.payload} matrix={matrix} />
        ) : (
          <EmptyOrErrorState
            kind={result.kind}
            reason={result.reason}
            remediation={result.remediation}
          />
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ready: replay-driven sections 3–5
// ---------------------------------------------------------------------------

async function ReadyReplayBody({
  payload,
  matrix
}: {
  payload: ReplayPayload;
  matrix: ReturnType<typeof getModelQualityMatrix>;
}) {
  const run_id = payload.run.run_id;
  const rounds = payload.run.rounds ?? [];
  const metrics: MetricSnapshot[] = payload.charts.round_metrics ?? [];

  // Fan out per-round detail fetches in parallel. A 404 on any one
  // round becomes a `null` entry so the section renders the slim
  // round_summary fallback instead of crashing the page.
  const detailEntries = await Promise.all(
    rounds.map(async (r) => {
      try {
        const detail = await getRunRoundDetail(run_id, r.round_id);
        return [r.round_id, detail] as const;
      } catch {
        return [r.round_id, null] as const;
      }
    })
  );
  const detailByRound = new Map<number, RoundDetail | null>(detailEntries);
  const candidateMetrics = buildSelectedCandidateMetrics(metrics, detailByRound);

  return (
    <>
      {/* Section 3 — Round 1 */}
      <RoundSection
        id="round-1"
        narrative={ROUND_NARRATIVE[1]}
        round={rounds.find((r) => r.round_id === 1)}
        detail={detailByRound.get(1) ?? null}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
      />

      {/* Section 4 — Round 2 */}
      <RoundSection
        id="round-2"
        narrative={ROUND_NARRATIVE[2]}
        round={rounds.find((r) => r.round_id === 2)}
        detail={detailByRound.get(2) ?? null}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
      />

      {/* Section 5 — Round 3 + final report */}
      <FinalReportSection
        id="round-3"
        narrative={ROUND_NARRATIVE[3]}
        round={rounds.find((r) => r.round_id === 3)}
        detail={detailByRound.get(3) ?? null}
        payload={payload}
        metrics={metrics}
        candidateMetrics={candidateMetrics}
        matrix={matrix}
      />
    </>
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
  narrative,
  round,
  detail,
  metrics,
  candidateMetrics
}: {
  id: string;
  narrative: SectionNarrative;
  round: RoundSummary | undefined;
  detail: RoundDetail | null;
  metrics: MetricSnapshot[];
  candidateMetrics: MetricSnapshot[];
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="scroll-mt-16 border-t border-atlas-border/40 px-8 py-16"
    >
      <header className="mb-8 max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          {narrative.eyebrow}
        </p>
        <h2
          id={`${id}-heading`}
          className="mt-2 text-3xl font-semibold tracking-tight text-atlas-text"
        >
          {narrative.title}
        </h2>
        <p className="mt-1 font-mono text-[11px] text-atlas-muted">{narrative.term}</p>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">
          {narrative.subtitle}
        </p>
      </header>

      {round === undefined ? (
        <RoundNotRunYet />
      ) : (
        <>
          {/* Slim cards strip — vulnerabilities, fixes, judge */}
          <div className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
            <div className="min-w-0">
              <SlimVulnerabilityCard
                records={detail?.model_vulnerabilities ?? []}
                round_id={round.round_id}
              />
            </div>
            <div className="min-w-0">
              <SlimFixCard
                records={detail?.defensive_fixes ?? []}
                round_id={round.round_id}
              />
            </div>
            <div className="min-w-0 xl:col-span-2 2xl:col-span-1">
              <RoundJudgeCard reports={detail?.judge_reports ?? []} />
            </div>
          </div>

          {/* Sanitized transcript */}
          {detail?.transcript_summary ? (
            <div className="mb-8">
              <SafeTranscriptPanel
                summary={detail.transcript_summary}
                safety_scan_passed={detail.safety_scan_passed ?? true}
                round_label={`Round ${round.round_id}`}
              />
            </div>
          ) : null}

          {/* Chart strip — focused subset for round-level reading */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard
              title="Missed risky activity"
              hint="model miss rate · Lower is better. Carry-forward state plus selected candidate result."
            >
              <MissRateChart
                metrics={metrics}
                candidate_metrics={candidateMetrics}
              />
            </ChartCard>
            <ChartCard
              title="Risky activity caught"
              hint="recall at fixed action-rate · Higher is better. Carry-forward state plus selected candidate result."
            >
              <RecallRecoveryChart
                metrics={metrics}
                candidate_metrics={candidateMetrics}
              />
            </ChartCard>
          </div>
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
  narrative,
  round,
  detail,
  payload,
  metrics,
  candidateMetrics,
  matrix
}: {
  id: string;
  narrative: SectionNarrative;
  round: RoundSummary | undefined;
  detail: RoundDetail | null;
  payload: ReplayPayload;
  metrics: MetricSnapshot[];
  candidateMetrics: MetricSnapshot[];
  matrix: ReturnType<typeof getModelQualityMatrix>;
}) {
  const finalReportCard = findFinalReportCard(payload);

  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className="scroll-mt-16 border-t border-atlas-border/40 px-8 py-16"
    >
      <header className="mb-10 max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          {narrative.eyebrow}
        </p>
        <h2
          id={`${id}-heading`}
          className="mt-2 text-3xl font-semibold tracking-tight text-atlas-text"
        >
          {narrative.title}
        </h2>
        <p className="mt-1 font-mono text-[11px] text-atlas-muted">{narrative.term}</p>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">
          {narrative.subtitle}
        </p>
      </header>

      {round !== undefined ? (
        <>
          {/* Round 3 cards strip */}
          <div className="mb-8 grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">
            <div className="min-w-0">
              <SlimVulnerabilityCard
                records={detail?.model_vulnerabilities ?? []}
                round_id={round.round_id}
              />
            </div>
            <div className="min-w-0">
              <SlimFixCard
                records={detail?.defensive_fixes ?? []}
                round_id={round.round_id}
              />
            </div>
            <div className="min-w-0 xl:col-span-2 2xl:col-span-1">
              <RoundJudgeCard reports={detail?.judge_reports ?? []} />
            </div>
          </div>

          {/* Sanitized round-3 transcript */}
          {detail?.transcript_summary ? (
            <div className="mb-8">
              <SafeTranscriptPanel
                summary={detail.transcript_summary}
                safety_scan_passed={detail.safety_scan_passed ?? true}
                round_label="Round 3"
              />
            </div>
          ) : null}
        </>
      ) : (
        <div className="mb-8">
          <RoundNotRunYet />
        </div>
      )}

      {/* All four charts in a 2x2 grid */}
      <div className="mb-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Missed risky activity"
          hint="model miss rate · Carry-forward state plus selected candidate result before judge rejection."
        >
          <MissRateChart
            metrics={metrics}
            candidate_metrics={candidateMetrics}
          />
        </ChartCard>
        <ChartCard
          title="Risky activity caught"
          hint="recall at fixed action-rate · Higher is better. Carry-forward state plus selected candidate result."
        >
          <RecallRecoveryChart
            metrics={metrics}
            candidate_metrics={candidateMetrics}
          />
        </ChartCard>
        <ChartCard
          title="Demo losses let through"
          hint="synthetic loss allowed · Lower is better. SYN $; play-money only."
        >
          <SyntheticLossChart
            metrics={metrics}
            candidate_metrics={candidateMetrics}
          />
        </ChartCard>
        <ChartCard
          title="How often we interrupt customers"
          hint="customer-friction rates · Step-up checks, reviews, and blocks all stay below configured action-rate limits."
        >
          <FrictionChart metrics={metrics} />
        </ChartCard>
      </div>

      {/* Round timeline */}
      <div className="mb-10">
        <h3 className="mb-3 font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          Round timeline
        </h3>
        <RoundTimeline metrics={metrics} candidate_metrics={candidateMetrics} />
      </div>

      {/* Final-report summary card */}
      {finalReportCard ? (
        <div className="mb-10">
          <FinalReportSummaryCard card={finalReportCard} />
        </div>
      ) : null}

      {/* Run summary / ledger-style facts */}
      <div className="mb-10">
        <RunFacts payload={payload} />
      </div>

      {/* Model-tier comparison matrix */}
      <RunComparisonMatrix
        tiers={matrix.tiers}
        runs={matrix.runs}
        expose_concrete_model_names={matrix.expose_concrete_model_names}
        summary_templates={matrix.summary_templates}
      />
    </section>
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
        {filtered.map((r) => {
          const id = String(r.model_vulnerability_id ?? "");
          const family = String(r.family_id ?? "");
          const summary = String(r.summary ?? "");
          const missRate = typeof r.model_miss_rate === "number" ? r.model_miss_rate : null;
          const recommended = Array.isArray(r.recommended_defensive_fix_types)
            ? (r.recommended_defensive_fix_types as string[])
            : [];
          return (
            <li
              key={id}
              className="rounded-md border border-atlas-border/60 bg-atlas-surface/40 p-3"
            >
              <p className="truncate font-mono text-xs text-atlas-text">{id}</p>
              <p className="mt-0.5 text-xs text-atlas-text/90">
                Pattern: {VULN_FAMILY_LABELS[family] ?? family}
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
          {filtered.length} candidate{filtered.length === 1 ? "" : "s"} persisted
        </p>
      </header>
      <ul className="mt-3 space-y-3">
        {filtered.map((r) => {
          const id = String(r.defensive_fix_id ?? "");
          const fixType = String(r.fix_type ?? "");
          const vulnerabilityId = String(r.vulnerability_id ?? "");
          const overrides = (r.proposed_threshold_overrides ?? {}) as Record<
            string,
            number
          >;
          return (
            <li
              key={id}
              className="rounded-md border border-atlas-border/60 bg-atlas-surface/40 p-3"
            >
              <p className="truncate font-mono text-xs text-atlas-text">{id}</p>
              <p className="mt-0.5 text-[11px] text-atlas-text/90">
                Fix type: {FIX_TYPE_PLAIN[fixType] ?? fixType}
              </p>
              <p className="font-mono text-[10px] text-atlas-muted">fix_type · {fixType}</p>
              {vulnerabilityId ? (
                <>
                  <p className="mt-0.5 text-[11px] text-atlas-text/90">
                    Fixes weak spot
                  </p>
                  <p className="font-mono text-[10px] text-atlas-muted">
                    targets · {vulnerabilityId}
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
  // Phase 8 evaluates one fix per round — render the first report.
  return <JudgeDecisionCard report={report} />;
}

// ---------------------------------------------------------------------------
// Final-report card + run-facts panel
// ---------------------------------------------------------------------------

function findFinalReportCard(
  payload: ReplayPayload
): Record<string, unknown> | null {
  const step5 = payload.five_step_story.find((s) => s.step_id === 5);
  if (!step5) return null;
  const card = step5.cards.find((c) => c.category === "final_report");
  return card ?? null;
}

function FinalReportSummaryCard({
  card
}: {
  card: Record<string, unknown>;
}) {
  const summary = String(card.summary ?? "");
  const acceptedCount = typeof card.accepted_count === "number" ? card.accepted_count : null;
  const trend = Array.isArray(card.miss_rate_trend)
    ? (card.miss_rate_trend as number[])
    : [];
  const safetyOk = card.safety_scan_passed === true;

  return (
    <article className="rounded-lg border border-atlas-ok/40 bg-atlas-panel/60 p-5">
      <header className="flex items-center justify-between gap-3 border-b border-atlas-border/60 pb-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-ok">
            Final report
          </p>
          <h3 className="mt-1 text-base font-semibold text-atlas-text">
            Closed-enum summary
          </h3>
        </div>
        <span
          className={[
            "rounded-full border px-2 py-0.5 font-mono text-[10px]",
            safetyOk
              ? "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok"
              : "border-atlas-warn/40 bg-atlas-warn/10 text-atlas-warn"
          ].join(" ")}
          aria-label={safetyOk ? "Safety scan passed" : "Safety scan flagged for review"}
        >
          <span aria-hidden="true">{safetyOk ? "✓" : "⚠"}</span> safety_scan
        </span>
      </header>
      <p className="mt-3 font-mono text-[11px] leading-relaxed text-atlas-text/90">
        {summary}
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-xs md:grid-cols-2">
        {acceptedCount !== null ? (
          <Fact label="Accepted defensive fixes" value={String(acceptedCount)} />
        ) : null}
        {trend.length > 0 ? (
          <Fact
            label="Miss-rate trend"
            value={trend.map((v) => v.toFixed(4)).join(" → ")}
          />
        ) : null}
      </dl>
    </article>
  );
}

function RunFacts({ payload }: { payload: ReplayPayload }) {
  const r = payload.run;
  return (
    <article className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-5">
      <header>
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Run summary
        </p>
        <h3 className="mt-1 text-base font-semibold text-atlas-text">
          Reproducibility record
        </h3>
      </header>
      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 text-xs md:grid-cols-2">
        <Fact label="Run ID" value={r.run_id} mono />
        <Fact label="Seed" value={String(r.seed)} mono />
        <Fact label="Demo mode" value={r.demo_mode} mono />
        <Fact label="Status" value={r.status} mono />
        <Fact label="Current round" value={String(r.current_round ?? 0)} mono />
        <Fact label="Created at (dataset reference)" value={r.created_at_utc ?? "-"} mono />
      </dl>
    </article>
  );
}

function Fact({
  label,
  value,
  mono = false
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-atlas-muted">{label}</dt>
      <dd
        className={[
          mono ? "font-mono tabular-nums" : "",
          "text-atlas-text"
        ].join(" ")}
      >
        {value}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty / error state
// ---------------------------------------------------------------------------

function EmptyOrErrorState({
  kind,
  reason,
  remediation
}: {
  kind: "empty" | "error";
  reason: string;
  remediation: string | null;
}) {
  const tone = kind === "empty" ? "muted" : "danger";
  return (
    <section
      id="empty-state"
      aria-label={kind === "empty" ? "No replay available" : "Replay load error"}
      className="scroll-mt-16 border-t border-atlas-border/40 px-8 py-24"
    >
      <div className="mx-auto max-w-2xl rounded-lg border border-atlas-border bg-atlas-panel/60 p-8 text-center">
        <p
          className={[
            "font-mono text-[10px] uppercase tracking-widest",
            tone === "danger" ? "text-atlas-danger" : "text-atlas-muted"
          ].join(" ")}
        >
          {kind === "empty" ? "No replay yet" : "Replay load error"}
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-atlas-text">
          {kind === "empty"
            ? "There is no completed run to replay."
            : "Could not load replay data."}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">{reason}</p>
        {remediation ? (
          <div className="mt-6 inline-flex flex-col items-stretch gap-1 rounded-md border border-atlas-border/60 bg-atlas-surface/60 px-4 py-3 text-left">
            <span className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
              Run locally
            </span>
            <code className="font-mono text-xs text-atlas-text">{remediation}</code>
          </div>
        ) : null}
        <p className="mt-6 text-[11px] text-atlas-muted/80">
          Local-only by design — there is no remote fallback. Data is loaded
          from <span className="font-mono">http://127.0.0.1:8000</span>.
        </p>
      </div>
    </section>
  );
}

function RoundNotRunYet() {
  return (
    <div className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-6 text-sm text-atlas-muted">
      <p className="font-mono text-[10px] uppercase tracking-widest">
        Round not yet executed
      </p>
      <p className="mt-2">
        Run <code className="font-mono">make run-rounds</code> to populate this
        round&apos;s artifacts.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

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
