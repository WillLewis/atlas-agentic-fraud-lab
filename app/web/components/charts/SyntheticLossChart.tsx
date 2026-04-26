// app/web/components/charts/SyntheticLossChart.tsx
// Synthetic loss allowed across rounds.
//
// SAFETY: y-axis labels and tooltips MUST go through formatSyntheticCurrency
// so the "SYN $" token always prefixes monetary values. CLAUDE.md
// non-negotiable: never emit a bare "$" anywhere. Compact notation
// (formatSyntheticCurrency(v, {compact:true})) keeps tick labels short
// without dropping the prefix.

import { getRoundMetrics } from "../../lib/fixtures";
import { formatSyntheticCurrency } from "../../lib/formatters";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

export function SyntheticLossChart() {
  const snapshots = getRoundMetrics();

  const series: LinePlotSeries = {
    name: "Synthetic loss allowed",
    color_token: "warn",
    points: snapshots.map((s) => ({
      x_label: s.round_label,
      value: s.synthetic_loss_allowed,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  return (
    <LinePlot
      series={[series]}
      y_axis_label="Synthetic loss allowed"
      y_format={(v) => formatSyntheticCurrency(v, { compact: true })}
      y_min={0}
      aria_label="Synthetic loss allowed across baseline and three rounds, in synthetic currency units; lower is better."
    />
  );
}
