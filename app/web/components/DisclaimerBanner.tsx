// app/web/components/DisclaimerBanner.tsx
// Persistent top banner showing the synthetic-only safety posture.
//
// Server component (no "use client") because everything renders from
// getDemoConfig(), which is server-only. There is intentionally no close
// button, no dismissibility state, no client-side toggling — the disclaimer
// must remain visible on every page in every demo mode.
//
// Per architecture doc §1.2 the failure modes for this component are:
// "Missing from pages; copy too vague". Keep the badge + synthetic-data note
// visible at all times.

import { getDemoConfig } from "../lib/demoConfig";

const MODE_BADGE_LABELS: Record<"public" | "internal", string> = {
  public: "Demo",
  internal: "Internal Demo"
};

const SYNTHETIC_DATA_NOTE = "Google-sourced synthetic data";
const REPO_URL = "https://github.com/WillLewis/atlas-agentic-fraud-lab";
const REPO_LABEL = REPO_URL;

export function DisclaimerBanner() {
  const config = getDemoConfig();
  const badgeLabel = MODE_BADGE_LABELS[config.demo_mode];

  return (
    <div className="atlas-demo-banner border-b px-6 py-2 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 text-xs text-atlas-muted">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
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

          <span className="text-atlas-muted">{SYNTHETIC_DATA_NOTE}</span>
        </div>

        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[11px] font-medium text-atlas-muted underline-offset-4 hover:text-atlas-text hover:underline"
        >
          {REPO_LABEL}
        </a>
      </div>
    </div>
  );
}
