// app/web/components/EnvironmentOverview.tsx
// Step 2 content — synthetic environment cards.
//
// Six cards summarize what the agents are deployed into:
//   1. Synthetic customer population
//   2. Synthetic event stream
//   3. Local mock scoring API
//   4. Baseline decision-threshold overlay
//   5. Baseline model metrics
//   6. Holdouts (clean / found adaptive / locked adaptive / drifted)
//
// Bible §8 Step 2 main message: "The mock institution starts with a plausible
// account-takeover risk scorer and fixed customer-friction limits."
//
// Public-mode labels (institution_label, model_label, api.base_url) come from
// getDemoConfig() per CLAUDE.md / Bible §7.3. All other UI strings live as
// structured constants below so the safety scanner can inspect them as data.

import { getDemoConfig } from "../lib/demoConfig";
import { getEntityCounts, getRoundMetrics } from "../lib/fixtures";
import { formatBps, formatRate, formatSyntheticCurrency } from "../lib/formatters";

// ---------------------------------------------------------------------------
// Step 2 narrative
// ---------------------------------------------------------------------------

const STEP_HEADING = "Agents Deployed";
const STEP_SUBHEADING = "Step 2";
const STEP_MAIN_MESSAGE =
  "The mock institution starts with a plausible account-takeover risk scorer and fixed customer-friction limits.";

// ---------------------------------------------------------------------------
// Synthetic event stream — mirrors config/synthetic_schema.yaml
// `events.allowed_types`. Phase 4 will hydrate this from /schema.
// ---------------------------------------------------------------------------

const SYNTHETIC_EVENT_TYPES: readonly string[] = [
  "login_success",
  "login_challenge_required",
  "challenge_passed",
  "challenge_failed",
  "password_recovery_completed",
  "username_recovery_completed",
  "profile_update",
  "recipient_added",
  "external_account_link_attempt",
  "instant_transfer_attempt",
  "external_transfer_attempt",
  "large_transfer_attempt"
];

// ---------------------------------------------------------------------------
// Decision-threshold overlay — mirrors config/decision_thresholds.yaml.
// Phase 4 will hydrate this from /decision-thresholds. Values here are
// synthetic demo constants, not real institution-specific controls
// (Bible §6.1 rule 3, §12.4).
// ---------------------------------------------------------------------------

const BASELINE_DECISION_THRESHOLDS: ReadonlyArray<{
  display_name: string;
  threshold: number;
}> = [
  { display_name: "Decline score threshold", threshold: 0.92 },
  { display_name: "Alert score threshold", threshold: 0.86 },
  { display_name: "Challenge score threshold", threshold: 0.74 }
];

// Action-rate limits in fractional form so formatRate / formatBps can render
// them consistently. Phase 4 hydrates from the same /decision-thresholds
// route.
const BASELINE_ACTION_RATE_LIMITS: ReadonlyArray<{
  display_name: string;
  limit_value: number;
  formatter: "rate" | "bps";
}> = [
  { display_name: "Challenge rate", limit_value: 0.08, formatter: "rate" },
  { display_name: "Alert rate", limit_value: 0.15, formatter: "rate" },
  { display_name: "Decline rate", limit_value: 0.0025, formatter: "bps" },
  { display_name: "Review rate", limit_value: 0.03, formatter: "rate" }
];

// ---------------------------------------------------------------------------
// Holdouts — mirrors config/synthetic_schema.yaml `splits.partitions`.
// Descriptions paraphrase Bible §6.1 rule 8 and §14 step 10.
// ---------------------------------------------------------------------------

interface HoldoutDescription {
  id: string;
  display_name: string;
  locked: boolean;
  purpose: string;
}

