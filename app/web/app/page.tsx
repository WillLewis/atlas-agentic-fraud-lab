// app/web/app/page.tsx
// Phase 1 page composition: sidebar + five narrative sections.
//
// Sections 1 (AgentRoster) and 2 (EnvironmentOverview) own their own
// <section id="…"> wrappers. Sections 3, 4, and 5 are composed inline here
// because their content is built from existing card and chart components.
//
// Phase 1 placeholder behavior: rounds 2 and 3 reuse the single fixture
// records from project_atlas_sample_data.json (mv_round1_001,
// fix_round1_graph_risk_feature, judge_round1_fix_graph_risk). A small
// inline notice on each placeholder section makes the reuse explicit.
// Phase 8 ledger replay will populate real per-round records and these
// notices become unnecessary.

import { AgentRoster } from "../components/AgentRoster";
import { DefensiveFixCard } from "../components/DefensiveFixCard";
import { EnvironmentOverview } from "../components/EnvironmentOverview";
import { JudgeDecisionCard } from "../components/JudgeDecisionCard";
import { LeftSidebar } from "../components/LeftSidebar";
// Component name shadows the type name; alias the type on import.
import { ModelVulnerabilityCard } from "../components/ModelVulnerabilityCard";
import { RoundTimeline } from "../components/RoundTimeline";
import { FrictionChart } from "../components/charts/FrictionChart";
import { MissRateChart } from "../components/charts/MissRateChart";
import { RecallRecoveryChart } from "../components/charts/RecallRecoveryChart";
import { SyntheticLossChart } from "../components/charts/SyntheticLossChart";
import {
  getDefensiveFixCandidates,
  getJudgeReports,
  getLedgerRecords,
  getModelVulnerabilityCards
} from "../lib/fixtures";
import type {
  DefensiveFixCandidate,
  JudgeReport,
  LedgerRecord,
  ModelVulnerabilityCard as ModelVulnerabilityCardData
} from "../lib/types";

// ---------------------------------------------------------------------------
// Section narrative — Bible §8 main messages. Eyebrow text matches the
// sidebar step numbering (Step 1 / 2 / 3 / 4 / 5).
// ---------------------------------------------------------------------------

interface SectionNarrative {
  eyebrow: string;
  title: string;
  subtitle: string;
}

