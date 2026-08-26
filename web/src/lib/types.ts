export type Approach = "baseline" | "classical" | "ppo" | string;

export type ScenarioSummary = {
  scenario: string;
  description?: string | null;
  generated: boolean;
  config_path?: string | null;
  generated_path?: string | null;
  horizon_periods?: number | null;
  criticality_tier?: string | null;
};

// --- Iteration 6a: custom scenarios ------------------------------------------

/** One editable scenario setting, with the reach it earned from the ledger. */
export type SettingSpec = {
  key: string;
  group: string;
  kind: "int" | "float" | "str" | "range2";
  label: string;
  reach: string;
  reach_label: string;
  /** False for the settings that cannot move the optimizer's answer at all. */
  reaches_optimizer: boolean;
  writes: string[];
  minimum?: number;
  maximum?: number;
  choices?: string[];
  note?: string;
  /**
   * Iteration 6b §1.2, network tier only. Orthogonal to `reach`: both classes DO
   * move the objective, but only one of them may be compared to the recorded
   * baseline. Absent on every scenario-tier setting.
   */
  answer_class?: string;
  answer_class_label?: string;
  /** False when changing this resizes the problem, so the objective is a different quantity. */
  comparable_to_baseline?: boolean;
};

/** One idea a planner would say out loud, over one or more raw settings. */
export type SimpleControlSpec = {
  name: string;
  label: string;
  kind: "value" | "scale" | "group";
  writes: string[];
  minimum?: number;
  maximum?: number;
  fields?: string[];
  help?: string;
};

export type CustomSettingsPayload = {
  base_scenario: string;
  default_seed: number;
  name_rules: {
    prefix: string;
    pattern: string;
    max_length: number;
    reserved: string[];
    note: string;
  };
  groups: string[];
  settings: SettingSpec[];
  simple_controls: SimpleControlSpec[];
  reach_labels: Record<string, string>;
  ledger: Record<string, number>;
  /** Decision 15: shown in Advanced under an explicit heading, never in Simple. */
  cannot_change_the_answer: { heading: string; settings: string[]; count: number };
  /**
   * Iteration 6b: the network tier. Was `excluded_from_6a` when changing the
   * network was refused outright. The two honesty classes arrive here rather than
   * being hard-coded in the form, so a class can never be rendered for a setting
   * that has stopped belonging to it.
   */
  network_tier: {
    group: string;
    keys: string[];
    reason: string;
    answer_class_labels: Record<string, string>;
    classes: Record<string, string[]>;
    not_comparable_note: string;
    not_comparable_keys: string[];
  };
};

export type Refusal = { code: string; field?: string | null; message: string };
export type ValidationWarning = Refusal & { detail?: Record<string, unknown> };

export type ValidationPayload = {
  ok: boolean;
  refusals: Refusal[];
  warnings: ValidationWarning[];
};

export type ConfigChange = {
  group: string;
  parameter: string;
  baseline_value: unknown;
  scenario_value: unknown;
  /** Present when the changed setting cannot move the optimizer's answer. */
  reach?: string;
  reach_label?: string;
  reaches_optimizer?: boolean;
};

export type CapacityReachability = {
  applicable: boolean;
  reaches_optimizer: boolean;
  capacity_read_period: number;
  window?: [number, number] | null;
  suggested_duration_periods?: number | null;
  why: string;
};

export type EstimateComponent = { stage: string; seconds: number; basis: string };

export type RunEstimate = {
  total_seconds: number;
  components: EstimateComponent[];
  excluded: string[];
  note: string;
};

export type CustomPreview = {
  scenario: string;
  slug: string;
  is_custom: true;
  base_scenario: string;
  seed: number;
  validation: ValidationPayload;
  resolved_config: Record<string, unknown>;
  resolved_overrides: Record<string, unknown>;
  config_changes: ConfigChange[];
  config_changes_count: number;
  capacity_reachability: CapacityReachability;
  run_estimate: RunEstimate;
  ledger: Record<string, number>;
  label: string;
};

export type SavedScenario = {
  scenario: string;
  slug: string;
  is_custom: boolean;
  description?: string | null;
  seed?: number | null;
  horizon_periods?: number | null;
  generated: boolean;
  config_exists: boolean;
  saved_at?: number | null;
  has_recorded_run: boolean;
  label: string;
  created?: boolean;
};

