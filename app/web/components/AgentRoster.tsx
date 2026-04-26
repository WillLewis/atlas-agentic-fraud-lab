// app/web/components/AgentRoster.tsx
// Step 1 content — agent assignment cards.
//
// All agent metadata lives in the SIMULATION_AGENTS / DETERMINISTIC_JUDGE
// constants below as structured TS data, not free strings inside JSX. This
// is the CLAUDE.md / Bible §22 invariant for UI copy: the safety scanner
// reads structured data, so descriptions and allowed-action lists must be
// inspectable without parsing JSX.
//
// Agent purposes are paraphrased from Bible §13 in public-safe terms. No
// "not allowed" list is rendered — the cards stay positive ("here is what
// each agent can do") to avoid surfacing operational fraud language at all.
//
// Abstract iconography only: geometric SVG glyphs per group (triangle for
// red-team, rounded rectangle for bank-defense, hexagon for the
// deterministic judge). No human silhouettes, no faces, no person glyphs —
// Bible §8 / arch doc §1.2 failure mode "uses human images".

import type { JSX } from "react";

import { getDemoConfig } from "../lib/demoConfig";
import type { ModelTier } from "../lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AgentGroup = "red_team" | "bank_defense" | "judge";

// Tier widens beyond the runtime ModelTier ("frontier" | "compact") because
// the deterministic judge is code, not an LLM, and renders a "Deterministic"
// pill instead of a model-tier badge.
type AgentTier = ModelTier | "deterministic";

interface AgentRosterEntry {
  id: string;
  group: AgentGroup;
  display_name: string;
  purpose: string;
  allowed: readonly string[];
  tier: AgentTier;
}

interface GroupMeta {
  title: string;
  description: string;
  badge_classes: string;
  glyph_classes: string;
}

// ---------------------------------------------------------------------------
// Roster — paraphrased from PROJECT_ATLAS_BIBLE.md §13
// ---------------------------------------------------------------------------

const RED_TEAM_AGENTS: readonly AgentRosterEntry[] = [
  {
    id: "fraud_scenario_agent",
    group: "red_team",
    display_name: "Fraud Scenario Agent",
    purpose: "Proposes abstract synthetic model-vulnerability hypotheses.",
    allowed: [
      "Choose a configured vulnerability family",
      "Propose scoring-query allocation across search methods",
      "Explain model-risk intuition in safe terms"
    ],
    tier: "frontier"
  },
  {
    id: "evolutionary_search_agent",
    group: "red_team",
    display_name: "Evolutionary Search Agent",
    purpose:
      "Optimizes synthetic event histories to surface under-ranked high-risk examples.",
    allowed: [
      "Mutate event timing, counts, and synthetic graph links",
      "Call the local mock scorer",
      "Return candidate batches under the scoring-query limit"
    ],
    tier: "frontier"
  },
  {
    id: "graph_probe_agent",
    group: "red_team",
    display_name: "Graph Probe Agent",
    purpose: "Explores safe synthetic relationship-risk vulnerabilities.",
    allowed: [
      "Analyze the synthetic recipient/device/account graph",
      "Propose graph features",
      "Identify cohorts with high graph risk and low model score"
    ],
    tier: "frontier"
  },
  {
    id: "model_vulnerability_analyst_agent",
    group: "red_team",
    display_name: "Model Vulnerability Analyst Agent",
    purpose: "Packages discovered misses into model vulnerability cards.",
    allowed: [
      "Summarize accepted high-risk synthetic candidates",
      "Generate safe cohort definitions",
      "Recommend defensive fix families"
    ],
    tier: "frontier"
  }
] as const;

