// app/web/components/JudgeDecisionCard.tsx
// Renders a single JudgeReport with a strong visual separation between
// judge-derived metrics (PROMINENT — large mono numbers, colored deltas,
// pass/fail pills) and agent-narrated text (SUBDUED — italic muted
// blockquote at the bottom of the card).
//
// This split is the user's explicit instruction for component 14 and
// reflects the Bible §6.1 rule 7 invariant: agents may generate hypotheses,
// candidates, defensive fix proposals, and explanations — only deterministic
// code can score, evaluate, accept, reject, or report final metrics. The
// card's visual hierarchy must mirror that invariant.
//
// The four metrics use the MetricCard component from component 11 so
// formatting (rate / synthetic_currency) and trend-arrow logic stay
// consistent with the rest of the app.

import type { JudgeReport } from "../lib/types";
import { GLOSSARY } from "../lib/glossary";
import { TermNote } from "./DualLabel";
import { MetricCard } from "./MetricCard";

export interface JudgeDecisionCardProps {
  report: JudgeReport;
}

export function JudgeDecisionCard({ report }: JudgeDecisionCardProps) {
  const accepted = report.accepted_by_judge;
  const borderClass = accepted ? "border-atlas-ok/40" : "border-atlas-danger/40";

  return (
    <article
      className={`flex h-full flex-col rounded-lg border bg-atlas-panel/60 p-5 ${borderClass}`}
    >
      {/* Header */}
      <header
        className="flex items-start justify-between gap-3 border-b border-atlas-border/60 pb-3"
        title={GLOSSARY.judge_decision.definition}
      >
        <div className="min-w-0">
          <p className="text-xs font-medium text-atlas-text">
            {GLOSSARY.judge_decision.plain}
          </p>
          <TermNote>{GLOSSARY.judge_decision.term}</TermNote>
          <p className="mt-1 truncate font-mono text-xs text-atlas-text">
            {report.judge_report_id}
          </p>
          <p className="truncate font-mono text-[11px] text-atlas-muted">
            fix · {report.defensive_fix_id}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span className="rounded-full border border-atlas-border bg-atlas-surface/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-atlas-muted">
            Round {report.round_id}
          </span>
          <span
            className={[
              "rounded-md border px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-wider",
              accepted
                ? "border-atlas-ok/40 bg-atlas-ok/15 text-atlas-ok"
                : "border-atlas-danger/40 bg-atlas-danger/15 text-atlas-danger"
            ].join(" ")}
            aria-label={accepted ? "Accepted by judge" : "Rejected by judge"}
          >
            <span aria-hidden="true">{accepted ? "✓ " : "✗ "}</span>
            {accepted ? "Accepted" : "Rejected"}
          </span>
        </div>
      </header>

      {/* PROMINENT: judge-derived metrics */}
      <section className="mt-4" aria-label="Judge-derived metrics">
        <div className="mb-3" title={GLOSSARY.judge_metrics.definition}>
          <p className="text-xs font-medium text-atlas-text">
            {GLOSSARY.judge_metrics.plain}
          </p>
          <TermNote>{GLOSSARY.judge_metrics.term}</TermNote>
        </div>
        <div className="grid grid-cols-1 gap-3 min-[1180px]:grid-cols-2">
          <MetricCard
            label={GLOSSARY.recall.plain}
            term={GLOSSARY.recall.term}
            definition={GLOSSARY.recall.definition}
            value={report.fixed.recall_at_fixed_action_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.recall_at_fixed_action_rate,
              improvement_direction: "up_is_good"
            }}
          />
          <MetricCard
            label={GLOSSARY.model_miss_rate.plain}
            term={GLOSSARY.model_miss_rate.term}
            definition={GLOSSARY.model_miss_rate.definition}
            value={report.fixed.model_miss_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.model_miss_rate,
              improvement_direction: "down_is_good"
            }}
          />
          <MetricCard
            label={GLOSSARY.false_positive_rate.plain}
            term={GLOSSARY.false_positive_rate.term}
            definition={GLOSSARY.false_positive_rate.definition}
            value={report.fixed.false_positive_rate_at_fixed_action_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.false_positive_rate_at_fixed_action_rate,
              improvement_direction: "down_is_good"
            }}
          />
          <MetricCard
            label={GLOSSARY.synthetic_loss_allowed.plain}
            term={GLOSSARY.synthetic_loss_allowed.term}
            definition={GLOSSARY.synthetic_loss_allowed.definition}
            value={report.fixed.synthetic_loss_allowed}
            format="synthetic_currency"
            comparison={{
              baseline_value: report.baseline.synthetic_loss_allowed,
              improvement_direction: "down_is_good"
            }}
          />
        </div>
      </section>

      {/* PROMINENT: holdout pass/fail */}
      <section
        className="mt-4 border-t border-atlas-border/60 pt-3"
        aria-label="Holdout generalization"
      >
        <div title={GLOSSARY.holdout_generalization.definition}>
          <p className="text-xs font-medium text-atlas-text">
            {GLOSSARY.holdout_generalization.plain}
          </p>
          <TermNote>{GLOSSARY.holdout_generalization.term}</TermNote>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <HoldoutPill
            label="Fresh customers"
            term={GLOSSARY.clean_holdout.term}
            passed={report.holdout_generalization.clean_holdout_pass}
          />
          <HoldoutPill
            label="Hidden stress test"
            term={GLOSSARY.locked_adaptive_holdout.term}
            passed={report.holdout_generalization.locked_adaptive_holdout_pass}
          />
          <HoldoutPill
            label="Future-drift test"
            term={GLOSSARY.drifted_holdout.term}
            passed={report.holdout_generalization.drifted_holdout_pass}
          />
        </div>
      </section>

      {/* SUBDUED: agent-narrated judge notes */}
      <section className="mt-4 border-t border-atlas-border/60 pt-3" aria-label="Judge notes">
        <p className="text-xs font-medium text-atlas-text" title={GLOSSARY.judge_notes.definition}>
          {GLOSSARY.judge_notes.plain}
          <span className="ml-1.5 normal-case tracking-normal text-atlas-muted/70">
            (condition record, generated by code)
          </span>
        </p>
        <TermNote>{GLOSSARY.judge_notes.term}</TermNote>
        <blockquote className="mt-2 break-words border-l-2 border-atlas-border/60 pl-3 text-xs italic leading-relaxed text-atlas-muted">
          {report.judge_notes}
        </blockquote>
      </section>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Holdout pass/fail pill
// ---------------------------------------------------------------------------

function HoldoutPill({
  label,
  passed,
  term
}: {
  label: string;
  passed: boolean;
  term?: string;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px]",
        passed
          ? "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok"
          : "border-atlas-danger/40 bg-atlas-danger/10 text-atlas-danger"
      ].join(" ")}
      aria-label={passed ? `${label} passed` : `${label} failed`}
      title={term}
    >
      <span aria-hidden="true">{passed ? "✓" : "✗"}</span>
      {label}
    </span>
  );
}
