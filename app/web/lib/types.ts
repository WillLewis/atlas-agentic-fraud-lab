// app/web/lib/types.ts
// TypeScript types for Project Atlas web shell.
//
// Field names mirror project_atlas_sample_data.json exactly so that the same
// shapes can be reused once Pydantic models in app/api/schemas/ are wired up
// in Phase 4 and onward. Do not rename fields to camelCase — keep snake_case.

// ---------------------------------------------------------------------------
// Shared enums and unions
// ---------------------------------------------------------------------------

export type DemoMode = "public" | "internal";

export type DecisionAction = "accept" | "challenge" | "alert" | "decline";

export type FixType = "feature_fix" | "policy_fix" | "model_calibration_fix";

export type SyntheticTruthLabel =
  | "normal_activity"
  | "high_risk_synthetic_activity";

export type ChallengeResult = "not_required" | "passed" | "failed";

export type ModelTier = "frontier" | "compact";

// ---------------------------------------------------------------------------
// Project envelope
// ---------------------------------------------------------------------------

export interface FixtureProject {
  project_name: string;
  project_folder: string;
  demo_mode: DemoMode;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Entities
// ---------------------------------------------------------------------------

export interface Customer {
  customer_id: string;
  customer_segment: string;
  home_region_bucket: string;
  account_age_days: number;
  normal_login_frequency_30d: number;
  normal_transfer_frequency_30d: number;
  synthetic_base_risk: number;
  created_from_seed: number;
}

export interface Account {
  account_id: string;
  customer_id: string;
  account_type: string;
  opened_days_ago: number;
  available_balance_bucket: string;
  account_status: string;
}

export interface Device {
  device_id: string;
  customer_id: string;
  device_channel: string;
  first_seen_days_ago: number;
  login_count_30d: number;
  is_current_event_device: boolean;
}

export interface Recipient {
  recipient_id: string;
  first_seen_days_ago: number;
  recipient_reuse_degree: number;
  recipient_risk_bucket: string;
}

export interface ExternalAccount {
  external_account_id: string;
  customer_id: string;
  linked_days_ago: number;
  verification_method: string;
  external_account_risk_bucket: string;
}

export interface GraphEdge {
  edge_id: string;
  source_node_id: string;
  source_node_type: string;
  target_node_id: string;
  target_node_type: string;
  relationship_type: string;
  first_seen_days_ago: number;
  event_count: number;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export interface LoginSession {
  session_id: string;
  customer_id: string;
  device_id: string;
  event_time_utc: string;
  channel: string;
  region_bucket: string;
  challenge_required: boolean;
  challenge_result: ChallengeResult;
}

export interface SecurityEvent {
  security_event_id: string;
  customer_id: string;
  session_id: string;
  event_type: string;
  event_time_utc: string;
  device_id: string;
  safe_risk_marker: string;
}

export interface TransferEvent {
  transfer_event_id: string;
  customer_id: string;
  account_id: string;
  event_type: string;
  event_time_utc: string;
  amount_bucket: string;
  recipient_id: string;
  channel: string;
  synthetic_truth_label: SyntheticTruthLabel;
}

// ---------------------------------------------------------------------------
// Features and labels
// ---------------------------------------------------------------------------

export interface FeatureVector {
  event_id: string;
  customer_id: string;
  login_count_72h: number;
  login_count_30d: number;
  login_velocity_ratio: number;
  challenge_count_72h: number;
  challenge_pass_ratio_30d: number;
  password_recovery_count_72h: number;
  device_count_72h: number;
  current_device_tenure_days: number;
  geo_consistency_flag: number;
  transfer_count_72h: number;
  recipient_tenure_days: number;
  shared_device_degree: number;
  shared_recipient_degree: number;
  entity_graph_risk_score: number;
  cash_movement_velocity_score: number;
}

export interface LatentDrivers {
  base_customer_risk: number;
  account_access_change_marker: number;
  device_novelty_marker: number;
  security_recovery_marker: number;
  cash_movement_velocity_marker: number;
  entity_reuse_marker: number;
  ring_membership_marker: number;
  label_noise: number;
}

export interface LabelGenerationRecord {
  event_id: string;
  latent_drivers: LatentDrivers;
  synthetic_risk_probability: number;
  synthetic_truth_label: SyntheticTruthLabel;
}

// ---------------------------------------------------------------------------
// Model vulnerability families and cards
// ---------------------------------------------------------------------------

export interface ModelVulnerabilityFamily {
  family_id: string;
  public_name: string;
  safe_description: string;
  expected_detector: string;
  recommended_defensive_fix_type: FixType;
}

export interface SafeCohortDefinition {
  [feature_name: string]: string;
}

export interface ModelVulnerabilityCard {
  model_vulnerability_id: string;
  round_id: number;
  family_id: string;
  summary: string;
  valid_high_risk_events_tested: number;
  accepted_high_risk_events: number;
  model_miss_rate: number;
  miss_rate_lift_vs_random: number;
  estimated_synthetic_loss_allowed: number;
  affected_decision_action: DecisionAction;
  safe_cohort_definition: SafeCohortDefinition;
  recommended_defensive_fix_types: FixType[];
}

// ---------------------------------------------------------------------------
// Defensive fix candidates
// ---------------------------------------------------------------------------

export interface RateLimitClaim {
  max_false_positive_rate_increase: number;
  max_challenge_rate_increase: number;
}

export interface DefensiveFixCandidate {
  defensive_fix_id: string;
  round_id: number;
  fix_type: FixType;
  description: string;
  files_changed: string[];
  expected_benefit: string;
  rate_limit_claim: RateLimitClaim;
  requires_judge_evaluation: boolean;
}

// ---------------------------------------------------------------------------
// Judge reports
// ---------------------------------------------------------------------------

export interface JudgeMetricSet {
  recall_at_fixed_action_rate: number;
  false_positive_rate_at_fixed_action_rate: number;
  model_miss_rate: number;
  synthetic_loss_allowed: number;
}

export interface HoldoutGeneralization {
  clean_holdout_pass: boolean;
  // Phase 9 reconciliation: judge runtime emits this when found-adaptive
  // event ids were supplied to the judge; OpenAPI JudgeReport already
  // exposes it. Optional on the web side so legacy fixture data without
  // the field still type-checks.
  found_adaptive_set_pass?: boolean;
  locked_adaptive_holdout_pass: boolean;
  drifted_holdout_pass: boolean;
}

export interface JudgeReport {
  judge_report_id: string;
  round_id: number;
  defensive_fix_id: string;
  accepted_by_judge: boolean;
  baseline: JudgeMetricSet;
  fixed: JudgeMetricSet;
  holdout_generalization: HoldoutGeneralization;
  judge_notes: string;
}

// ---------------------------------------------------------------------------
// Ledger
// ---------------------------------------------------------------------------

export interface LedgerRecord {
  run_id: string;
  round_id: number;
  seed: number;
  demo_mode: DemoMode;
  model_version_before: string;
  decision_threshold_version_before: string;
  model_version_after: string;
  decision_threshold_version_after: string;
  agent_roster_version: string;
  safety_scan_passed: boolean;
  judge_report_path: string;
  model_vulnerability_card_path: string;
}

// ---------------------------------------------------------------------------
// Derived metric snapshot for the web shell
//
// Phase 1 placeholder shape: a per-round summary the charts and timeline can
// consume. In Phase 9 the same shape will be hydrated from real judge output
// served by the FastAPI replay endpoint, so keep field names aligned with the
// JudgeMetricSet keys (model_miss_rate, recall_at_fixed_action_rate, etc.).
// ---------------------------------------------------------------------------

export type SnapshotKind = "baseline" | "fixed" | "interpolated";

export interface MetricSnapshot {
  round_id: number;
  round_label: string;
  kind: SnapshotKind;
  model_miss_rate: number;
  recall_at_fixed_action_rate: number;
  false_positive_rate_at_fixed_action_rate: number;
  synthetic_loss_allowed: number;
  // Friction proxies derived from the judge's fixed-action-rate context.
  // Phase 1 sources these from the single fixture judge report; Phase 9 will
  // populate them from real action-rate snapshots.
  challenge_rate: number;
  alert_rate: number;
  decline_rate: number;
}

// ---------------------------------------------------------------------------
// Top-level fixture envelope
// ---------------------------------------------------------------------------

export interface AtlasSampleData {
  project: FixtureProject;
  entities: {
    customers: Customer[];
    accounts: Account[];
    devices: Device[];
    recipients: Recipient[];
    external_accounts: ExternalAccount[];
    graph_edges: GraphEdge[];
  };
  events: {
    login_sessions: LoginSession[];
    security_events: SecurityEvent[];
    transfer_events: TransferEvent[];
  };
  features: FeatureVector[];
  label_generation: LabelGenerationRecord[];
  model_vulnerability_families: ModelVulnerabilityFamily[];
  model_vulnerability_cards: ModelVulnerabilityCard[];
  defensive_fix_candidates: DefensiveFixCandidate[];
  judge_reports: JudgeReport[];
  ledger_records: LedgerRecord[];
}