const BANK_DEFENSE_AGENTS: readonly AgentRosterEntry[] = [
  {
    id: "bank_strategy_agent",
    group: "bank_defense",
    display_name: "Bank Strategy Agent",
    purpose:
      "Triages model vulnerability cards and selects a defensive fix approach.",
    allowed: [
      "Read incoming model vulnerability cards",
      "Select a fix type within the configured allow-list",
      "Coordinate handoff to the Governance Agent"
    ],
    tier: "frontier"
  },
  {
    id: "feature_fix_agent",
    group: "bank_defense",
    display_name: "Feature Fix Agent",
    purpose:
      "Proposes defensive features derived from synthetic event histories or graph relationships.",
    allowed: [
      "Derive features from synthetic event histories",
      "Derive features from synthetic graph relationships",
      "Submit a feature fix candidate"
    ],
    tier: "frontier"
  },
  {
    id: "decision_threshold_fix_agent",
    group: "bank_defense",
    display_name: "Decision-Threshold Fix Agent",
    purpose:
      "Proposes synthetic decision-threshold changes while preserving action-rate limits.",
    allowed: [
      "Propose decision-threshold adjustments",
      "Respect challenge / alert / decline action-rate limits",
      "Submit a policy fix candidate"
    ],
    tier: "frontier"
  },
  {
    id: "model_calibration_fix_agent",
    group: "bank_defense",
    display_name: "Model Calibration Fix Agent",
    purpose:
      "Retrains or recalibrates the mock scorer using allowed synthetic training data.",
    allowed: [
      "Retrain the mock scorer on allowed synthetic data",
      "Recalibrate the score distribution",
      "Submit a model calibration fix candidate"
    ],
    tier: "frontier"
  },
  {
    id: "governance_agent",
    group: "bank_defense",
    display_name: "Governance Agent",
    purpose:
      "Blocks unsafe, overfit, action-rate-limit-violating, or non-generalizing defensive fixes.",
    allowed: [
      "Reject fixes that exceed customer-friction tolerances",
      "Reject fixes that fail the locked adaptive holdout",
      "Summarize accept/reject rationale using judge output"
    ],
    tier: "frontier"
  }
] as const;

const DETERMINISTIC_JUDGE: AgentRosterEntry = {
  id: "evaluation_judge",
  group: "judge",
  display_name: "Evaluation Judge",
  purpose:
    "Deterministic code that owns metrics, holdout evaluation, and defensive fix acceptance.",
  allowed: [
    "Compute model miss rate, recall, and friction metrics",
    "Evaluate clean, found, locked, and drifted holdouts",
    "Accept or reject defensive fixes; enforce action-rate limits"
  ],
  tier: "deterministic"
} as const;

// ---------------------------------------------------------------------------
// Group metadata — color tokens and abstract glyph styling
// ---------------------------------------------------------------------------

const GROUP_META: Record<AgentGroup, GroupMeta> = {
  red_team: {
    title: "Red-Team Simulation Agents",
    description:
      "Run constrained synthetic searches against the local mock scorer. Cannot access locked holdouts or generate operational fraud guidance.",
    badge_classes: "border-atlas-danger/40 bg-atlas-danger/10 text-atlas-danger",
    glyph_classes: "text-atlas-danger"
  },
  bank_defense: {
    title: "Bank-Defense Simulation Agents",
    description:
      "Propose feature, decision-threshold, or calibration defensive fixes. Cannot accept their own fixes — every proposal goes to the deterministic judge.",
    badge_classes: "border-atlas-accent/40 bg-atlas-accent/10 text-atlas-accent",
    glyph_classes: "text-atlas-accent"
  },
  judge: {
    title: "Deterministic Control",
    description:
      "Code, not an LLM. Owns measurement, holdout enforcement, and the only authority to accept or reject a defensive fix.",
    badge_classes: "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok",
    glyph_classes: "text-atlas-ok"
  }
};

// ---------------------------------------------------------------------------
// Step 1 narrative copy — Bible §8 main message
// ---------------------------------------------------------------------------

