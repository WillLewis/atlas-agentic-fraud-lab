const GLYPHS = [
  { text: "under_ranked_cohort", top: "14%", left: "8%", delay: "0s" },
  { text: "demo_action_rate_limit: 0.04", top: "28%", left: "78%", delay: "2s" },
  { text: "synthetic_search_active", top: "44%", left: "22%", delay: "4s" },
  { text: "demo_decision_threshold: 0.88", top: "58%", left: "70%", delay: "6s" },
  { text: "model_miss_rate_delta: -0.13", top: "70%", left: "12%", delay: "1s" },
  { text: "synthetic_cohort_id: demo_03f", top: "82%", left: "60%", delay: "3s" },
  { text: "calibration_pass", top: "12%", left: "50%", delay: "7s" },
  { text: "defensive_fix.apply()", top: "90%", left: "30%", delay: "5s" }
] as const;

export function AmbientGlyphs() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
    >
      {GLYPHS.map((glyph) => (
        <span
          key={glyph.text}
          className="atlas-intro-float absolute font-mono text-[10px] tracking-tight text-intro-foreground/60"
          style={{
            top: glyph.top,
            left: glyph.left,
            animationDelay: glyph.delay
          }}
        >
          {glyph.text}
        </span>
      ))}
    </div>
  );
}
