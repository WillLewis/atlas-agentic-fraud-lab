// app/web/components/charts/SyntheticLossChart.tsx
// Demo losses let through across rounds.
//
// Phase 9: pure function of `metrics`.
//
// SAFETY: y-axis labels and tooltips MUST go through formatSyntheticCurrency
// so the "SYN $" token always prefixes monetary values. CLAUDE.md
// non-negotiable: never emit a bare dollar sign anywhere. Compact notation
// (formatSyntheticCurrency(v, {compact:true})) keeps tick labels short
// without dropping the prefix.

import { formatSyntheticCurrency } from "../../lib/formatters";
import { GLOSSARY } from "../../lib/glossary";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface SyntheticLossChartProps {
  metrics: MetricSnapshot[];
  candidate_metrics?: MetricSnapshot[];
}

export function SyntheticLossChart({
  metrics,
  candidate_metrics
}: SyntheticLossChartProps) {
  const carryForwardSeries: LinePlotSeries = {
    name: "Carry-forward state",
    color_token: "warn",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.synthetic_loss_allowed,
      is_anchor: s.kind !== "interpolated"
    }))
  };
  const selectedCandidateSeries: LinePlotSeries | null = candidate_metrics
    ? {
        name: "Selected candidate result",
        color_token: "accent",
        stroke_dasharray: "4 3",
        points: candidate_metrics.map((s) => ({
          x_label: s.round_label,
          value: s.synthetic_loss_allowed,
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
      y_axis_label={GLOSSARY.synthetic_loss_allowed.plain}
      y_format={(v) => formatSyntheticCurrency(v, { compact: true })}
      y_min={0}
      show_legend={series.length > 1}
      aria_label="Demo losses let through, synthetic loss allowed, across baseline and synthetic rounds, in synthetic currency units; lower is better."
    />
  );
}