const STEP_HEADING = "Agents Assigned";
const STEP_SUBHEADING = "Step 1";
const STEP_MAIN_MESSAGE =
  "The agents receive objectives, tools, scoring-query limits, action-rate limits, and safety constraints. No agent can access real customer data or production systems.";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentRoster() {
  const config = getDemoConfig();
  const tierLabels: Record<AgentTier, string> = {
    frontier: config.model_tier_labels.frontier,
    compact: config.model_tier_labels.compact,
    deterministic: "Deterministic"
  };

  return (
    <section
      id="agents-assigned"
      aria-labelledby="agents-assigned-heading"
      className="scroll-mt-16 px-8 py-16"
    >
      <header className="mb-10 max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-widest text-atlas-muted">
          {STEP_SUBHEADING}
        </p>
        <h2
          id="agents-assigned-heading"
          className="mt-2 text-3xl font-semibold tracking-tight text-atlas-text"
        >
          {STEP_HEADING}
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-atlas-muted">{STEP_MAIN_MESSAGE}</p>
      </header>

      <div className="flex flex-col gap-10">
        <AgentGroupSection
          group="red_team"
          agents={RED_TEAM_AGENTS}
          tierLabels={tierLabels}
        />
        <AgentGroupSection
          group="bank_defense"
          agents={BANK_DEFENSE_AGENTS}
          tierLabels={tierLabels}
        />
        <AgentGroupSection
          group="judge"
          agents={[DETERMINISTIC_JUDGE]}
          tierLabels={tierLabels}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface AgentGroupSectionProps {
  group: AgentGroup;
  agents: readonly AgentRosterEntry[];
  tierLabels: Record<AgentTier, string>;
}

function AgentGroupSection({ group, agents, tierLabels }: AgentGroupSectionProps) {
  const meta = GROUP_META[group];
  return (
    <div>
      <div className="mb-4 flex items-baseline gap-3">
        <h3 className="text-base font-semibold uppercase tracking-wide text-atlas-text">
          {meta.title}
        </h3>
        <span className="font-mono text-[11px] text-atlas-muted">
          {agents.length} {agents.length === 1 ? "agent" : "agents"}
        </span>
      </div>
      <p className="mb-4 max-w-3xl text-sm text-atlas-muted">{meta.description}</p>
      <ul
        role="list"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        {agents.map((agent) => (
          <li key={agent.id}>
            <AgentCard agent={agent} tierLabels={tierLabels} />
          </li>
        ))}
      </ul>
    </div>
  );
}

interface AgentCardProps {
  agent: AgentRosterEntry;
  tierLabels: Record<AgentTier, string>;
}

function AgentCard({ agent, tierLabels }: AgentCardProps) {
  const meta = GROUP_META[agent.group];
  const tierLabel = tierLabels[agent.tier];
  const tierIsDeterministic = agent.tier === "deterministic";

  return (
    <article className="flex h-full flex-col rounded-lg border border-atlas-border bg-atlas-panel/60 p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <GroupGlyph group={agent.group} className={`h-7 w-7 ${meta.glyph_classes}`} />
        <span
          className={[
            "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider",
            tierIsDeterministic
              ? "border-atlas-ok/40 bg-atlas-ok/10 text-atlas-ok"
              : meta.badge_classes
          ].join(" ")}
        >
          {tierLabel}
        </span>
      </div>
      <h4 className="text-sm font-semibold leading-snug text-atlas-text">
        {agent.display_name}
      </h4>
      <p className="mt-1.5 text-xs leading-relaxed text-atlas-muted">{agent.purpose}</p>
      <div className="mt-3 border-t border-atlas-border/60 pt-3">
        <p className="font-mono text-[10px] uppercase tracking-widest text-atlas-muted">
          Allowed
        </p>
        <ul className="mt-1.5 space-y-1 text-xs text-atlas-text/80">
          {agent.allowed.map((line, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden="true" className="text-atlas-muted">
                ▸
              </span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Abstract group glyphs — pure SVG, no person/face shapes.
// ---------------------------------------------------------------------------

interface GroupGlyphProps {
  group: AgentGroup;
  className?: string;
}

function GroupGlyph({ group, className }: GroupGlyphProps): JSX.Element {
  // Triangle (red-team), rounded rectangle (bank-defense), hexagon (judge).
  // Stroke-only so they read as outlines on the dark background.
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className
  };
  switch (group) {
    case "red_team":
      return (
        <svg {...props}>
          <path d="M12 4 L20 19 L4 19 Z" />
          <circle cx="12" cy="14" r="1.2" fill="currentColor" />
        </svg>
      );
    case "bank_defense":
      return (
        <svg {...props}>
          <rect x="4.5" y="4.5" width="15" height="15" rx="3" />
          <path d="M9 12 L11.5 14.5 L15 10" />
        </svg>
      );
    case "judge":
      return (
        <svg {...props}>
          <path d="M12 3 L20 7.5 L20 16.5 L12 21 L4 16.5 L4 7.5 Z" />
          <path d="M9 12 L11 14 L15 10" />
        </svg>
      );
  }
}
