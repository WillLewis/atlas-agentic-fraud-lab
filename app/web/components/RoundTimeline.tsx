// app/web/components/RoundTimeline.tsx
// Three-round timeline showing before/after model_miss_rate and
// recall_at_fixed_action_rate. Visual only — no interactivity, no replay
// scrubbing yet. Phase 9 will hook this up to a run selector.
//
// Each round panel pulls the round's "before" metrics from the prior
// MetricSnapshot and "after" from its own snapshot:
//   Round 1: before=snapshots[0] (baseline)        after=snapshots[1]
//   Round 2: before=snapshots[1]                   after=snapshots[2]
//   Round 3: before=snapshots[2]                   after=snapshots[3]
//
// Round 1's "after" is the only judge-derived value in the fixture; rounds
// 2 and 3 are Phase 1 placeholder extrapolations from fixtures.ts. The
// connector chevrons between rounds are decorative.

import { getRoundMetrics } from "../lib/fixtures";
import { formatRate } from "../lib/formatters";
import type { MetricSnapshot } from "../lib/types";

interface TimelineRound {
  round_id: number;
  label: string;
  before: MetricSnapshot;
  after: MetricSnapshot;
}

export function RoundTimeline() {
  const snapshots = getRoundMetrics();
  if (snapshots.length < 4) {
    throw new Error(
      "RoundTimeline: getRoundMetrics() returned fewer than 4 snapshots."
    );
  }

  const rounds: TimelineRound[] = [
    { round_id: 1, label: "Round 1", before: snapshots[0]!, after: snapshots[1]! },
    { round_id: 2, label: "Round 2", before: snapshots[1]!, after: snapshots[2]! },
    { round_id: 3, label: "Round 3", before: snapshots[2]!, after: snapshots[3]! }
  ];

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
        label="Model miss rate"
        before_value={round.before.model_miss_rate}
        after_value={round.after.model_miss_rate}
        improvement_direction="down_is_good"
      />
      <BeforeAfter
        label="Recall at fixed action-rate"
        before_value={round.before.recall_at_fixed_action_rate}
        after_value={round.after.recall_at_fixed_action_rate}
        improvement_direction="up_is_good"
      />
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
