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
import { GLOSSARY } from "../lib/glossary";
import { TermNote } from "./DualLabel";

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
  term: string;
  definition: string;
  threshold: number;
}> = [
  {
    display_name: "Block above",
    term: "decline score threshold",
    definition: GLOSSARY.decline_threshold.definition,
    threshold: 0.92
  },
  {
    display_name: "Review above",
    term: "alert score threshold",
    definition: GLOSSARY.alert_threshold.definition,
    threshold: 0.86
  },
  {
    display_name: "Verify above",
    term: "challenge score threshold",
    definition: GLOSSARY.challenge_threshold.definition,
    threshold: 0.74
  }
];

// Action-rate limits in fractional form so formatRate / formatBps can render
// them consistently. Phase 4 hydrates from the same /decision-thresholds
// route.
const BASELINE_ACTION_RATE_LIMITS: ReadonlyArray<{
  display_name: string;
  term: string;
  definition: string;
  limit_value: number;
  formatter: "rate" | "bps";
}> = [
  {
    display_name: "Step-up checks",
    term: "challenge rate",
    definition: GLOSSARY.challenge_rate.definition,
    limit_value: 0.08,
    formatter: "rate"
  },
  {
    display_name: "Sent to review",
    term: "alert rate",
    definition: GLOSSARY.alert_rate.definition,
    limit_value: 0.15,
    formatter: "rate"
  },
  {
    display_name: "Blocked outright",
    term: "decline rate",
    definition: GLOSSARY.decline_rate.definition,
    limit_value: 0.0025,
    formatter: "bps"
  },
  {
    display_name: "Manual review",
    term: "review rate",
    definition: GLOSSARY.review_rate.definition,
    limit_value: 0.03,
    formatter: "rate"
  }
];

// ---------------------------------------------------------------------------
// Holdouts — mirrors config/synthetic_schema.yaml `splits.partitions`.
// Descriptions paraphrase Bible §6.1 rule 8 and §14 step 10.
// ---------------------------------------------------------------------------

interface HoldoutDescription {
  id: string;
  display_name: string;
  term: string;
  locked: boolean;
  purpose: string;
}

