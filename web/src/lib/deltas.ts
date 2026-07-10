import type { Benchmark, CostBreakdown, PlanMetrics } from "./types";

export type MetricKey =
  | "total_cost"
  | "holding"
  | "ordering"
  | "transport"
  | "backorder"
  | "lost_sale"
  | "fill_rate"
  | "days_of_inventory";

export type DeltaTone = "good" | "bad" | "neutral";

export type MetricComparison = {
  key: MetricKey;
  label: string;
  before: number;
  after: number;
  displayBefore: string;
  displayAfter: string;
  deltaLabel: string;
  arrow: "up" | "down" | "flat";
  tone: DeltaTone;
};

const COST_KEYS: MetricKey[] = [
  "total_cost",
  "holding",
  "ordering",
  "transport",
  "backorder",
  "lost_sale",
];

const COST_LABELS: Record<MetricKey, string> = {
  total_cost: "Total cost",
  holding: "Holding",
  ordering: "Ordering",
  transport: "Transport",
  backorder: "Backorder",
  lost_sale: "Lost sale",
  fill_rate: "Fill rate",
  days_of_inventory: "Days inventory",
};

export function computeDelta(metric: MetricKey, before: number, after: number): Pick<MetricComparison, "deltaLabel" | "arrow" | "tone"> {
  const rawChange = after - before;
  const arrow = rawChange > 0 ? "up" : rawChange < 0 ? "down" : "flat";

  if (metric === "fill_rate") {
    const points = rawChange * 100;
    return {
      deltaLabel: `${points >= 0 ? "+" : ""}${points.toFixed(2)} pts`,
      arrow,
      tone: points > 0 ? "good" : points < 0 ? "bad" : "neutral",
    };
  }

  if (before === 0) {
    return {
      deltaLabel: "n/a",
      arrow,
      tone: "neutral",
    };
  }

  const relative = rawChange / before;
  const lowerIsBetter = COST_KEYS.includes(metric) || metric === "days_of_inventory";
  const isGood = lowerIsBetter ? relative < 0 : relative > 0;
  return {
    deltaLabel: `${relative >= 0 ? "+" : ""}${(relative * 100).toFixed(2)}%`,
    arrow,
    tone: relative === 0 ? "neutral" : isGood ? "good" : "bad",
  };
}

export function winnerMessage(benchmark: Benchmark): string {
  const winner = benchmark.winner.approach;
  if (winner === "baseline") {
    return "Baseline already best; no improvement found by evidence.";
  }
  return `${winner} wins by benchmark evidence.`;
}

export function buildMetricComparisons(benchmark: Benchmark): MetricComparison[] {
  const winner = benchmark.winner.approach;
  const baseline = benchmark.plans.baseline.metrics;
  const after = benchmark.plans[winner]?.metrics ?? baseline;
  const baselineCosts = baseline.cost_breakdown ?? {};
  const afterCosts = after.cost_breakdown ?? {};

  return [
    metricRow("total_cost", baseline.total_cost, after.total_cost),
    metricRow("holding", costValue(baselineCosts, "holding"), costValue(afterCosts, "holding")),
    metricRow("ordering", costValue(baselineCosts, "ordering"), costValue(afterCosts, "ordering")),
    metricRow("transport", costValue(baselineCosts, "transport"), costValue(afterCosts, "transport")),
    metricRow("backorder", costValue(baselineCosts, "backorder"), costValue(afterCosts, "backorder")),
    metricRow("lost_sale", costValue(baselineCosts, "lost_sale"), costValue(afterCosts, "lost_sale")),
    metricRow("fill_rate", baseline.fill_rate, after.fill_rate),
    metricRow("days_of_inventory", baseline.days_of_inventory, after.days_of_inventory),
  ];
}

function metricRow(key: MetricKey, before: number, after: number): MetricComparison {
  return {
    key,
    label: COST_LABELS[key],
    before,
    after,
    displayBefore: formatMetric(key, before),
    displayAfter: formatMetric(key, after),
    ...computeDelta(key, before, after),
  };
}

function costValue(costs: CostBreakdown, key: keyof CostBreakdown): number {
  return Number(costs[key] ?? 0);
}

export function formatMetric(key: MetricKey, value: number): string {
  if (key === "fill_rate") {
    return `${(value * 100).toFixed(2)}%`;
  }
  if (COST_KEYS.includes(key)) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(value);
  }
  return value.toLocaleString("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

export function selectedMetrics(benchmark: Benchmark): { before: PlanMetrics; after: PlanMetrics } {
  const before = benchmark.plans.baseline.metrics;
  const after = benchmark.plans[benchmark.winner.approach]?.metrics ?? before;
  return { before, after };
}

