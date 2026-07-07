import { describe, expect, it } from "vitest";

import { buildMetricComparisons, computeDelta, winnerMessage } from "./deltas";
import type { Benchmark } from "./types";

const benchmark: Benchmark = {
  scenario: "baseline",
  comparison: [],
  winner: {
    approach: "classical",
    total_cost: 80,
    objective: 80,
    fill_rate: 0.93,
    days_of_inventory: 16,
    latency_seconds: 0.2,
    peak_memory_mb: 110,
    gpu_utilization_percent: 0,
  },
  objective_tie_across_approaches: false,
  plans: {
    baseline: {
      metrics: {
        total_cost: 100,
        objective: 100,
        fill_rate: 0.9,
        days_of_inventory: 20,
        cost_breakdown: {
          holding: 20,
          ordering: 10,
          transport: 8,
          backorder: 4,
          lost_sale: 2,
        },
      },
    },
    classical: {
      metrics: {
        total_cost: 80,
        objective: 80,
        fill_rate: 0.93,
        days_of_inventory: 16,
        cost_breakdown: {
          holding: 18,
          ordering: 11,
          transport: 6,
          backorder: 2,
          lost_sale: 1,
        },
      },
    },
  },
  resource_profiles: {},
  ppo_outcome: "lost_to_classical",
};

describe("delta integrity utility", () => {
  it("marks cost reductions as good relative deltas", () => {
    expect(computeDelta("total_cost", 100, 80)).toEqual({
      deltaLabel: "-20.00%",
      arrow: "down",
      tone: "good",
    });
  });

  it("marks cost increases as bad", () => {
    expect(computeDelta("ordering", 10, 11)).toEqual({
      deltaLabel: "+10.00%",
      arrow: "up",
      tone: "bad",
    });
  });

  it("formats fill-rate deltas as signed percentage points", () => {
    expect(computeDelta("fill_rate", 0.9, 0.932)).toEqual({
      deltaLabel: "+3.20 pts",
      arrow: "up",
      tone: "good",
    });
  });

  it("treats lower days of inventory as good without changing the formula", () => {
    expect(computeDelta("days_of_inventory", 20, 16)).toEqual({
      deltaLabel: "-20.00%",
      arrow: "down",
      tone: "good",
    });
  });

  it("builds rows from baseline and evidence winner metrics", () => {
    const rows = buildMetricComparisons(benchmark);
    expect(rows.find((row) => row.key === "total_cost")?.deltaLabel).toBe("-20.00%");
    expect(rows.find((row) => row.key === "fill_rate")?.deltaLabel).toBe("+3.00 pts");
    expect(rows.find((row) => row.key === "ordering")?.tone).toBe("bad");
  });

  it("renders the honest no-improvement state when baseline wins", () => {
    const baselineWins = {
      ...benchmark,
      winner: { ...benchmark.winner, approach: "baseline" },
    };
    expect(winnerMessage(baselineWins)).toBe("Baseline already best; no improvement found by evidence.");
  });
});

