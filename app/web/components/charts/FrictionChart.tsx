// app/web/components/charts/FrictionChart.tsx
// Customer-friction rates across rounds: challenge, alert, decline.
//
// Phase 9: pure function of `metrics`.
//
// All three series are plotted on the same percentage y-axis. Block rate
// renders very small relative to challenge / alert — that visual flatness
// is the point: the safety story is that defensive fixes do not push
// friction beyond configured action-rate limits (Bible §6.1, §16.5).
// The aria_label and the per-series tooltips make this readable for
// screen-reader users.

import { formatRate } from "../../lib/formatters";
import { GLOSSARY } from "../../lib/glossary";
import type { MetricSnapshot } from "../../lib/types";
import { LinePlot, type LinePlotSeries } from "./LinePlot";

interface FrictionChartProps {
  metrics: MetricSnapshot[];
}

export function FrictionChart({ metrics }: FrictionChartProps) {
  const challenge: LinePlotSeries = {
    name: `${GLOSSARY.challenge_rate.plain} · ${GLOSSARY.challenge_rate.term}`,
    color_token: "accent",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.challenge_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  const alert: LinePlotSeries = {
    name: `${GLOSSARY.alert_rate.plain} · ${GLOSSARY.alert_rate.term}`,
    color_token: "warn",
    points: metrics.map((s) => ({
      x_label: s.round_label,
      value: s.alert_rate,
      is_anchor: s.kind !== "interpolated"
    }))
  };

  const decline: LinePlotSeries = {
    name: `${GLOSSARY.decline_rate.plain} · ${GLOSSARY.decline_rate.term}`,
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
      y_axis_label={GLOSSARY.friction_rates.plain}
      y_format={(v) => formatRate(v, { digits: 1 })}
      y_min={0}
      show_legend
      aria_label="How often we interrupt customers, customer-friction rates, across baseline and synthetic rounds. All series stay below the configured action-rate limits."
    />
  );
}