export type RunCard = {
  scenario: string;
  is_custom: boolean;
  generated: boolean;
  reading: string;
  will_run: string[];
  excluded: { stage: string; why: string }[];
  fixed_inputs: {
    seed?: number | null;
    horizon: number;
    history_periods?: number | null;
    finished_good_series: number;
  };
  estimate: RunEstimate;
  capacity_reachability: CapacityReachability;
  warnings: (ValidationWarning & { do_not_read_as?: string })[];
  writes_artifact: string;
  label: string;
};

export type CostBreakdown = {
  holding?: number;
  ordering?: number;
  backorder?: number;
  lost_sale?: number;
  transport?: number;
};

export type PlanMetrics = {
  total_cost: number;
  objective: number;
  fill_rate: number;
  days_of_inventory: number;
  cost_breakdown?: CostBreakdown;
};

export type Plan = {
  metrics: PlanMetrics;
  policy?: Record<string, unknown>;
  plan?: Array<Record<string, unknown>>;
  cost_breakdown?: CostBreakdown;
  lane_assignments?: Array<Record<string, unknown>>;
};

export type ComparisonRow = {
  approach: Approach;
  total_cost: number;
  objective: number;
  fill_rate: number;
  days_of_inventory: number;
  latency_seconds: number;
  peak_process_rss_mb: number;
  allocation_rate_gbps_proxy: number;
  gpu_utilization_percent: number | null;
};

export type ResourceProfile = {
  wall_clock_seconds?: number;
  peak_process_rss_mb?: number;
  allocation_rate_gbps_proxy?: number;
  cpu_utilization_percent?: number;
  gpu_utilization_percent?: number;
  gpu_memory_used_mb?: number | null;
  gpu_metrics_status?: string;
};

export type Benchmark = {
  scenario: string;
  comparison: ComparisonRow[];
  winner: ComparisonRow;
  objective_tie_across_approaches: boolean;
  plans: Record<string, Plan>;
  resource_profiles: Record<string, ResourceProfile>;
  ppo_outcome: string;
  artifacts?: Record<string, unknown>;
};

export type Citation = {
  citation_id?: string;
  source_id?: string;
  source_type?: string;
  title?: string;
  text_excerpt?: string;
  score?: number;
  prompt_injection_flagged?: boolean;
};

export type PromptInjectionFlag = {
  source_id?: string;
  source_type?: string;
  title?: string;
  pattern?: string;
  matched_excerpt?: string;
  action?: string;
};

export type Rationale = {
  advisory: boolean;
  label: string;
  scenario: string;
  selected_approach: string;
  advisory_rationale: string;
  citations: Citation[];
  prompt_injection_flags: PromptInjectionFlag[];
  retrieval?: Record<string, unknown>;
  llm_profile?: Record<string, unknown>;
};

export type ScenarioComparison = {
  benchmark: Benchmark;
  rationale: Rationale;
  /** Iteration 6a: what actually ran. Additive — absent on a recorded replay. */
  run_settings?: {
    include_ppo: boolean;
    include_rationale: boolean;
    is_custom: boolean;
    horizon: number;
    excluded: string[];
  };
  capacity_reachability?: CapacityReachability | null;
  /**
   * Iteration 6b guardrail 4. Whether this run's objective may be compared to the
   * recorded baseline at all — false whenever a problem-size network count differs,
   * because total demand differs and the objective measures a different quantity.
   */
  network_comparability?: {
    comparable_to_baseline: boolean;
    /** True when ANY of the eight network counts differs from baseline — i.e. this
     *  is a custom *dataset*, not merely custom conditions. */
    network_edited?: boolean;
    edited_settings?: {
      key: string;
      label: string;
      baseline_value: number;
      scenario_value: number;
    }[];
    resized_settings: {
      key: string;
      label: string;
      baseline_value: number;
      scenario_value: number;
    }[];
    why: string;
    note: string;
  } | null;
  warnings?: (ValidationWarning & { do_not_read_as?: string })[];
};

export type ApiResponse<T> = {
  scenario?: string | null;
  status: "ok";
  data: T;
};

// ---------------------------------------------------------------------------
// Dataset transparency layer (Iteration 4)
// ---------------------------------------------------------------------------

/** Every truncated list in the payload carries one of these. */
export type Showing = {
  shown: number;
  total: number;
  truncated: boolean;
  ranked_by: string;
  note: string;
};

