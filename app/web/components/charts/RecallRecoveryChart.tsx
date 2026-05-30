// app/web/components/charts/RecallRecoveryChart.tsx
// Risk-catch recovery across rounds.
//
// Phase 9: pure function of `metrics`. Up is good for this metric.
//
// Bible §16.3: recall_at_fixed_action_rate is the right metric for "did
// the fix actually catch more high-risk synthetic events without
// raising customer friction?" The chart axis label names the
// fixed-action-rate context so a viewer doesn't read it as a general
// recall metric.

import { formatRate } from "../../lib/formatters";
import { GLOSSARY } from "../../lib/glossary";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface RecallRecoveryChartProps {
  metrics: MetricSnapshot[];
  candidate_metrics?: MetricSnapshot[];
}

export function RecallRecoveryChart({
  metrics,
  candidate_metrics
}: RecallRecoveryChartProps) {
  const carryForwardSeries: LinePlotSeries = {
    name: "Accepted state",
    color_token: "ok",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.recall_at_fixed_action_rate,
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
          value: s.recall_at_fixed_action_rate,
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
      y_axis_label={GLOSSARY.recall.plain}
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      y_max={1}
      show_legend={series.length > 1}
      aria_label="Risky activity caught, recall at fixed action-rate, across baseline and synthetic rounds; higher is better."
    />
  );
}