const HOLDOUTS: readonly HoldoutDescription[] = [
  {
    id: "clean_holdout",
    display_name: "Fresh customers (never tested)",
    term: "clean holdout",
    locked: false,
    purpose: GLOSSARY.clean_holdout.definition
  },
  {
    id: "found_adaptive_set",
    display_name: "Cases we already found",
    term: "found adaptive set",
    locked: false,
    purpose: GLOSSARY.found_adaptive_set.definition
  },
  {
    id: "locked_adaptive_holdout",
    display_name: "Hidden stress test",
    term: "locked adaptive holdout",
    locked: true,
    purpose: GLOSSARY.locked_adaptive_holdout.definition
  },
  {
    id: "drifted_holdout",
    display_name: "Future-drift test",
    term: "drifted holdout",
    locked: true,
    purpose: GLOSSARY.drifted_holdout.definition
  }
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface EnvironmentOverviewProps {
  sectionId?: string;
  showHeader?: boolean;
}

export function EnvironmentOverview({
  sectionId = "agents-deployed",
  showHeader = true
}: EnvironmentOverviewProps = {}) {
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
      id={sectionId}
      {...(showHeader
        ? { "aria-labelledby": "agents-deployed-heading" }
        : { "aria-label": "Synthetic demo environment details" })}
      className={[
        "atlas-data-section px-8 py-16",
        showHeader ? "scroll-mt-16" : "border-t border-atlas-border/40"
      ].join(" ")}
    >
      {showHeader ? (
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
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card eyebrow="Population" title="Synthetic customers">
          <DefinitionRow label="Customers loaded" value={String(counts.customers)} />
          <DefinitionRow label="Accounts" value={String(counts.accounts)} />
          <DefinitionRow label="Devices" value={String(counts.devices)} />
          <DefinitionRow label="Recipients" value={String(counts.recipients)} />
          <DefinitionRow label="External accounts" value={String(counts.external_accounts)} />
          <DefinitionRow label="Graph edges" value={String(counts.graph_edges)} />
          <Footnote>A representative sample of the synthetic population.</Footnote>
        </Card>

        <Card eyebrow="Event stream" title="Synthetic event types">
          <DefinitionRow
            label="Total events in this sample"
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
          <Footnote>The activity types the agents can work with.</Footnote>
        </Card>

        <Card eyebrow="Scoring" title="Local mock scoring API">
          <DefinitionRow label="Institution" value={config.institution_label} />
          <DefinitionRow label="Model" value={config.model_label} />
          <DefinitionRow
            label="Scoring surface"
            value="Local mock API"
            mono
          />
          <DefinitionRow label="Posture" value="Local-only" />
          <Footnote>Scored locally by the mock risk model — no real systems involved.</Footnote>
        </Card>

        <Card eyebrow="Decision overlay" title="Baseline thresholds">
          {BASELINE_DECISION_THRESHOLDS.map((t) => (
            <DefinitionRow
              key={t.display_name}
              label={t.display_name}
              term={t.term}
              title={t.definition}
              value={t.threshold.toFixed(2)}
              mono
            />
          ))}
          <div className="mt-3 border-t border-atlas-border/60 pt-3">
            <div title={GLOSSARY.action_rate_limits.definition}>
              <p className="text-xs font-medium text-atlas-text">
                {GLOSSARY.action_rate_limits.plain}
              </p>
              <TermNote>{GLOSSARY.action_rate_limits.term}</TermNote>
            </div>
            <div className="mt-2 space-y-1">
              {BASELINE_ACTION_RATE_LIMITS.map((l) => (
                <DefinitionRow
                  key={l.display_name}
                  label={l.display_name}
                  term={l.term}
                  title={l.definition}
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

        <Card eyebrow={GLOSSARY.baseline_state.term} title={GLOSSARY.baseline_state.plain}>
          <DefinitionRow
            label={GLOSSARY.model_miss_rate.plain}
            term={GLOSSARY.model_miss_rate.term}
            title={GLOSSARY.model_miss_rate.definition}
            value={formatRate(baseline.model_miss_rate)}
            mono
          />
          <DefinitionRow
            label={GLOSSARY.recall.plain}
            term={GLOSSARY.recall.term}
            title={GLOSSARY.recall.definition}
            value={formatRate(baseline.recall_at_fixed_action_rate)}
            mono
          />
          <DefinitionRow
            label={GLOSSARY.false_positive_rate.plain}
            term={GLOSSARY.false_positive_rate.term}
            title={GLOSSARY.false_positive_rate.definition}
            value={formatRate(baseline.false_positive_rate_at_fixed_action_rate)}
            mono
          />
          <DefinitionRow
            label={GLOSSARY.synthetic_loss_allowed.plain}
            term={GLOSSARY.synthetic_loss_allowed.term}
            title={GLOSSARY.synthetic_loss_allowed.definition}
            value={formatSyntheticCurrency(baseline.synthetic_loss_allowed)}
            mono
          />
          <Footnote>Measured before the agents start.</Footnote>
        </Card>

        <Card eyebrow="Test sets" title="Holdouts">
          <ul className="space-y-3">
            {HOLDOUTS.map((h) => (
              <li key={h.id} className="border-l-2 border-atlas-border pl-3">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-semibold text-atlas-text">
                    {h.display_name}
                    <TermNote>{h.term}</TermNote>
                  </span>
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
  term?: string;
  title?: string;
}

function DefinitionRow({ label, value, mono, term, title }: DefinitionRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-xs" title={title}>
      <span className="text-atlas-muted">
        {label}
        {term ? <TermNote>{term}</TermNote> : null}
      </span>
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