export type DatasetProvenance = {
  scenario: string;
  is_synthetic: boolean;
  badge_text: string;
  requested_seed: number | null;
  effective_seed: number | null;
  generator: string | null;
  generator_version: number | null;
  generated_at_utc: string | null;
  generated_at_source: string;
  synthetic_data_notice: string | null;
  data_location: string;
  regeneration_command: string;
  byte_identical_claim: string;
  source_files: { table: string; file: string; rows: number }[];
};

export type GlanceTile = {
  key: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  plain_english_note: string;
};

export type DatasetNarrative = {
  one_sentence_summary: string;
  scenario_sentence: string;
  forecast_method_sentence: string;
  pipeline_sentence: string;
  provenance_sentence: string;
};

export type NetworkTier = { tier: string; plain_label: string; count: number };

export type DatasetNetwork = {
  node_count: number;
  nodes_by_type: Record<string, number>;
  nodes_by_region: Record<string, number>;
  tiers: NetworkTier[];
  node_list: {
    node_id: string;
    node_type: string;
    plain_label: string;
    name: string;
    region: string;
    capacity_units_per_period: number;
    storage_capacity_units: number;
  }[];
  node_list_showing: Showing;
  edges: {
    lane_id: string;
    from: string;
    to: string;
    lane_type: string;
    sku_scope: string;
    lead_time_days: number;
    cost_per_unit: number;
    capacity_units_per_period: number;
  }[];
  edges_showing: Showing;
};

export type DatasetProducts = {
  sku_count: number;
  sku_count_by_type: Record<string, number>;
  sku_type_labels: Record<string, string>;
  bom_row_count: number;
  bom_parent_count: number;
  bom_max_tier_depth: number;
  bom_tree: {
    parent_sku_id: string;
    children: { sku_id: string; quantity_per_parent: number; tier_depth: number }[];
  }[];
  bom_tree_showing: Showing;
  top_by_demand_share: {
    sku_id: string;
    units: number;
    share_of_finished_good_demand: number;
  }[];
  top_by_demand_share_showing: Showing;
};

export type DatasetDemand = {
  total_rows: number;
  rows_by_type: Record<string, number>;
  history_periods: number;
  period_unit: string;
  days_per_period: number | null;
  series_count: number;
  total_units_finished_goods: number;
  units_per_period: { period: number; units: number }[];
  units_per_period_showing: Showing;
  lumpy_series_count: number;
  lumpy_zero_fraction_threshold: number;
  max_zero_fraction: number;
  forecast_method_split: { croston_sba: number; auto_ets: number };
  forecast_method_note: string;
  top_series: {
    node_id: string;
    sku_id: string;
    is_lumpy: boolean;
    forecast_method: string;
    units_by_period: number[];
  }[];
  top_series_showing: Showing;
  shock_window: {
    from_period: number;
    to_period: number;
    multipliers: number[];
    affected_rows: number;
    affected_sku_count: number;
  } | null;
};

export type LaneRow = {
  lane_id: string;
  from: string;
  to: string;
  lane_type: string;
  plain_label: string;
  sku_scope: string;
  lead_time_days: number;
  lead_time_std_days: number;
  cost_per_unit: number;
  capacity_units_per_period: number;
  distance_km: number;
  co2_kg_per_unit: number;
};

export type DisruptionEntry = {
  lane_id: string;
  from: string;
  to: string;
  lane_type: string;
  sku_scope: string;
  disruption_code: string;
  from_period: number;
  to_period: number;
  periods_affected: number;
  min_capacity_multiplier: number;
  max_lead_time_multiplier: number;
};

export type DatasetLanes = {
  lane_count: number;
  count_by_type: Record<string, number>;
  lane_type_labels: Record<string, string>;
  lane_period_row_count: number;
  periods_covered: number;
  lead_time_days_range: { min: number; max: number };
  cost_per_unit_range: { min: number; max: number };
  table: LaneRow[];
  table_showing: Showing;
  disruption_timeline: DisruptionEntry[];
  disrupted_lane_count: number;
};

export type DatasetCapacity = {
  production_line_count: number;
  lines_by_plant: Record<string, number>;
  total_throughput_units_per_period: number;
  lines: {
    line_id: string;
    plant_id: string;
    sku_id: string;
    max_throughput_units_per_period: number;
  }[];
  lines_showing: Showing;
  storage_by_node_type: {
    node_type: string;
    plain_label: string;
    storage_capacity_units: number;
    throughput_units_per_period: number;
  }[];
};

