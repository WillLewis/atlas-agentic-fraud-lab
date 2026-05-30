// app/web/components/charts/MissRateChart.tsx
// Model-miss-rate trend across rounds.
//
// Phase 9: chart is a pure function of its `metrics` prop. The page
// (`app/web/app/page.tsx`) chooses the data source — live replay via
// `loadActiveReplay()` (component 8) or, in fixture-mode demos,
// `getRoundMetrics()`. Anchor dots are non-interpolated snapshots;
// hollow dots mark `kind === "interpolated"` (fixture-only).
//
// Axis labels stay synthetic-only and tick values are percentages.

import { formatRate } from "../../lib/formatters";
import { GLOSSARY } from "../../lib/glossary";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface MissRateChartProps {
  metrics: MetricSnapshot[];
  candidate_metrics?: MetricSnapshot[];
}

export function MissRateChart({ metrics, candidate_metrics }: MissRateChartProps) {
  const carryForwardSeries: LinePlotSeries = {
    name: "Accepted state",
    color_token: "danger",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.model_miss_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };
  const selectedCandidateSeries: LinePlotSeries | null = candidate_metrics
    ? {
        name: "Proposed fix before judge decision",
        color_token: "accent",
        stroke_dasharray: "4 3",
        points: candidate_metrics.map((s) => ({
          x_label: s.round_label,
          value: s.model_miss_rate,
          is_anchor: s.kind !== "interpolated"
        }))
      }
    : null;
  const series = selectedCandidateSeries
    ? [carryForwardSeries, selectedCandidateSeries]
    : [carryForwardSeries];

  return (
    <LinePlot
      series={series}
      y_axis_label={GLOSSARY.model_miss_rate.plain}
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      show_legend={series.length > 1}
      aria_label="Missed risky activity, model miss rate, across baseline and synthetic rounds; lower is better."
    />
  );
}
