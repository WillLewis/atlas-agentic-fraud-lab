// app/web/components/charts/LinePlot.tsx
// Shared SVG line-chart primitive for Phase 1 placeholder charts.
//
// The four chart components (MissRate, SyntheticLoss, RecallRecovery,
// Friction) wrap this primitive with their data extraction and unit
// formatters. No charting library — plain SVG so the bundle stays small
// and the safety scanner sees plain attribute strings rather than chart
// library magic.
//
// Anchor vs interpolated points: filled dots for is_anchor=true (real
// judge-derived values from the fixture), hollow dots for is_anchor=false
// (Phase 1 placeholder extrapolations from fixtures.ts). This visual
// distinction is the user-visible analogue of MetricSnapshot.kind.

import type { CSSProperties, JSX } from "react";

import { ChartReveal } from "./ChartReveal";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SeriesColorToken = "accent" | "danger" | "warn" | "ok";

export interface LinePlotPoint {
  x_label: string;
  value: number;
  is_anchor: boolean;
}

export interface LinePlotSeries {
  name: string;
  color_token: SeriesColorToken;
  points: ReadonlyArray<LinePlotPoint>;
  stroke_dasharray?: string;
}

export interface LinePlotProps {
  series: ReadonlyArray<LinePlotSeries>;
  /** Short axis label. */
  y_axis_label: string;
  /** Formatter applied to y-axis tick labels and point tooltips. */
  y_format: (value: number) => string;
  /** Forced y-axis bounds. If absent, computed from the data with 10% headroom. */
  y_min?: number;
  y_max?: number;
  /** Render a legend above the plot when multi-series. */
  show_legend?: boolean;
  /** Accessible chart description. */
  aria_label: string;
}

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const VIEWBOX_WIDTH = 520;
const VIEWBOX_HEIGHT = 248;
const PADDING_TOP = 28;
const PADDING_RIGHT = 44;
const PADDING_BOTTOM = 46;
const PADDING_LEFT = 78;

const PLOT_WIDTH = VIEWBOX_WIDTH - PADDING_LEFT - PADDING_RIGHT;
const PLOT_HEIGHT = VIEWBOX_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
const PLOT_X0 = PADDING_LEFT;
const PLOT_Y0 = PADDING_TOP + PLOT_HEIGHT;

const Y_TICK_FRACTIONS = [0, 0.25, 0.5, 0.75, 1] as const;

const SERIES_COLOR_CLASS: Record<SeriesColorToken, string> = {
  accent: "text-atlas-accent",
  danger: "text-atlas-danger",
  warn: "text-atlas-warn",
  ok: "text-atlas-ok"
};

const ANCHOR_HOLLOW_FILL = "var(--atlas-chart-empty-fill)";
const GRID_STROKE = "var(--atlas-chart-grid)";

