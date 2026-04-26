// app/web/components/charts/RecallRecoveryChart.tsx
// Recall at fixed action-rate limit, across rounds.
//
// Bible §16.3: recall_at_fixed_action_rate is the right metric for "did the
// fix actually catch more high-risk synthetic events without raising
// customer friction?" Up is good for this metric. The chart axis label
// names the fixed-action-rate context so a viewer doesn't read it as a
// general recall metric.

import { getRoundMetrics } from "../../lib/fixtures";
import { formatRate } from "../../lib/formatters";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

export function RecallRecoveryChart() {
  const snapshots = getRoundMetrics();

  const series: LinePlotSeries = {
    name: "Recall at fixed action-rate limit",
    color_token: "ok",
    points: snapshots.map((s) => ({
      x_label: s.round_label,
      value: s.recall_at_fixed_action_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  return (
    <LinePlot
      series={[series]}
      y_axis_label="Recall at fixed action-rate"
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      y_max={1}
      aria_label="Recall at the fixed action-rate limit across baseline and three rounds; higher is better."
    />
  );
}
