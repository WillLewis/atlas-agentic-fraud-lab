// app/web/components/RoundTimeline.tsx
// Round-by-round timeline showing before/after model_miss_rate and
// recall_at_fixed_action_rate. Visual only — no interactivity, no replay
// scrubbing yet.
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

import { formatRate } from "../lib/formatters";
import type { MetricSnapshot } from "../lib/types";

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
      aria-label="Three-round timeline of model miss rate and recall at fixed action-rate limit"
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
        round.after.recall_at_fixed_action_rate);

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
        label="Model miss rate · carry-forward"
        before_value={round.before.model_miss_rate}
        after_value={round.after.model_miss_rate}
        improvement_direction="down_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label="Model miss rate · selected candidate"
          before_value={round.before.model_miss_rate}
          after_value={round.candidate_after.model_miss_rate}
          improvement_direction="down_is_good"
        />
      ) : null}
      <BeforeAfter
        label="Recall at fixed action-rate · carry-forward"
        before_value={round.before.recall_at_fixed_action_rate}
        after_value={round.after.recall_at_fixed_action_rate}
        improvement_direction="up_is_good"
      />
      {candidateMoves && round.candidate_after ? (
        <BeforeAfter
          label="Recall at fixed action-rate · selected candidate"
          before_value={round.before.recall_at_fixed_action_rate}
          after_value={round.candidate_after.recall_at_fixed_action_rate}
          improvement_direction="up_is_good"
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
  before_value: number;
  after_value: number;
  improvement_direction: "down_is_good" | "up_is_good";
}

function BeforeAfter({
  label,
  before_value,
  after_value,
  improvement_direction
}: BeforeAfterProps) {
  const delta = after_value - before_value;
  const isImprovement =
    delta === 0 ? null : improvement_direction === "down_is_good" ? delta < 0 : delta > 0;
  const tone =
    isImprovement === null ? "neutral" : isImprovement ? "good" : "bad";
  const arrow = delta === 0 ? "→" : delta > 0 ? "↑" : "↓";

  return (
    <div className="mt-2 flex flex-col gap-0.5">
      <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        {label}
      </p>
      <p className="flex items-baseline gap-2 text-sm">
        <span className="font-mono tabular-nums text-atlas-muted">
          {formatRate(before_value)}
        </span>
        <span aria-hidden="true" className="text-atlas-muted">
          →
        </span>
        <span className="font-mono tabular-nums text-atlas-text">
          {formatRate(after_value)}
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
          <span aria-hidden="true">{arrow}</span>{" "}
          {Math.abs(delta * 100).toFixed(2)} pp
        </span>
      </p>
    </div>
  );
}
