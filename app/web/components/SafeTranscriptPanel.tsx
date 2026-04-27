// app/web/components/SafeTranscriptPanel.tsx
// Phase 9 component 8 — sanitized round transcript surface.
//
// The panel ONLY renders the closed-enum, deterministic
// `transcript_summary` produced by
// `src/atlas/ledger/report_builder.build_round_transcript_summary`.
// No raw LLM transcripts; no free-form prose path. Phase 9 invariant
// (a)(4). The `safety_scan_passed` boolean comes verbatim from the
// persisted RoundState.

interface SafeTranscriptPanelProps {
  summary: string;
  safety_scan_passed: boolean;
  round_label?: string;
}

export function SafeTranscriptPanel({
  summary,
  safety_scan_passed,
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
        <span
          className={[
            "rounded-full border px-2 py-0.5 font-mono text-[10px]",
            safety_scan_passed
              ? "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok"
              : "border-atlas-warn/40 bg-atlas-warn/10 text-atlas-warn"
          ].join(" ")}
          aria-label={
            safety_scan_passed
              ? "Safety scan passed"
              : "Safety scan flagged this transcript for review"
          }
        >
          <span aria-hidden="true">{safety_scan_passed ? "✓ " : "⚠ "}</span>
          safety_scan: {safety_scan_passed ? "pass" : "review"}
        </span>
      </header>
      <p className="font-mono text-[11px] leading-relaxed text-atlas-text/90">
        {summary}
      </p>
    </section>
  );
}

export default SafeTranscriptPanel;
