// app/web/components/MetricCard.tsx
// Reusable metric display.
//
// Props: label, value, format type, optional baseline-vs-fixed comparison.
// Trend arrow is derived from the comparison block when present, so callers
// don't have to set arrow direction manually.
//
// Values flow exclusively through the typed formatters in lib/formatters.ts;
// callers must pass numbers, not pre-formatted strings. This keeps the
// safety scanner's bare-"$" contract enforceable in one place
// (formatSyntheticCurrency).

import {
  NULL_PLACEHOLDER,
  formatBps,
  formatRate,
  formatSyntheticCurrency
} from "../lib/formatters";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MetricFormat = "rate" | "bps" | "synthetic_currency" | "raw";

export type ImprovementDirection = "down_is_good" | "up_is_good";

export interface MetricComparison {
  baseline_value: number;
  improvement_direction: ImprovementDirection;
  // Optional override of the baseline label shown in the comparison row
  // (defaults to "from"). Useful for "vs Round 1" wording in Phase 9.
  baseline_label?: string;
}

export interface MetricCardProps {
  label: string;
  value: number;
  format: MetricFormat;
  comparison?: MetricComparison;
  hint?: string;
}

// ---------------------------------------------------------------------------
// Format dispatch
// ---------------------------------------------------------------------------

function formatValue(value: number, format: MetricFormat): string {
  if (!Number.isFinite(value)) return NULL_PLACEHOLDER;
  switch (format) {
    case "rate":
      return formatRate(value);
    case "bps":
      return formatBps(value);
    case "synthetic_currency":
      return formatSyntheticCurrency(value);
    case "raw":
      return value.toLocaleString("en-US", { maximumFractionDigits: 4 });
  }
}

// Format a delta in the same units as the underlying metric. Always carries
// an explicit sign so the direction is unambiguous in copy.
function formatDelta(delta: number, format: MetricFormat): string {
  if (!Number.isFinite(delta)) return NULL_PLACEHOLDER;
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
  const magnitude = Math.abs(delta);
  switch (format) {
    case "rate":
      // Rates are fractions; show the change in percentage points.
      return `${sign}${(magnitude * 100).toFixed(2)} pp`;
    case "bps":
      return `${sign}${Math.round(magnitude * 10_000)} bps`;
    case "synthetic_currency":
      // Reuse formatSyntheticCurrency so the bare-$ contract holds.
      return `${sign}${formatSyntheticCurrency(magnitude)}`;
    case "raw":
      return `${sign}${magnitude.toLocaleString("en-US", { maximumFractionDigits: 4 })}`;
  }
}

// Relative percentage change vs baseline. Returns NULL_PLACEHOLDER when the
// baseline is zero (avoids divide-by-zero) or non-finite.
function formatRelative(value: number, baseline: number): string {
  if (!Number.isFinite(value) || !Number.isFinite(baseline) || baseline === 0) {
    return NULL_PLACEHOLDER;
  }
  const rel = (value - baseline) / Math.abs(baseline);
  const sign = rel > 0 ? "+" : rel < 0 ? "−" : "±";
  return `${sign}${(Math.abs(rel) * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MetricCard({ label, value, format, comparison, hint }: MetricCardProps) {
  const valueStr = formatValue(value, format);
  const trendInfo = comparison ? deriveTrend(value, comparison) : null;

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        {label}
      </p>
      <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-atlas-text">
        {valueStr}
      </p>
      {trendInfo && comparison ? (
        <p
          className={[
            "mt-2 flex items-baseline gap-1.5 text-[11px]",
            trendInfo.tone === "good"
              ? "text-atlas-ok"
              : trendInfo.tone === "bad"
                ? "text-atlas-danger"
                : "text-atlas-muted"
          ].join(" ")}
        >
          <span aria-hidden="true" className="text-sm leading-none">
            {trendInfo.arrow}
          </span>
          <span className="font-mono">
            {formatDelta(value - comparison.baseline_value, format)}
          </span>
          <span className="text-atlas-muted">
            ({formatRelative(value, comparison.baseline_value)})
          </span>
          <span className="text-atlas-muted">
            {comparison.baseline_label ?? "from"}{" "}
            <span className="font-mono">
              {formatValue(comparison.baseline_value, format)}
            </span>
          </span>
        </p>
      ) : null}
      {hint ? (
        <p className="mt-3 border-t border-atlas-border/60 pt-2 text-[11px] leading-relaxed text-atlas-muted">
          {hint}
        </p>
      ) : null}
    </article>
  );
}

// ---------------------------------------------------------------------------
// Trend derivation
// ---------------------------------------------------------------------------

interface TrendInfo {
  arrow: "↑" | "↓" | "→";
  tone: "good" | "bad" | "neutral";
}

function deriveTrend(value: number, comparison: MetricComparison): TrendInfo {
  const delta = value - comparison.baseline_value;
  if (!Number.isFinite(delta) || delta === 0) {
    return { arrow: "→", tone: "neutral" };
  }
  const arrow: "↑" | "↓" = delta > 0 ? "↑" : "↓";
  const isImprovement =
    comparison.improvement_direction === "down_is_good" ? delta < 0 : delta > 0;
  return {
    arrow,
    tone: isImprovement ? "good" : "bad"
  };
}
