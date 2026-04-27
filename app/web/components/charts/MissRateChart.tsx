// app/web/components/charts/MissRateChart.tsx
// Model-miss-rate trend across rounds.
//
// Phase 9: chart is a pure function of its `metrics` prop. The page
// (`app/web/app/page.tsx`) chooses the data source — live replay via
// `loadActiveReplay()` (component 8) or, in fixture-mode demos,
// `getRoundMetrics()`. Anchor dots are non-interpolated snapshots;
// hollow dots mark `kind === "interpolated"` (fixture-only).
//
// Axis labels stay synthetic-only: the y-axis reads "Model miss rate"
// (Bible §16.1) and tick values are percentages.

import { formatRate } from "../../lib/formatters";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface MissRateChartProps {
  metrics: MetricSnapshot[];
}

export function MissRateChart({ metrics }: MissRateChartProps) {
  const series: LinePlotSeries = {
    name: "Model miss rate",
    color_token: "danger",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.model_miss_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  return (
    <LinePlot
      series={[series]}
      y_axis_label="Model miss rate"
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      aria_label="Model miss rate across baseline and synthetic rounds; lower is better."
    />
  );
}
