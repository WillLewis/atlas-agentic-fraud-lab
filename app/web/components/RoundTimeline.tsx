// app/web/components/RoundTimeline.tsx
// Round-by-round timeline showing before/after judge metrics. Visual only —
// no interactivity, no replay scrubbing yet.
//
// Phase 9: pure function of `metrics`. The page composes the data
// source — live replay (component 8) or `getRoundMetrics()` in
// fixture-mode demos. Each round panel pulls "before" from the prior
// snapshot and "after" from its own:
//   Round 1: before=metrics[0] (baseline)         after=metrics[1]
//   Round 2: before=metrics[1]                    after=metrics[2]
//   Round 3: before=metrics[2]                    after=metrics[3]
//
// When live replay carries fewer than 4 snapshots (a partially-completed
// run), the timeline renders only as many panels as it can derive
// (snapshots.length - 1). Empty input → empty list, no throw.

import { formatRate, formatSyntheticCurrency } from "../lib/formatters";
import { GLOSSARY } from "../lib/glossary";
import type { MetricSnapshot } from "../lib/types";
import { TermNote } from "./DualLabel";

interface TimelineRound {
  round_id: number;
  label: string;
  before: MetricSnapshot;
  after: MetricSnapshot;
  candidate_after: MetricSnapshot | null;
}

interface RoundTimelineProps {
  metrics: MetricSnapshot[];
  candidate_metrics?: MetricSnapshot[];
}

export function RoundTimeline({ metrics, candidate_metrics }: RoundTimelineProps) {
  // Pair each non-baseline snapshot with the prior one. ``rounds[i]``'s
  // before is ``metrics[i]`` and after is ``metrics[i+1]``. We yield
  // one panel per round we have a (before, after) pair for; an empty
  // ``metrics`` array (or one with only a baseline) produces zero
  // panels and we render an empty list rather than throwing.
  const rounds: TimelineRound[] = [];
  for (let i = 0; i + 1 < metrics.length; i += 1) {
    const before = metrics[i];
    const after = metrics[i + 1];
    if (!before || !after) continue;
    rounds.push({
      round_id: after.round_id,
      label: after.round_label,
      before,
      after,
      candidate_after: candidate_metrics?.[i + 1] ?? null
    });
  }

  return (
    <ol
      role="list"
      aria-label="Three-round timeline of missed risky activity and risky activity caught"
      className="grid grid-cols-1 gap-3 md:grid-cols-3"
    >
      {rounds.map((r, i) => (
        <li key={r.round_id} className="relative">
          <RoundPanel round={r} />
          {/* Decorative connector chevron between adjacent rounds (md+ only) */}
          {i < rounds.length - 1 ? (
            <span
              aria-hidden="true"
              className="absolute right-[-0.5rem] top-1/2 hidden -translate-y-1/2 text-atlas-muted md:block"
            >
              ▸
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Round panel
// ---------------------------------------------------------------------------

function RoundPanel({ round }: { round: TimelineRound }) {
  const isPlaceholder = round.after.kind === "interpolated";
  const candidateMoves =
    round.candidate_after !== null &&
    (round.candidate_after.model_miss_rate !== round.after.model_miss_rate ||
      round.candidate_after.recall_at_fixed_action_rate !==
        round.after.recall_at_fixed_action_rate ||
      round.candidate_after.false_positive_rate_at_fixed_action_rate !==
        round.after.false_positive_rate_at_fixed_action_rate ||
      round.candidate_after.synthetic_loss_allowed !==
        round.after.synthetic_loss_allowed);

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
            Round {round.round_id}
          </p>
          <h3 className="mt-1 text-sm font-semibold text-atlas-text">{round.label}</h3>
        </div>
        {isPlaceholder ? (
          <span
            className="rounded-full border border-atlas-warn/40 bg-atlas-warn/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-atlas-warn"
            aria-label="Placeholder values — not judge-derived in Phase 1"
          >
            Placeholder
          </span>
        ) : (
          <span
            className="rounded-full border border-atlas-ok/40 bg-atlas-ok/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-atlas-ok"
            aria-label="Judge-derived values from fixture"
          >
            Anchor
          </span>
        )}
      </header>

      <BeforeAfter
        label={`${GLOSSARY.model_miss_rate.plain} · carry-forward`}
        term={GLOSSARY.model_miss_rate.term}
        definition={GLOSSARY.model_miss_rate.definition}
        before_value={round.before.model_miss_rate}
        after_value={round.after.model_miss_rate}
        format="rate"
        improvement_direction="down_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label={`${GLOSSARY.model_miss_rate.plain} · selected candidate`}
          term={GLOSSARY.model_miss_rate.term}
          definition={GLOSSARY.model_miss_rate.definition}
          before_value={round.before.model_miss_rate}
          after_value={round.candidate_after.model_miss_rate}
          format="rate"
          improvement_direction="down_is_good"
        />
      ) : null}
      <BeforeAfter
        label={`${GLOSSARY.recall.plain} · carry-forward`}
        term={GLOSSARY.recall.term}
        definition={GLOSSARY.recall.definition}
        before_value={round.before.recall_at_fixed_action_rate}
        after_value={round.after.recall_at_fixed_action_rate}
        format="rate"
        improvement_direction="up_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label={`${GLOSSARY.recall.plain} · selected candidate`}
          term={GLOSSARY.recall.term}
          definition={GLOSSARY.recall.definition}
          before_value={round.before.recall_at_fixed_action_rate}
          after_value={round.candidate_after.recall_at_fixed_action_rate}
          format="rate"
          improvement_direction="up_is_good"
        />
      ) : null}
      <BeforeAfter
        label={`${GLOSSARY.false_positive_rate.plain} · carry-forward`}
        term={GLOSSARY.false_positive_rate.term}
        definition={GLOSSARY.false_positive_rate.definition}
        before_value={round.before.false_positive_rate_at_fixed_action_rate}
        after_value={round.after.false_positive_rate_at_fixed_action_rate}
        format="rate"
        improvement_direction="down_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label={`${GLOSSARY.false_positive_rate.plain} · selected candidate`}
          term={GLOSSARY.false_positive_rate.term}
          definition={GLOSSARY.false_positive_rate.definition}
          before_value={round.before.false_positive_rate_at_fixed_action_rate}
          after_value={round.candidate_after.false_positive_rate_at_fixed_action_rate}
          format="rate"
          improvement_direction="down_is_good"
        />
      ) : null}
      <BeforeAfter
        label={`${GLOSSARY.synthetic_loss_allowed.plain} · carry-forward`}
        term={GLOSSARY.synthetic_loss_allowed.term}
        definition={GLOSSARY.synthetic_loss_allowed.definition}
        before_value={round.before.synthetic_loss_allowed}
        after_value={round.after.synthetic_loss_allowed}
        format="synthetic_currency"
        improvement_direction="down_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label={`${GLOSSARY.synthetic_loss_allowed.plain} · selected candidate`}
          term={GLOSSARY.synthetic_loss_allowed.term}
          definition={GLOSSARY.synthetic_loss_allowed.definition}
          before_value={round.before.synthetic_loss_allowed}
          after_value={round.candidate_after.synthetic_loss_allowed}
          format="synthetic_currency"
          improvement_direction="down_is_good"
        />
      ) : null}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Before/after row