const HOLDOUTS: readonly HoldoutDescription[] = [
  {
    id: "clean_holdout",
    display_name: "Clean Holdout",
    locked: false,
    purpose:
      "Customer-level holdout drawn before any red-team activity. Measures whether a fix improves recall on unseen customers."
  },
  {
    id: "found_adaptive_set",
    display_name: "Found Adaptive Set",
    locked: false,
    purpose:
      "Synthetic candidates the red-team agents surfaced during the round. Used only to show what the fix improves on examples we already found."
  },
  {
    id: "locked_adaptive_holdout",
    display_name: "Locked Adaptive Holdout",
    locked: true,
    purpose:
      "Adaptive variants the simulation agents do not see. Catches defensive fixes that overfit to found examples."
  },
  {
    id: "drifted_holdout",
    display_name: "Drifted Holdout",
    locked: true,
    purpose:
      "Synthetic distribution-shifted holdout. Measures how a fix generalizes under modest synthetic drift."
  }
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EnvironmentOverview() {
  const config = getDemoConfig();
  const counts = getEntityCounts();
  const baseline = getRoundMetrics()[0];
  if (!baseline) {
    throw new Error(
      "EnvironmentOverview: getRoundMetrics() returned no baseline snapshot."
    );
  }

  const totalEventCount =
    counts.login_sessions + counts.security_events + counts.transfer_events;

  return (
    <section
      id="agents-deployed"
      aria-labelledby="agents-deployed-heading"
      className="scroll-mt-16 px-8 py-16"
    >
      <header className="mb-10 max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          {STEP_SUBHEADING}
        </p>
        <h2
          id="agents-deployed-heading"
          className="mt-2 text-3xl font-semibold tracking-tight text-atlas-text"
        >
          {STEP_HEADING}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">{STEP_MAIN_MESSAGE}</p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card eyebrow="Population" title="Synthetic customers">
          <DefinitionRow label="Customers loaded" value={String(counts.customers)} />
          <DefinitionRow label="Accounts" value={String(counts.accounts)} />
          <DefinitionRow label="Devices" value={String(counts.devices)} />
          <DefinitionRow label="Recipients" value={String(counts.recipients)} />
          <DefinitionRow label="External accounts" value={String(counts.external_accounts)} />
          <DefinitionRow label="Graph edges" value={String(counts.graph_edges)} />
          <Footnote>Fixture sample. Phase 2 generates the full synthetic population.</Footnote>
        </Card>

        <Card eyebrow="Event stream" title="Synthetic event types">
          <DefinitionRow
            label="Total events in fixture"
            value={String(totalEventCount)}
          />
          <ul className="mt-3 grid grid-cols-1 gap-1 font-mono text-[11px] text-atlas-text/80">
            {SYNTHETIC_EVENT_TYPES.map((evt) => (
              <li key={evt} className="flex items-center gap-2">
                <span aria-hidden="true" className="h-1 w-1 rounded-full bg-atlas-accent/60" />
                {evt}
              </li>
            ))}
          </ul>
          <Footnote>Allowed event types from synthetic_schema.</Footnote>
        </Card>

        <Card eyebrow="Scoring" title="Local mock scoring API">
          <DefinitionRow label="Institution" value={config.institution_label} />
          <DefinitionRow label="Model" value={config.model_label} />
          <DefinitionRow
            label="Endpoint"
            value={config.api.base_url}
            mono
          />
          <DefinitionRow label="Posture" value="Local-only" />
          <Footnote>Phase 4 brings the FastAPI service up; Phase 1 renders the configured surface only.</Footnote>
        </Card>

        <Card eyebrow="Decision overlay" title="Baseline thresholds">
          {BASELINE_DECISION_THRESHOLDS.map((t) => (
            <DefinitionRow
              key={t.display_name}
              label={t.display_name}
              value={t.threshold.toFixed(2)}
              mono
            />
          ))}
          <div className="mt-3 border-t border-atlas-border/60 pt-3">
            <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
              Action-rate limits
            </p>
            <div className="mt-2 space-y-1">
              {BASELINE_ACTION_RATE_LIMITS.map((l) => (
                <DefinitionRow
                  key={l.display_name}
                  label={l.display_name}
                  value={
                    l.formatter === "rate"
                      ? `≤ ${formatRate(l.limit_value, { digits: 2 })}`
                      : `≤ ${formatBps(l.limit_value)}`
                  }
                  mono
                />
              ))}
            </div>
          </div>
          <Footnote>Synthetic demo constants. Not real institution-specific controls.</Footnote>
        </Card>

        <Card eyebrow="Baseline metrics" title="Pre-round 1 model state">
          <DefinitionRow
            label="Model miss rate"
            value={formatRate(baseline.model_miss_rate)}
            mono
          />
          <DefinitionRow
            label="Recall at fixed action-rate"
            value={formatRate(baseline.recall_at_fixed_action_rate)}
            mono
          />
          <DefinitionRow
            label="False-positive rate"
            value={formatRate(baseline.false_positive_rate_at_fixed_action_rate)}
            mono
          />
          <DefinitionRow
            label="Synthetic loss allowed"
            value={formatSyntheticCurrency(baseline.synthetic_loss_allowed)}
            mono
          />
          <Footnote>From judge baseline in the fixture replay record.</Footnote>
        </Card>

        <Card eyebrow="Splits" title="Holdouts">
          <ul className="space-y-3">
            {HOLDOUTS.map((h) => (
              <li key={h.id} className="border-l-2 border-atlas-border pl-3">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-semibold text-atlas-text">{h.display_name}</span>
                  {h.locked ? (
                    <span
                      className="font-mono text-[9px] uppercase tracking-wider text-atlas-warn"
                      aria-label="Locked from simulation agents"
                    >
                      Locked
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-xs leading-relaxed text-atlas-muted">{h.purpose}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Card primitive (local — promoted to a shared component if reuse grows)
// ---------------------------------------------------------------------------

interface CardProps {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}

function Card({ eyebrow, title, children }: CardProps) {
  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
        {eyebrow}
      </p>
      <h3 className="mt-1 text-base font-semibold text-atlas-text">{title}</h3>
      <div className="mt-3 flex flex-col">{children}</div>
    </article>
  );
}

interface DefinitionRowProps {
  label: string;
  value: string;
  mono?: boolean;
}

function DefinitionRow({ label, value, mono }: DefinitionRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-xs">
      <span className="text-atlas-muted">{label}</span>
      <span
        className={
          mono
            ? "text-atlas-text font-mono tabular-nums"
            : "text-atlas-text"
        }
      >
        {value}
      </span>
    </div>
  );
}

function Footnote({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 border-t border-atlas-border/60 pt-2 text-[11px] leading-relaxed text-atlas-muted">
      {children}
    </p>
  );
}
