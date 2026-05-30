// app/web/lib/formatters.ts
// Display helpers for the Project Atlas web shell.
//
// All synthetic-loss currency rendering MUST go through formatSyntheticCurrency.
// CLAUDE.md non-negotiable safety rule: never emit a bare "$" — every monetary
// figure carries a "SYN $" or "synthetic " token so a viewer cannot mistake
// the demo for a real-money system. The safety scanner depends on this.
//
// Rates here are fractions (0.0–1.0) consistent with judge metrics in
// project_atlas_sample_data.json. The formatters convert to percentages or
// basis points for display.

import type { DecisionAction } from "./types";

// Em-dash placeholder used whenever a value is non-finite. Centralizing it
// keeps "missing data" looking the same across the app.
export const NULL_PLACEHOLDER = "—";

// Tokens that must appear with every synthetic-currency display. Exported so
// tests and the safety scanner can reference the same constants.
export const SYNTHETIC_CURRENCY_PREFIX = "SYN $";
export const SYNTHETIC_CURRENCY_NEGATIVE_PREFIX = "−SYN $";
export const SYNTHETIC_CURRENCY_DISPLAY_SCALE = 100;

// ---------------------------------------------------------------------------
// formatRate(value, options?)
//
// Input: a fractional rate in [0, 1]. Output: percentage string with the
// configured decimal precision. Examples:
//   formatRate(0.0767)            -> "7.67%"
//   formatRate(0.44)              -> "44.00%"
//   formatRate(0.5800, {digits:1}) -> "58.0%"
// ---------------------------------------------------------------------------

export interface FormatRateOptions {
  digits?: number;
}

export function formatRate(value: number, options: FormatRateOptions = {}): string {
  if (!Number.isFinite(value)) return NULL_PLACEHOLDER;
  const digits = options.digits ?? 2;
  return `${(value * 100).toFixed(digits)}%`;
}

// ---------------------------------------------------------------------------
// formatBps(value)
//
// Input: a fractional rate in [0, 1]. Output: basis-points string. The
// conversion is rate × 10000. Decline rates in MetricSnapshot are fractions
// (0.0014 → "14 bps"); decline_rate_limit_bps in config is an integer (25 →
// pass it as 25 / 10000 = 0.0025 to format consistently, or use formatBps to
// only format already-fractional rates and keep raw bps as plain numbers in
// callers).
// ---------------------------------------------------------------------------

export function formatBps(value: number): string {
  if (!Number.isFinite(value)) return NULL_PLACEHOLDER;
  // Round to the nearest whole bp; sub-bp precision is noise for friction.
  const bps = Math.round(value * 10_000);
  return `${bps} bps`;
}

// ---------------------------------------------------------------------------
// formatSyntheticCurrency(amount, options?)
//
// Input: an integer amount of raw synthetic currency units (no implied real
// dollars). Output: a display-scaled value prefixed with "SYN $" and using
// thousands separators. Negative values get a leading minus sign before
// "SYN $" so a viewer never sees a bare "$" anywhere in the document.
//
// Examples:
//   formatSyntheticCurrency(184000)            -> "SYN $1,840"
//   formatSyntheticCurrency(91000)             -> "SYN $910"
//   formatSyntheticCurrency(-12500)            -> "−SYN $125"
//   formatSyntheticCurrency(184000, {compact:true}) -> "SYN $1.8K"
// ---------------------------------------------------------------------------

export interface FormatSyntheticCurrencyOptions {
  compact?: boolean;
  digits?: number;
}

const COMPACT_FORMATTER = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1
});

const STANDARD_FORMATTER = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0
});

export function formatSyntheticCurrency(
  amount: number,
  options: FormatSyntheticCurrencyOptions = {}
): string {
  if (!Number.isFinite(amount)) return NULL_PLACEHOLDER;
  const compact = options.compact ?? false;
  const formatter = compact
    ? COMPACT_FORMATTER
    : options.digits !== undefined
      ? new Intl.NumberFormat("en-US", { maximumFractionDigits: options.digits })
      : STANDARD_FORMATTER;

  const scaledAmount = amount / SYNTHETIC_CURRENCY_DISPLAY_SCALE;
  const isNegative = scaledAmount < 0;
  const magnitudeStr = formatter.format(Math.abs(scaledAmount));
  return isNegative
    ? `${SYNTHETIC_CURRENCY_NEGATIVE_PREFIX}${magnitudeStr}`
    : `${SYNTHETIC_CURRENCY_PREFIX}${magnitudeStr}`;
}

// ---------------------------------------------------------------------------
// formatDecisionAction(action)
//
// Input: the typed DecisionAction union from ./types.
// Output: a Title-Case display label. Falls back to NULL_PLACEHOLDER if an
// unexpected value sneaks through (defensive — TS prevents the case at
// compile time but runtime data may still be malformed).
// ---------------------------------------------------------------------------

const DECISION_ACTION_LABELS: Record<DecisionAction, string> = {
  accept: "Accept",
  challenge: "Challenge",
  alert: "Alert",
  decline: "Decline"
};

export function formatDecisionAction(action: DecisionAction): string {
  return DECISION_ACTION_LABELS[action] ?? NULL_PLACEHOLDER;
}
