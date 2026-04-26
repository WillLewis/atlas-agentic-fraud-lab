// app/web/components/charts/MissRateChart.tsx
// Model-miss-rate trend across rounds. Source: getRoundMetrics() — round 0
// (Baseline) and round 1 are real judge values from the fixture; rounds 2
// and 3 are Phase 1 placeholder extrapolations and rendered with hollow
// dots via LinePlot's is_anchor flag.
//
// Axis labels stay synthetic-only: the y-axis reads "Model miss rate"
// (Bible §16.1) and tick values are percentages.

import { getRoundMetrics } from "../../lib/fixtures";
import { formatRate } from "../../lib/formatters";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

export function MissRateChart() {
  const snapshots = getRoundMetrics();

  const series: LinePlotSeries = {
    name: "Model miss rate",
    color_token: "danger",
    points: snapshots.map((s) => ({
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
      aria_label="Model miss rate across baseline and three synthetic rounds; lower is better."
    />
  );
}