export type DatasetCosts = {
  label: string;
  by_sku_type: {
    sku_type: string;
    plain_label: string;
    parameters: {
      parameter: string;
      plain_label: string;
      min: number;
      max: number;
    }[];
  }[];
  transport: {
    cost_per_unit_min: number;
    cost_per_unit_max: number;
    cost_per_km_min: number;
    cost_per_km_max: number;
  };
};

export type DatasetServiceTargets = {
  row_count: number;
  customer_count: number;
  sku_count: number;
  criticality_tiers: Record<string, number>;
  fill_rate_target_range: { min: number; max: number };
  days_inventory_target_range: { min: number; max: number };
};

export type DatasetInitialInventory = {
  row_count: number;
  total_on_hand_units: number;
  total_in_transit_units: number;
  total_backlog_units: number;
  on_hand_by_node_type: {
    node_type: string;
    plain_label: string;
    on_hand_units: number;
  }[];
  held_at_node_types: string[];
  held_sku_types: string[];
  periods_of_cover_estimate: number | null;
  days_of_cover_estimate: number | null;
  basis: string;
};

export type ScenarioChange = {
  kind: string;
  what: string;
  where: Record<string, unknown>;
  when: { from_period?: number; to_period?: number; periods_affected?: number };
  magnitude: Record<string, unknown>;
  evidence: string;
  plain_english: string;
};

export type DatasetScenarioDiff = {
  vs: string;
  is_baseline: boolean;
  comparable: boolean;
  comparison_note: string | null;
  description: string | null;
  changes: ScenarioChange[];
  config_changes: {
    group: string;
    parameter: string;
    baseline_value: unknown;
    scenario_value: unknown;
  }[];
  config_changes_showing: Showing;
};

export type DatasetPipelineLink = {
  stage_inputs: Record<string, string[]>;
  /** Human wording for each table name, supplied by the API so the UI never invents one. */
  table_labels: Record<string, string>;
  note: string;
};

export type DatasetOverview = {
  provenance: DatasetProvenance;
  at_a_glance: GlanceTile[];
  narrative: DatasetNarrative;
  network: DatasetNetwork;
  products: DatasetProducts;
  demand: DatasetDemand;
  lanes: DatasetLanes;
  capacity: DatasetCapacity;
  costs: DatasetCosts;
  service_targets: DatasetServiceTargets;
  initial_inventory: DatasetInitialInventory;
  scenario_diff: DatasetScenarioDiff;
  pipeline_link: DatasetPipelineLink;
};

// ---------------------------------------------------------------------------
// Conversational analyst — "Ask the plan" (Iteration 5, BETA)
// ---------------------------------------------------------------------------
// These mirror the payloads of POST /chat/ask, POST /chat/whatif and
// GET /chat/whatif/stream exactly. Nothing here is computed in the browser: the
// panel renders what the API says, including the fields that keep a what-if from
// being mistaken for a benchmark result (`is_what_if`, `label`, `warnings`,
// `impact.reaches_optimizer`, `numeric_values_source`).

export type ChatRoute = "grounded" | "glossary" | "declined" | "entity_not_found" | "what_if";

export type ChatCitation = {
  citation_id: string;
  fact_id: string;
  source: string;
  label: string;
  text_excerpt: string;
};

export type ChatGrounding = {
  ok: boolean;
  numbers_checked: number;
  numbers_ungrounded: number;
  ungrounded_tokens: string[];
  authorization_rules?: Record<string, number>;
  note?: string;
};

export type PerturbationKind = "node_outage" | "lane_disruption" | "demand_multiplier";

export type Perturbation = {
  kind: PerturbationKind;
  scenario: string;
  from_period: number;
  to_period: number;
  node_id?: string;
  lane_id?: string;
  capacity_multiplier?: number;
  demand_multiplier?: number;
  scope?: string;
  scope_id?: string;
  seed: number;
};

export type WhatIfImpact = {
  reaches_optimizer: boolean;
  why: string;
  lanes_affected: string[];
  lanes_affected_count: number;
  lane_types_affected: Record<string, number>;
  series_affected: number;
  series_by_demand_type: Record<string, number>;
  demand_rows_affected: number;
  capacity_read_period: number | null;
  removes_all_capacity_for: string[];
  estimated_seconds: number;
};

