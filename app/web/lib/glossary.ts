// app/web/lib/glossary.ts
// Plain-language display layer for Project Atlas.
//
// Dual-label convention: `plain` is the headline shown first, `term` is the
// canonical technical term kept visible as a muted subtitle (satisfies the
// project terminology standard), `definition` is the tooltip text.
//
// This file is intentionally data-only so the safety scanner can inspect it.
// It contains NO banned legacy terms.

export interface GlossaryEntry {
  plain: string;
  term: string;
  definition: string;
}

export const GLOSSARY = {
  // --- core metrics ---
  model_miss_rate: {
    plain: "Missed risky activity",
    term: "model miss rate",
    definition:
      "Of all genuinely risky synthetic events, the share the model wrongly accepted. Lower is better."
  },
  recall: {
    plain: "Risky activity caught",
    term: "recall at fixed action-rate",
    definition:
      "Share of risky events the model correctly flags, holding customer-friction limits fixed. Higher is better."
  },
  false_positive_rate: {
    plain: "Good customers wrongly flagged",
    term: "false-positive rate",
    definition:
      "Share of normal synthetic activity that got challenged, alerted, or declined. Lower is better."
  },
  synthetic_loss_allowed: {
    plain: "Synthetic losses let through",
    term: "synthetic loss allowed",
    definition:
      "Scaled play-money value of risky events the model accepted. Shown as SYN $, reduced 10:1 for display — not real currency."
  },
  synthetic_loss_prevented: {
    plain: "Synthetic losses prevented by the fix",
    term: "synthetic loss prevented",
    definition:
      "Scaled play-money the fix would have stopped versus the baseline. SYN $, illustrative only."
  },
  miss_rate_lift_vs_random: {
    plain: "Better than random guessing",
    term: "miss-rate lift vs random",
    definition:
      "How much more effective the agents' targeted search was than picking events at random."
  },

  // --- customer-friction ---
  challenge_rate: {
    plain: "Step-up checks",
    term: "challenge rate",
    definition: "How often a customer is asked for an extra verification step."
  },
  alert_rate: {
    plain: "Sent to review",
    term: "alert rate",
    definition: "How often an event is routed to a human review queue."
  },
  decline_rate: {
    plain: "Blocked outright",
    term: "decline rate",
    definition: "How often a transaction is declined. Measured in basis points."
  },
  review_rate: {
    plain: "Manual review",
    term: "review rate",
    definition: "How often an event is queued for manual review."
  },
  friction_rates: {
    plain: "How often we interrupt customers",
    term: "customer-friction rates",
    definition: "Step-up checks, reviews, and blocks. All series stay under their configured limits."
  },
  action_rate_limits: {
    plain: "Customer-friction limits",
    term: "action-rate limits",
    definition: "Caps on how often the bank may interrupt customers — a fix can't exceed them."
  },

  // --- decision thresholds ---
  decline_threshold: {
    plain: "Block above",
    term: "decline score threshold",
    definition: "Risk score at or above which an event is declined."
  },
  alert_threshold: {
    plain: "Review above",
    term: "alert score threshold",
    definition: "Risk score at or above which an event is sent to review."
  },
  challenge_threshold: {
    plain: "Verify above",
    term: "challenge score threshold",
    definition: "Risk score at or above which a customer is asked to verify."
  },

  // --- holdouts ---
  holdout_generalization: {
    plain: "Does the fix actually hold up?",
    term: "holdout generalization",
    definition:
      "Whether the fix works on data the agents never saw — not just the cases they found."
  },
  clean_holdout: {
    plain: "Fresh customers (never tested)",
    term: "clean holdout",
    definition: "Customers set aside before any testing. Does the fix help on unseen people?"
  },
  found_adaptive_set: {
    plain: "Cases we already found",
    term: "found adaptive set",
    definition:
      "The risky cases the agents surfaced this round. Shows what the fix improves on known examples."
  },
  locked_adaptive_holdout: {
    plain: "Hidden stress test",
    term: "locked adaptive holdout",
    definition:
      "Look-alike cases the agents never see — catches a fix that just memorized the found examples."
  },
  drifted_holdout: {
    plain: "Future-drift test",
    term: "drifted holdout",
    definition: "A shifted version of the data. Does the fix still hold as conditions change?"
  },

  // --- cards / judge ---
  model_vulnerabilities: {
    plain: "Model weak spots found",
    term: "model vulnerabilities",
    definition: "Where the stress-test agents got risky activity past the model."
  },
  defensive_fix_candidates: {
    plain: "Proposed fixes",
    term: "defensive fix options",
    definition: "What the defense agents propose to close the weak spot."
  },
  judge_decision: {
    plain: "Referee's call · decided by code",
    term: "judge decision · deterministic",
    definition:
      "Agents only propose. Plain code measures the result and accepts or rejects the fix."
  },
  judge_metrics: {
    plain: "Scores measured by the referee",
    term: "judge-derived metrics",
    definition: "Numbers computed by code — agents can't edit or overwrite them."
  },
  judge_notes: {
    plain: "Why the referee decided this",
    term: "judge notes",
    definition: "The condition-by-condition record behind the accept/reject call."
  },
  safe_cohort_definition: {
    plain: "Who this affects (safe summary)",
    term: "safe cohort definition",
    definition: "An abstract, feature-level description of the affected group — no individuals."
  },
  baseline_state: {
    plain: "Starting model — before any testing",
    term: "baseline metrics · pre-round 1",
    definition: "Where the model stands before the agents go to work."
  }
} as const satisfies Record<string, GlossaryEntry>;

// Plain display names for the 7 vulnerability families (family_id is kept as
// the technical subtitle wherever these are shown).
export const VULN_FAMILY_LABELS: Record<string, string> = {
  low_velocity_high_graph_risk: "Quiet account, risky connections",
  recent_change_feature_delay: "Recent security change under-weighted",
  score_boundary_cluster: "Clustered just below the line",
  activity_channel_shift: "Unusual channel-mix shift",
  current_device_mismatch: "Device doesn't match recent use",
  label_noise_mislearned: "Noisy-label confusion",
  overfit_fix_failure: "Fix that memorizes known cases"
};

// Short plain labels for fix types (raw fix_type kept as the technical subtitle).
export const FIX_TYPE_PLAIN: Record<string, string> = {
  feature_fix: "Add a new signal",
  policy_fix: "Adjust the decision thresholds",
  model_calibration_fix: "Retrain the model"
};
