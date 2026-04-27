// app/web/components/charts/FrictionChart.tsx
// Customer-friction rates across rounds: challenge, alert, decline.
//
// Phase 9: pure function of `metrics`.
//
// All three series are plotted on the same percentage y-axis. Decline rate
// renders very small relative to challenge / alert — that visual flatness
// is the point: the safety story is that defensive fixes do not push
// friction beyond configured action-rate limits (Bible §6.1, §16.5).
// The aria_label and the per-series tooltips make this readable for
// screen-reader users.

import { formatRate } from "../../lib/formatters";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface FrictionChartProps {
  metrics: MetricSnapshot[];
}

export function FrictionChart({ metrics }: FrictionChartProps) {
  const challenge: LinePlotSeries = {
    name: "Challenge rate",
    color_token: "accent",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.challenge_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  const alert: LinePlotSeries = {
    name: "Alert rate",
    color_token: "warn",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.alert_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  const decline: LinePlotSeries = {
    name: "Decline rate",
    color_token: "danger",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.decline_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  return (
    <LinePlot
      series={[challenge, alert, decline]}
      y_axis_label="Customer-friction rates"
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      show_legend
      aria_label="Customer-friction rates across baseline and synthetic rounds: challenge, alert, and decline. All series stay below the configured action-rate limits."
    />
  );
}
