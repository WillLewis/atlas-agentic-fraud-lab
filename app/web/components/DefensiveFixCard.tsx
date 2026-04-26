// app/web/components/DefensiveFixCard.tsx
// Renders a single DefensiveFixCandidate fixture record as a public-safe
// proposal card. Pure server component: data flows in via props so the
// same record can be reused across the round sections in Phase 1.
//
// requires_judge_evaluation is rendered prominently because the architecture
// invariant ("agents propose; deterministic code decides", Bible §6.1 rule 7)
// is the most important thing the card communicates. A fix card without an
// "evaluation pending" or "evaluation complete" cue is not safe to demo.

import type { DefensiveFixCandidate, FixType } from "../lib/types";

const FIX_TYPE_LABELS: Record<FixType, string> = {
  feature_fix: "Feature fix",
  policy_fix: "Decision-threshold fix",
  model_calibration_fix: "Model calibration fix"
};

export interface DefensiveFixCardProps {
  candidate: DefensiveFixCandidate;
}

export function DefensiveFixCard({ candidate }: DefensiveFixCardProps) {
  const fixTypeLabel = FIX_TYPE_LABELS[candidate.fix_type] ?? candidate.fix_type;
  const fmtPp = (frac: number): string => `${(frac * 100).toFixed(2)} pp`;

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-accent/40 bg-atlas-panel/60 p-5">
      {/* Header */}
      <header className="flex items-start justify-between gap-3 border-b border-atlas-border/60 pb-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-accent">
            Defensive Fix Candidate
          </p>
          <p className="mt-1 truncate font-mono text-xs text-atlas-text">
            {candidate.defensive_fix_id}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="rounded-full border border-atlas-border bg-atlas-surface/70 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-atlas-muted">
            Round {candidate.round_id}
          </span>
          <span className="rounded-full border border-atlas-accent/40 bg-atlas-accent/10 px-2 py-0.5 font-mono text-[10px] text-atlas-accent">
            {fixTypeLabel}
          </span>
        </div>
      </header>

      {/* Description */}
      <p className="mt-4 text-sm leading-relaxed text-atlas-text">{candidate.description}</p>

      {/* Expected benefit */}
      <div className="mt-4 border-t border-atlas-border/60 pt-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Expected benefit
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-atlas-text/80">
          {candidate.expected_benefit}
        </p>
      </div>

      {/* Files changed */}
      {candidate.files_changed.length > 0 ? (
        <div className="mt-4 border-t border-atlas-border/60 pt-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
            Files changed
          </p>
          <ul className="mt-1.5 space-y-0.5 font-mono text-[11px] text-atlas-text/80">
            {candidate.files_changed.map((f) => (
              <li key={f} className="flex gap-2">
                <span aria-hidden="true" className="text-atlas-muted">
                  ▸
                </span>
                <span className="break-all">{f}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Rate-limit claim */}
      <div className="mt-4 border-t border-atlas-border/60 pt-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Rate-limit claim
        </p>
        <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <Stat
            label="Max false-positive increase"
            value={`≤ ${fmtPp(candidate.rate_limit_claim.max_false_positive_rate_increase)}`}
          />
          <Stat
            label="Max challenge-rate increase"
            value={`≤ ${fmtPp(candidate.rate_limit_claim.max_challenge_rate_increase)}`}
          />
        </dl>
      </div>

      {/* Judge-evaluation marker */}
      <p
        className={[
          "mt-4 flex items-center gap-2 border-t border-atlas-border/60 pt-3 text-[11px]",
          candidate.requires_judge_evaluation ? "text-atlas-warn" : "text-atlas-muted"
        ].join(" ")}
      >
        <span aria-hidden="true">{candidate.requires_judge_evaluation ? "⚠" : "○"}</span>
        {candidate.requires_judge_evaluation
          ? "Requires deterministic judge evaluation before acceptance."
          : "No judge evaluation required."}
      </p>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Local helper — small key/value stat block (kept local to mirror the
// pattern used by ModelVulnerabilityCard.tsx)
// ---------------------------------------------------------------------------

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-sm tabular-nums text-atlas-text">{value}</dd>
    </div>
  );
}
