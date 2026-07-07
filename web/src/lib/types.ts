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
  peak_memory_mb: number;
  gpu_utilization_percent: number;
};

export type ResourceProfile = {
  wall_clock_seconds?: number;
  peak_unified_memory_mb?: number;
  effective_memory_bandwidth_gbps?: number;
  cpu_utilization_percent?: number;
  gpu_utilization_percent?: number;
  gpu_memory_used_mb?: number | null;
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