function animationDelay(seriesIndex: number, pointIndex = 0): number {
  return 180 + seriesIndex * 130 + pointIndex * 120;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LinePlot({
  series,
  y_axis_label,
  y_format,
  y_min,
  y_max,
  show_legend = false,
  aria_label
}: LinePlotProps): JSX.Element {
  const numPoints = series[0]?.points.length ?? 0;
  const flatValues = series.flatMap((s) => s.points.map((p) => p.value));

  const dataMin = flatValues.length > 0 ? Math.min(...flatValues) : 0;
  const dataMax = flatValues.length > 0 ? Math.max(...flatValues) : 1;
  const computedMin = y_min ?? Math.min(0, dataMin);
  const computedMax = y_max ?? dataMax * 1.1;
  // Guard against zero-range collapse (e.g., flat series).
  const range = computedMax - computedMin || 1;

  const xAt = (i: number): number =>
    numPoints <= 1
      ? PLOT_X0 + PLOT_WIDTH / 2
      : PLOT_X0 + (i * PLOT_WIDTH) / (numPoints - 1);
  const yAt = (val: number): number =>
    PLOT_Y0 - ((val - computedMin) / range) * PLOT_HEIGHT;

  const yTicks = Y_TICK_FRACTIONS.map((f) => computedMin + f * range);

  // X-axis labels come from the first series; all series share the same
  // x positions (round labels). Defensive: if a multi-series chart somehow
  // has mismatched x labels, we still draw the first series's labels.
  const xLabels = series[0]?.points.map((p) => p.x_label) ?? [];

  const seriesLayouts = series.map((s, seriesIndex) => {
    const pathD = s.points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i)} ${yAt(p.value)}`)
      .join(" ");
    const changedSegments = s.points.flatMap((p, i) => {
      const previous = s.points[i - 1];
      if (!previous || previous.value === p.value) {
        return [];
      }
      return [
        {
          key: `${s.name}-change-${i}`,
          d: `M ${xAt(i - 1)} ${yAt(previous.value)} L ${xAt(i)} ${yAt(p.value)}`,
          delay: animationDelay(seriesIndex, i) + 150
        }
      ];
    });

    return { series: s, pathD, changedSegments };
  });

  return (
    <ChartReveal>
      {show_legend && series.length > 1 ? (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-atlas-muted">
          {series.map((s) => (
            <span
              key={s.name}
              className={`inline-flex items-center gap-1.5 ${SERIES_COLOR_CLASS[s.color_token]}`}
            >
              <span
                aria-hidden="true"
                className={[
                  "inline-block h-0 w-4 border-t-2 border-current",
                  s.stroke_dasharray ? "border-dashed" : "border-solid"
                ].join(" ")}
              />
              <span className="text-atlas-text">{s.name}</span>
            </span>
          ))}
        </div>
      ) : null}

      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="block h-auto w-full"
        role="img"
        aria-label={aria_label}
      >
        {/* Y-axis label */}
        <text
          x={PLOT_X0}
          y={14}
          className="fill-atlas-muted font-mono text-[10px] uppercase tracking-wider"
        >
          {y_axis_label}
        </text>

        {/* Gridlines + y-axis tick labels */}
        {yTicks.map((tick, i) => (
          <g key={`ytick-${i}`}>
            <line
              x1={PLOT_X0}
              x2={VIEWBOX_WIDTH - PADDING_RIGHT}
              y1={yAt(tick)}
              y2={yAt(tick)}
              stroke={GRID_STROKE}
              strokeDasharray="2 3"
              strokeWidth={1}
            />
            <text
              x={PLOT_X0 - 6}
              y={yAt(tick) + 3}
              textAnchor="end"
              className="fill-atlas-muted font-mono text-[9px] tabular-nums"
            >
              {y_format(tick)}
            </text>
          </g>
        ))}

        {/* X-axis labels */}
        {xLabels.map((label, i) => (
          <text
            key={`xlabel-${i}`}
            x={xAt(i)}
            y={PLOT_Y0 + 18}
            textAnchor={i === 0 ? "start" : i === xLabels.length - 1 ? "end" : "middle"}
            className="fill-atlas-muted text-[10px]"
          >
            {label}
          </text>
        ))}

        {/* Data series */}
        {seriesLayouts.map(({ series: s, pathD, changedSegments }, seriesIndex) => (
          <g
            key={s.name}
            className={`line-plot-series ${SERIES_COLOR_CLASS[s.color_token]}`}
            color="currentColor"
            style={
              {
                "--series-delay": `${seriesIndex * 120}ms`
              } as CSSProperties
            }
          >
            <path
              d={pathD}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.6}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray={s.stroke_dasharray}
            />
            {changedSegments.map((segment) => (
              <path
                key={segment.key}
                d={segment.d}
                fill="none"
                stroke="currentColor"
                strokeWidth={3.2}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className="line-plot-change-segment"
                style={
                  {
                    "--segment-delay": `${segment.delay}ms`
                  } as CSSProperties
                }
              />
            ))}
            {s.points.map((p, i) => (
              <circle
                key={`${s.name}-pt-${i}`}
                cx={xAt(i)}
                cy={yAt(p.value)}
                r={3.5}
                fill={p.is_anchor ? "currentColor" : ANCHOR_HOLLOW_FILL}
                stroke="currentColor"
                strokeWidth={1.6}
                className="line-plot-point"
                style={
                  {
                    "--point-delay": `${animationDelay(seriesIndex, i)}ms`
                  } as CSSProperties
                }
              >
                <title>{`${s.name} · ${p.x_label}: ${y_format(p.value)}${p.is_anchor ? "" : " (placeholder)"}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>

      <figcaption className="sr-only">{aria_label}</figcaption>
    </ChartReveal>
  );
}
