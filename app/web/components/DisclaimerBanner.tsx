// app/web/components/DisclaimerBanner.tsx
// Persistent top banner showing the synthetic-only safety posture.
//
// Server component (no "use client") because everything renders from
// getDemoConfig(), which is server-only. There is intentionally no close
// button, no dismissibility state, no client-side toggling — the disclaimer
// must remain visible on every page in every demo mode.
//
// Per architecture doc §1.2 the failure modes for this component are:
// "Missing from pages; copy too vague". Keeping the badge + institution
// label + model label + disclaimer text together addresses both.

import { getDemoConfig } from "../lib/demoConfig";

const MODE_BADGE_LABELS: Record<"public" | "internal", string> = {
  public: "Public Demo",
  internal: "Internal Demo"
};

export function DisclaimerBanner() {
  const config = getDemoConfig();
  const badgeLabel = MODE_BADGE_LABELS[config.demo_mode];

  return (
    <div className="atlas-demo-banner border-b px-6 py-2 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-atlas-muted">
        <span
          className="inline-flex items-center gap-1.5 rounded-sm bg-atlas-warn/15 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-atlas-warn"
          aria-label={`Demo mode: ${badgeLabel}`}
        >
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-1.5 rounded-full bg-atlas-warn"
          />
          {badgeLabel}
        </span>

        <span className="font-medium text-atlas-text">{config.institution_label}</span>

        <span aria-hidden="true" className="text-atlas-border">
          ·
        </span>

        <span>{config.model_label}</span>

        <span aria-hidden="true" className="text-atlas-border">
          ·
        </span>

        <span className="text-atlas-muted">{config.disclaimer}</span>
      </div>
    </div>
  );
}