/** The card a planner confirms before any compute is spent (decision 6). */
export type ConfirmationCard = {
  reading: string;
  perturbation: Perturbation;
  impact: WhatIfImpact;
  fingerprint: string;
  estimated_seconds: number;
  estimate_basis: string;
  warnings: string[];
  requires_confirmation: boolean;
  runnable: boolean;
  how_to_run: string;
  ppo_included: boolean;
  beta: boolean;
};

export type UnresolvedEntity = {
  reference: string;
  node_type: string | null;
  ordinal?: number | null;
  existing_ids: string[];
};

export type ParseResult = {
  outcome: "parsed" | "clarify" | "refused" | "not_found";
  scenario: string;
  question: string;
  parser: string;
  reason: string;
  message: string;
  perturbation: Perturbation | null;
  impact: WhatIfImpact | null;
  confirmation: ConfirmationCard | null;
  missing: string[];
  options: string[];
  unresolved: UnresolvedEntity[];
  injection_flags: Record<string, unknown>[];
  beta: boolean;
  label: string;
  /** Always false: a parse never executes anything. */
  executable: boolean;
};

export type ChatAnswer = {
  scenario: string;
  question: string;
  route: ChatRoute;
  reason: string;
  answer: string;
  answer_source: string;
  citations: ChatCitation[];
  facts_used: { fact_id: string; source: string; kind: string; score: number; matched: string[] }[];
  grounding: ChatGrounding;
  llm_profile?: Record<string, unknown> | null;
  notes: string[];
  injection_flags: Record<string, unknown>[];
  beta: boolean;
  label: string;
  numeric_values_source: string;
  what_if_capable: boolean;
  what_if: {
    available: boolean;
    requires_confirmation: boolean;
    how_to_run: string;
    parse: ParseResult;
  } | null;
};

export type MetricDelta = {
  before: number | null;
  after: number | null;
  absolute: number | null;
  percent: number | null;
};

export type WhatIfMetrics = {
  winner: string;
  ppo_outcome: string;
  objective: number;
  total_cost: number;
  fill_rate: number;
  days_of_inventory: number;
  cvar_75: number;
  by_approach: Record<
    string,
    {
      objective: number;
      total_cost: number;
      fill_rate: number;
      days_of_inventory: number;
      cvar_75: number;
      latency_seconds: number;
    }
  >;
  cost_breakdown?: CostBreakdown;
  policy?: Record<string, number>;
};

export type WhatIfDiff = {
  table: string;
  column: string;
  capacity_multiplier_applied?: number;
  demand_multiplier_applied?: number;
  lane_ids?: string[];
  scope?: string;
  scope_id?: string | null;
  rows_changed: number;
  rows_in_window: number;
  units_before: number;
  units_after: number;
};

export type WhatIfResult = {
  executed?: boolean;
  /** True on every what-if payload. The UI must never render one as a benchmark. */
  is_what_if: boolean;
  scenario: string;
  perturbation: Perturbation;
  reading: string;
  fingerprint: string;
  seed: number;
  horizon: number;
  ppo_included: boolean;
  base: WhatIfMetrics;
  what_if: WhatIfMetrics;
  deltas: Record<string, MetricDelta>;
  impact: WhatIfImpact;
  diff: WhatIfDiff;
  moved_the_plan: boolean;
  explanation: string;
  warnings: string[];
  timing: Record<string, number | boolean | null>;
  cached: boolean;
  beta: boolean;
  label: string;
  numeric_values_source: string;
  period_semantics: string;
};

/**
 * A real captured Q&A transcript, replayed when `?replay=true` and the backend is
 * unavailable. Real payloads from this device — not mock data — stored in the same
 * shape the live calls return, so replay and live render through identical code.
 */
export type RecordedTranscript = {
  scenario: string;
  captured_at_utc: string;
  captured_from: string;
  note: string;
  entries: (
    | { kind: "ask"; question: string; answer: ChatAnswer }
    | {
        kind: "whatif";
        question: string;
        /** The `/chat/ask` answer for the same question, so replay shows what live shows. */
        answer: ChatAnswer;
        confirmation: ConfirmationCard;
        result: WhatIfResult;
      }
  )[];
};