// ---------------------------------------------------------------------------

interface BeforeAfterProps {
  label: string;
  term: string;
  definition: string;
  before_value: number;
  after_value: number;
  format: "rate" | "synthetic_currency";
  improvement_direction: "down_is_good" | "up_is_good";
}

function BeforeAfter({
  label,
  term,
  definition,
  before_value,
  after_value,
  format,
  improvement_direction
}: BeforeAfterProps) {
  const delta = after_value - before_value;
  const isImprovement =
    delta === 0 ? null : improvement_direction === "down_is_good" ? delta < 0 : delta > 0;
  const tone =
    isImprovement === null ? "neutral" : isImprovement ? "good" : "bad";
  const arrow = delta === 0 ? "→" : delta > 0 ? "↑" : "↓";
  const valueLabel = (value: number): string =>
    format === "synthetic_currency" ? formatSyntheticCurrency(value) : formatRate(value);
  const deltaLabel =
    format === "synthetic_currency"
      ? formatSyntheticCurrency(Math.abs(delta))
      : `${Math.abs(delta * 100).toFixed(2)} pp`;

  return (
    <div className="mt-2 flex flex-col gap-0.5">
      <p className="text-xs font-medium text-atlas-muted" title={definition}>
        {label}
        <TermNote>{term}</TermNote>
      </p>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
        <span className="font-mono tabular-nums text-atlas-muted">
          {valueLabel(before_value)}
        </span>
        <span aria-hidden="true" className="text-atlas-muted">
          →
        </span>
        <span className="font-mono tabular-nums text-atlas-text">
          {valueLabel(after_value)}
        </span>
        <span
          className={[
            "ml-1 font-mono text-[10px]",
            tone === "good"
              ? "text-atlas-ok"
              : tone === "bad"
                ? "text-atlas-danger"
                : "text-atlas-muted"
          ].join(" ")}
        >
          <span aria-hidden="true">{arrow}</span> {deltaLabel}
        </span>
      </p>
    </div>
  );
}
