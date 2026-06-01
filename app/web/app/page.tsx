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
    title: "I gave each agent a specifically narrow job.",
    lead:
      "My take on agents is they should have a specialized utility and they should stay in their lane.",
    paragraphs: [
      "Posture and prompt-wise, the red-team agents are curious; the bank-defense agents are cautious; the judge is a poker-faced Switzerland. None of them gets the keys to the kingdom: the full system.",
      "One red-team agent forms model vulnerability hypotheses. It uses a deterministic orchestrator to manage search methods, requested model vulnerability families, and how many times the red team can check its score on an approach. It basically says, \"maybe the mock scorer under-ranks this risk pattern.\" The red-team agents then try to produce evidence for that hypothesis. If they find accepted high-risk cases, it becomes a model vulnerability card.",
      "Another searches event histories with evolutionary search. It picks events, mutates the records, recomputes features, and rescores them. It is evolutionary in that it has a loop that ranks the best candidates, then re-mutates the winners while keeping some random exploration. It is saying, \"If I slightly change the history on this model vulnerability family, can I produce a coherent case the scorer treats as lower risk than it should?\"",
      "Another looks at relationship-graph signals using relationship/connection-weighted search. It reads the relationship graph for customer, recipient, device, and account links, counts which have the most edges or relationships, and over-indexes on those. It applies a mutation and the system recomputes graph features like relationship risk and shared-recipient signals. Accepted high-risk cases can become model vulnerability cards. It is asking, \"If graph-connected customers are more likely to expose a model vulnerability, which existing events should I adjust first?\"",
      "A final analyst packages the result into model vulnerability cards the defense side can actually use.",
      "On the other side, the bank-defense agents read those cards and choose what kind of defensive fix to try: a feature fix, a decision-threshold fix, or a model calibration fix. They can argue for a recommendation, and the fix candidate is accepted or rejected by the judge.",
      "The bank strategy agent triages model vulnerability cards, choosing which defensive fix types are eligible by validating card-recommended fixes, round-allowed fixes, and requested fixes.",
      "The feature fix agent proposes feature-transform defensive fixes. It uses closed-enum transforms like boost_current_device_tenure or boost_graph_risk.",
      "The decision-threshold agent proposes decision-threshold fixes while copying action-rate limits and friction tolerances from the baseline.",
      "Then there is a model calibration agent that proposes calibration/retraining fixes. It retrains or recalibrates the scorer with a different training seed and L2/C strength in sklearn. L2 is essentially telling the model, \"Prefer simpler, smaller weights unless the data gives you a good reason not to.\"",
      "The judge checks model miss rate, holdouts, action-rate limits, and whether the proposed fix candidate generalizes. If the numbers do not work, the candidate is rejected."
    ],
    criteria: [
      "generated data",
      "defensive fixes only",
      "judge decides"
    ],
    footer: "Scoped agents · limited tools · code decides",
    watermark: "Roles"
  },
  agentsDeployed: {
    id: "agents-deployed",
    eyebrow: "Agents deployed",
    title: "Let the adversarial games begin - but there are rules to this.",
    lead:
      "First rule: the environment is generated all the way down.",
    paragraphs: [
      "Customers, accounts, devices, recipients, login sessions, transfer events, security events, relationship edges, labels, features, and splits are all generated for the demo, courtesy of Google.",
      "Another rule: the red-team agents do not get to directly rewrite engineered features. They mutate event histories, then the system recomputes features before the mock scorer sees the case. That constraint matters because it keeps the search tied to actual records instead of letting an agent hallucinate convenient numbers.",
      "The bank-defense agents enter the same environment with a different temperament. They have to propose defensive fixes that survive the judge's checks: better recall at fixed action-rate limits, no unacceptable customer friction, and no failure on locked holdouts."
    ],
    criteria: [
      "model miss-rate reduction",
      "holdout performance",
      "within action-rate limits"
    ],
    footer: "Generated environment · local mock scorer · fixed evaluation rules",
    watermark: "Run"
  },
  round1: {
    id: "round-1",
    eyebrow: "Round 1 response",
    title: "The first fix looked useful. But the judge said no-no-no.",
    lead:
      "Round 1 is the failure case I wanted the demo to show.",
    paragraphs: [
      "The red-team agents found two model vulnerability cards: one around elevated relationship-graph risk, and another around cases clustered just below the scorer's decision boundary.",
      "The bank-defense side responded with several defensive fix options and selected a feature fix for the score-boundary cluster. On the found examples, the fix looked good. Model miss rate moved down. Recall moved up. Loss allowed fell. Ostensibly that would have been a win.",
      "The judge wasn't going for it though. It checked the candidate against the full evaluation set and rejected it. The false-positive increase was outside tolerance, and the locked adaptive holdout did not pass. The fix helped the examples that produced it, but it did not earn the right to become the accepted state.",
      "That is the point of Round 1: the agents surfaced something real inside the lab, and the defense produced a plausible answer, but the judge kept the system honest."
    ],
    footer: "Rejected defensive fix · vulnerability recorded · baseline carried forward",
    watermark: "Round 1"
  },
  round2: {
    id: "round-2",
    eyebrow: "Round 2 response",
    title: "The second pass found a fix FTW.",
    lead:
      "After Round 1, the agents had a ledger.",
    paragraphs: [
      "The rejected fix stayed in the record, the model vulnerability cards stayed available, and the red-team agents shifted pressure to new families: activity-channel shift, current-device mismatch, and recent-change feature delay.",
      "This time, the bank-defense side selected a feature fix for current-device mismatch. The idea was narrower and better grounded in the feature space. It strengthened a signal the mock scorer had been under-weighting without trying to move the whole decision boundary at once.",
      "The judge accepted it. Model miss rate dropped from 73.44% to 18.75%. Recall at the fixed action-rate limit rose from 26.56% to 81.25%. Loss allowed fell from SYN $19.47M to SYN $5.75M. The locked holdout passed, and the customer-friction checks stayed within the configured limits.",
      "Same scorer. Same judge. Same constraints. Different defensive state."
    ],
    footer: "Accepted defensive fix · locked holdout passed · state updated",
    watermark: "Round 2"
  },
  round3: {
    id: "round-3",
    eyebrow: "Round 3 · final report",
    title: "The final report turns the run into evidence.",
    lead:
      "Round 3 answers the question that comes after a good fix.",
    paragraphs: [
      "Can the agents still find pressure, and can the defense improve the system without overfitting to the latest examples?",
      "The red-team agents came back with two final model vulnerability cards: one near the label-noise boundary and another showing how a defensive fix can appear strong on found examples while still leaving graph-risk cases under-ranked. The bank-defense side chose a model calibration fix, with the judge again waiting at the end of the line.",
      "The judge accepted the final fix. Model miss rate moved from 18.75% to 3.12%. Recall rose to 96.88%. Loss allowed fell to SYN $0.62M. The final accepted state passed clean, found adaptive, locked adaptive, and drifted holdout checks.",
      "The final report kept it real: one rejected fix, two accepted defensive fixes, the metrics that changed, and the limits that held."
    ],
    footer: "Final metrics · accepted state · action-rate limits",
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
        "The record uses generated data, local mock scoring, and locked holdout checks."
      ]}
      criteria={[
        `${completedRounds} rounds completed`,
        acceptedCount !== null
          ? `${acceptedCount} defensive fixes accepted`
          : "defensive fixes judged",
        firstMissRate !== null && finalMissRate !== null
          ? `${formatRate(firstMissRate, { digits: 1 })} to ${formatRate(finalMissRate, { digits: 1 })} model miss rate`
          : "model miss rate recorded"
      ]}
      footer="Judge metrics · accepted state · action-rate limits"
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
