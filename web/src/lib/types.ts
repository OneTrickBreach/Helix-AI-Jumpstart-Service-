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
