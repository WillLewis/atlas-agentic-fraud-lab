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
import { NarrativeInterlude } from "../components/NarrativeInterlude";
import { FrictionChart } from "../components/charts/FrictionChart";
import { MissRateChart } from "../components/charts/MissRateChart";
import { RecallRecoveryChart } from "../components/charts/RecallRecoveryChart";
import { SyntheticLossChart } from "../components/charts/SyntheticLossChart";
import { AtlasFooter } from "../components/intro/AtlasFooter";
import { AtlasIntro } from "../components/intro/AtlasIntro";
import { getRunRoundDetail } from "../lib/api";
import { FIX_TYPE_PLAIN, GLOSSARY, VULN_FAMILY_LABELS } from "../lib/glossary";
import { familyLabelFromId } from "../lib/ids";
import { loadActiveReplay } from "../lib/replay";
import type { ReplayPayload, RoundDetail, RoundSummary } from "../lib/replay";
import type { JudgeReport, MetricSnapshot } from "../lib/types";

// ---------------------------------------------------------------------------
// Narrative pages — Bible §8
// ---------------------------------------------------------------------------

const NARRATIVE_BREAKS = {
  agentsAssigned: {
    id: "agents-assigned",
    eyebrow: "Agents assigned",
    title: "The roles are set before the loop begins.",
    lead:
      "Before any synthetic search starts, each agent gets a narrow job: stress-test the mock scorer, propose defensive fixes, or judge the result.",
    paragraphs: [
      "The setup is intentionally constrained. Agents can work with generated cases, local mock scores, and public-safe summaries, but they cannot touch real customers, real controls, or production endpoints.",
      "This is what makes the demo useful as an AI/ML product story: the system is agentic enough to explore, but bounded enough that deterministic code can decide what counts as real improvement."
    ],
    criteria: [
      "synthetic search only",
      "defensive fixes only",
      "deterministic judge"
    ],
    footer: "Scoped agents · bounded tools · code-reviewed outcomes",
    watermark: "Assign"
  },
  agentsDeployed: {
    id: "agents-deployed",
    eyebrow: "Agents deployed",
    title: "The synthetic search begins.",
    lead:
      "This next step sends the agents into a closed demo environment. They will test generated cases against the Mock Account-Takeover Risk Scorer and record every proposed defensive fix.",
    paragraphs: [
      "The agents can score synthetic cases and recommend changes, but they cannot touch real customers, real controls, or production endpoints.",
      "Every defensive fix has to pass three tests: reduce model miss rate, generalize beyond the cohort that exposed the issue, and stay inside action-rate limits so customer experience does not quietly degrade."
    ],
    criteria: [
      "model miss-rate reduction",
      "generalization beyond found cohort",
      "within action-rate limits"
    ],
    footer: "Agents propose · deterministic code decides",
    watermark: "Evaluate"
  },
  round1: {
    id: "round-1",
    eyebrow: "Round 1 response",
    title: "The first answer is not always the right answer.",
    lead:
      "In the first round, red-team surfaces an under-ranked synthetic cohort. Bank-defense proposes a decision-threshold-style defensive fix, and the judge rejects it.",
    paragraphs: [
      "That rejection is the point of the loop. A defensive fix can look convincing on the cases that exposed the issue and still fail once it is tested against fresh holdouts, drifted examples, and customer-friction limits.",
      "In a real model review, this is where the team should slow down: the system found a valid synthetic model vulnerability, but it has not yet found a defensible change to ship."
    ],
    footer: "Rejected fixes are useful signal",
    watermark: "Round 1"
  },
  round2: {
    id: "round-2",
    eyebrow: "Round 2 response",
    title: "Defense iterates with a stronger candidate.",
    lead:
      "Next, bank-defense changes the response. It proposes a synthetic feature or calibration change, and the judge retests the result against holdouts and action-rate limits.",
    paragraphs: [
      "This time, the change reduces missed risky activity while staying inside the demo's customer-friction guardrails.",
      "For an AI/ML product team, this is the useful behavior: learn from the failed defensive fix, improve model behavior, and prove the improvement survives data the agents did not see."
    ],
    footer: "Generalization beats memorization",
    watermark: "Round 2"
  },
  round3: {
    id: "round-3",
    eyebrow: "Round 3 · final report",
    title: "The evidence becomes a decision record.",
    lead:
      "Finally, the judge consolidates miss-rate movement, generalization, and customer-friction trade-offs into a deterministic verdict.",
    paragraphs: [
      "The final report is not an agent summary. It is the record of what changed, why it passed, and where the evaluation still depends on synthetic assumptions.",
      "This is the artifact a team would want before moving from research preview into a governance, model-risk, or executive review conversation."
    ],
    footer: "Final numbers · locked holdouts · friction trade-offs",
    watermark: "Verdict"
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
  const params = await searchParams;
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

          {/* Chart strip — focused subset for round-level reading */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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
    <section
      id={id}
      aria-label="Round 3 final report evidence"
      className="atlas-data-section border-t border-atlas-border/40 px-8 py-16"
    >
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

        </>
      ) : (
        <div className="mb-8">
          <RoundNotRunYet />
        </div>
      )}

      <ChartReadingGuide />

      {/* All four charts in a 2x2 grid */}
      <div className="mb-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
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
        {filtered.map((r) => {
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
              key={id}
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
            Summary
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
          <span aria-hidden="true">{safetyOk ? "✓" : "⚠"}</span> safety check
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
          Run details
        </h3>
      </header>
      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 text-xs md:grid-cols-2">
        <Fact label="Run" value="Completed demo run" title={r.run_id} />
        <Fact label="Seed" value={String(r.seed)} mono />
        <Fact label="Demo mode" value={r.demo_mode} mono />
        <Fact label="Status" value={r.status} mono />
        <Fact label="Current round" value={String(r.current_round ?? 0)} mono />
        <Fact label="Created" value={r.created_at_utc ?? "-"} mono />
      </dl>
    </article>
  );
}

function Fact({
  label,
  value,
  mono = false,
  title
}: {
  label: string;
  value: string;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3" title={title}>
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
