// app/web/components/SafeTranscriptPanel.tsx
// Phase 9 component 8 — sanitized round transcript surface.
//
// The panel ONLY renders the closed-enum, deterministic
// `transcript_summary` produced by
// `src/atlas/ledger/report_builder.build_round_transcript_summary`.
// No raw LLM transcripts; no free-form prose path. Phase 9 invariant
// (a)(4).

import { familyLabelFromId, fixTypeLabelFromId } from "../lib/ids";

interface SafeTranscriptPanelProps {
  summary: string;
  round_label?: string;
}

function humanizeTranscript(text: string): string {
  return text
    .replace(/\bmodel_vulnerability\b/g, "weak-spot")
    .replace(/\bmv_round\d+_[a-z0-9_]+/g, (id) => {
      const f = familyLabelFromId(id);
      return f ? `the "${f}" weak spot` : "the weak spot";
    })
    .replace(/\bfix_round\d+_[a-z0-9_]+/g, (id) => {
      const t = fixTypeLabelFromId(id);
      const f = familyLabelFromId(id);
      return t ? `the ${t.toLowerCase()} fix${f ? ` for "${f}"` : ""}` : "the selected fix";
    })
    .replace(/\bcandidate\(s\)/g, "fix option(s)")
    .replace(/\bselected candidate\b/g, "selected fix option")
    .replace(/\bcandidates\b/g, "fix options")
    .replace(/\bcandidate\b/g, "fix option")
    .replace(/\s*Carry-forward:.*$/s, "")
    .trim();
}

export function SafeTranscriptPanel({
  summary,
  round_label
}: SafeTranscriptPanelProps) {
  if (summary.length === 0) {
    return (
      <section
        aria-label="Sanitized round transcript summary"
        className="rounded-md border border-atlas-border bg-atlas-panel/60 p-4 text-xs text-atlas-muted"
      >
        <p className="font-mono uppercase tracking-widest">
          {round_label ?? "Transcript summary"}
        </p>
        <p className="mt-2 italic">No transcript summary recorded for this round.</p>
      </section>
    );
  }

  return (
    <section
      aria-label="Sanitized round transcript summary"
      className="rounded-md border border-atlas-border bg-atlas-panel/60 p-4"
    >
      <header className="mb-2 flex items-center justify-between gap-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          {round_label ?? "Transcript summary"}
        </p>
      </header>
      <p className="font-mono text-[11px] leading-relaxed text-atlas-text/90">
        {humanizeTranscript(summary)}
      </p>
    </section>
  );
}

export default SafeTranscriptPanel;