const ROUND_NARRATIVE: Record<"round_1" | "round_2" | "round_3", SectionNarrative> = {
  round_1: {
    eyebrow: "Step 3",
    title: "Round 1 — Test and Response",
    subtitle:
      "Red-team agents identify the first synthetic model vulnerability; bank-defense agents propose a fix; the judge checks whether measured improvement is real."
  },
  round_2: {
    eyebrow: "Step 4",
    title: "Round 2 — Adaptive Pressure",
    subtitle:
      "The value is not one-time testing; it is repeated adaptation with disciplined measurement."
  },
  round_3: {
    eyebrow: "Step 5",
    title: "Round 3 — Final Report",
    subtitle:
      "Agentic defense improves resilience only when paired with deterministic evaluation and strict customer-friction limits."
  }
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function HomePage() {
  const mvCards = getModelVulnerabilityCards();
  const fixCandidates = getDefensiveFixCandidates();
  const judgeReports = getJudgeReports();
  const ledgerRecords = getLedgerRecords();

  const sharedMv = mvCards[0];
  const sharedFix = fixCandidates[0];
  const sharedJudge = judgeReports[0];
  const sharedLedger = ledgerRecords[0];
  if (!sharedMv || !sharedFix || !sharedJudge || !sharedLedger) {
    throw new Error(
      "page.tsx: project_atlas_sample_data.json is missing one or more required fixture records."
    );
  }

  return (
    <div className="flex">
      <LeftSidebar />
      <main className="min-w-0 flex-1">
        {/* Section 1 + Section 2 own their own <section id="…"> */}
        <AgentRoster />
        <EnvironmentOverview />

        {/* Section 3 — Round 1 */}
        <RoundSection
          id="round-1"
          narrative={ROUND_NARRATIVE.round_1}
          mv={sharedMv}
          fix={sharedFix}
          judge={sharedJudge}
        />

        {/* Section 4 — Round 2 (placeholder reuse of Round 1 fixture record) */}
        <RoundSection
          id="round-2"
          narrative={ROUND_NARRATIVE.round_2}
          mv={sharedMv}
          fix={sharedFix}
          judge={sharedJudge}
          is_placeholder
        />

        {/* Section 5 — Round 3 final report */}
        <FinalReportSection
          id="round-3"
          narrative={ROUND_NARRATIVE.round_3}
          ledger={sharedLedger}
        />
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Round section (Sections 3 and 4)
// ---------------------------------------------------------------------------

interface RoundSectionProps {
  id: string;
  narrative: SectionNarrative;
  mv: ModelVulnerabilityCardData;
  fix: DefensiveFixCandidate;
  judge: JudgeReport;
  is_placeholder?: boolean;
}

function RoundSection({
  id,
  narrative,
  mv,
  fix,
  judge,
  is_placeholder
}: RoundSectionProps) {
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
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">
          {narrative.subtitle}
        </p>
        {is_placeholder ? <PlaceholderNote /> : null}
      </header>

      {/* Three cards: vulnerability, fix, judge decision */}
      <div className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ModelVulnerabilityCard vulnerability={mv} />
        <DefensiveFixCard candidate={fix} />
        <JudgeDecisionCard report={judge} />
      </div>

      {/* Chart strip — focused subset for round-level reading */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Model miss rate"
          hint="Lower is better. Anchored at Baseline and Round 1; Rounds 2–3 are Phase 1 placeholders."
        >
          <MissRateChart />
        </ChartCard>
        <ChartCard
          title="Recall at fixed action-rate limit"
          hint="Higher is better. Anchored at Baseline and Round 1; Rounds 2–3 are Phase 1 placeholders."
        >
          <RecallRecoveryChart />
        </ChartCard>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Final report section (Section 5)
// ---------------------------------------------------------------------------

interface FinalReportSectionProps {
  id: string;
  narrative: SectionNarrative;
  ledger: LedgerRecord;
}

function FinalReportSection({ id, narrative, ledger }: FinalReportSectionProps) {
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
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">
          {narrative.subtitle}
        </p>
      </header>

      {/* Round timeline */}
      <div className="mb-10">
        <h3 className="mb-3 font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          Round timeline
        </h3>
        <RoundTimeline />
      </div>

      {/* All four charts in a 2x2 grid */}
      <div className="mb-10 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Model miss rate"
          hint="Trend across rounds. Anchors at Baseline and Round 1."
        >
          <MissRateChart />
        </ChartCard>
        <ChartCard
          title="Recall at fixed action-rate limit"
          hint="Higher is better."
        >
          <RecallRecoveryChart />
        </ChartCard>
        <ChartCard
          title="Synthetic loss allowed"
          hint="In synthetic currency units. Lower is better."
        >
          <SyntheticLossChart />
        </ChartCard>
        <ChartCard
          title="Customer-friction rates"
          hint="Challenge, alert, and decline rates. All series remain below configured action-rate limits."
        >
          <FrictionChart />
        </ChartCard>
      </div>

      {/* Run ledger */}
      <LedgerSummary record={ledger} />
    </section>
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

function PlaceholderNote() {
  return (
    <p
      className="mt-4 inline-flex max-w-2xl items-start gap-2 rounded-md border border-atlas-warn/30 bg-atlas-warn/10 px-3 py-2 text-[11px] leading-relaxed"
      role="note"
    >
      <span aria-hidden="true" className="text-atlas-warn">
        ⚠
      </span>
      <span className="text-atlas-text/80">
        Phase 1 shell: this round reuses the Round 1 fixture record as placeholder
        content. Phase 8 ledger replay will populate real per-round records.
      </span>
    </p>
  );
}

function LedgerSummary({ record }: { record: LedgerRecord }) {
  return (
    <article className="rounded-lg border border-atlas-border bg-atlas-panel/60 p-5">
      <header>
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Run ledger
        </p>
        <h3 className="mt-1 text-base font-semibold text-atlas-text">
          Reproducibility record
        </h3>
      </header>
      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 text-xs md:grid-cols-2">
        <LedgerRow label="Run ID" value={record.run_id} mono />
        <LedgerRow label="Round ID" value={String(record.round_id)} mono />
        <LedgerRow label="Seed" value={String(record.seed)} mono />
        <LedgerRow label="Demo mode" value={record.demo_mode} mono />
        <LedgerRow
          label="Model version (before)"
          value={record.model_version_before}
          mono
        />
        <LedgerRow
          label="Model version (after)"
          value={record.model_version_after}
          mono
        />
        <LedgerRow
          label="Threshold version (before)"
          value={record.decision_threshold_version_before}
          mono
        />
        <LedgerRow
          label="Threshold version (after)"
          value={record.decision_threshold_version_after}
          mono
        />
        <LedgerRow
          label="Agent roster version"
          value={record.agent_roster_version}
          mono
        />
        <LedgerRow
          label="Safety scan"
          value={record.safety_scan_passed ? "✓ Passed" : "✗ Failed"}
          tone={record.safety_scan_passed ? "ok" : "danger"}
        />
      </dl>
      <div className="mt-4 border-t border-atlas-border/60 pt-3 space-y-1 text-[11px] text-atlas-muted">
        <p>
          Judge report:{" "}
          <span className="font-mono break-all text-atlas-text/80">
            {record.judge_report_path}
          </span>
        </p>
        <p>
          Vulnerability card:{" "}
          <span className="font-mono break-all text-atlas-text/80">
            {record.model_vulnerability_card_path}
          </span>
        </p>
      </div>
    </article>
  );
}

function LedgerRow({
  label,
  value,
  mono,
  tone
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: "ok" | "danger";
}) {
  const valueClass = [
    mono ? "font-mono tabular-nums" : "",
    tone === "ok" ? "text-atlas-ok" : tone === "danger" ? "text-atlas-danger" : "text-atlas-text"
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-atlas-muted">{label}</dt>
      <dd className={valueClass}>{value}</dd>
    </div>
  );
}
