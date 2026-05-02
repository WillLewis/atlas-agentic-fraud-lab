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
      <header className="flex items-start justify-between gap-3 border-b border-atlas-border/60 pb-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
            Judge Decision · Deterministic
          </p>
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
        <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Judge-derived metrics
        </p>
        <div className="grid grid-cols-1 gap-3 min-[1180px]:grid-cols-2">
          <MetricCard
            label="Recall at fixed action-rate"
            value={report.fixed.recall_at_fixed_action_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.recall_at_fixed_action_rate,
              improvement_direction: "up_is_good"
            }}
          />
          <MetricCard
            label="Model miss rate"
            value={report.fixed.model_miss_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.model_miss_rate,
              improvement_direction: "down_is_good"
            }}
          />
          <MetricCard
            label="False-positive rate"
            value={report.fixed.false_positive_rate_at_fixed_action_rate}
            format="rate"
            comparison={{
              baseline_value: report.baseline.false_positive_rate_at_fixed_action_rate,
              improvement_direction: "down_is_good"
            }}
          />
          <MetricCard
            label="Synthetic loss allowed"
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
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Holdout generalization
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <HoldoutPill
            label="Clean holdout"
            passed={report.holdout_generalization.clean_holdout_pass}
          />
          <HoldoutPill
            label="Locked adaptive"
            passed={report.holdout_generalization.locked_adaptive_holdout_pass}
          />
          <HoldoutPill
            label="Drifted holdout"
            passed={report.holdout_generalization.drifted_holdout_pass}
          />
        </div>
      </section>

      {/* SUBDUED: agent-narrated judge notes */}
      <section className="mt-4 border-t border-atlas-border/60 pt-3" aria-label="Judge notes">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Judge notes
          <span className="ml-1.5 normal-case tracking-normal text-atlas-muted/70">
            (narrative summary)
          </span>
        </p>
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

function HoldoutPill({ label, passed }: { label: string; passed: boolean }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px]",
        passed
          ? "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok"
          : "border-atlas-danger/40 bg-atlas-danger/10 text-atlas-danger"
      ].join(" ")}
      aria-label={passed ? `${label} passed` : `${label} failed`}
    >
      <span aria-hidden="true">{passed ? "✓" : "✗"}</span>
      {label}
    </span>
  );
}
