import { describe, expect, it } from "vitest";

import {
  WHAT_IF_CHIP,
  answerChips,
  changeDirection,
  changeLabel,
  chipForAnswerSource,
  chipForSource,
  timingLabel,
  whatIfChips,
  whatIfHeadline,
  whatIfMetricRows,
} from "./chatDisplay";
import type { ChatAnswer, WhatIfResult } from "./types";

/** Minimal shapes: these tests are about display rules, not payload completeness. */
function answer(overrides: Partial<ChatAnswer>): ChatAnswer {
  return {
    scenario: "component-shortage-shock",
    question: "q",
    route: "grounded",
    reason: "grounded_qa",
    answer: "a",
    answer_source: "llm_grounded",
    citations: [],
    facts_used: [],
    grounding: { ok: true, numbers_checked: 0, numbers_ungrounded: 0, ungrounded_tokens: [] },
    notes: [],
    injection_flags: [],
    beta: true,
    label: "BETA",
    numeric_values_source: "files on disk",
    what_if_capable: true,
    what_if: null,
    ...overrides,
  };
}

function citation(source: string) {
  return { citation_id: "F1", fact_id: "x", source, label: "l", text_excerpt: "t" };
}

// The real numbers from a captured DC-001 outage on component-shortage-shock.
function whatIf(overrides: Partial<WhatIfResult> = {}): WhatIfResult {
  return {
    is_what_if: true,
    scenario: "component-shortage-shock",
    perturbation: {
      kind: "node_outage",
      scenario: "component-shortage-shock",
      from_period: 1,
      to_period: 52,
      node_id: "DC-001",
      seed: 12345,
    },
    reading: "DC-001 unable to ship or receive from period 1 to period 52",
    fingerprint: "fp",
    seed: 12345,
    horizon: 8,
    ppo_included: false,
    base: {
      winner: "classical",
      ppo_outcome: "not_evaluated",
      objective: 95445.445064,
      total_cost: 82915.472858,
      fill_rate: 0.8247,
      days_of_inventory: 2.919964,
      cvar_75: 19649.685288,
      by_approach: {},
    },
    what_if: {
      winner: "classical",
      ppo_outcome: "not_evaluated",
      objective: 95755.003011,
      total_cost: 83225.030805,
      fill_rate: 0.8247,
      days_of_inventory: 2.919964,
      cvar_75: 19720.369201,
      by_approach: {},
    },
    deltas: {
      objective: { before: 95445.445064, after: 95755.003011, absolute: 309.557947, percent: 0.003243 },
      total_cost: { before: 82915.472858, after: 83225.030805, absolute: 309.557947, percent: 0.003733 },
      fill_rate: { before: 0.8247, after: 0.8247, absolute: 0, percent: 0 },
      days_of_inventory: { before: 2.919964, after: 2.919964, absolute: 0, percent: 0 },
      cvar_75: { before: 19649.685288, after: 19720.369201, absolute: 70.683913, percent: 0.003597 },
    },
    impact: {
      reaches_optimizer: true,
      why: "covers period 52",
      lanes_affected: ["LANE-0011"],
      lanes_affected_count: 10,
      lane_types_affected: { dc_to_customer: 8, plant_to_dc: 2 },
      series_affected: 0,
      series_by_demand_type: {},
      demand_rows_affected: 0,
      capacity_read_period: 52,
      removes_all_capacity_for: [],
      estimated_seconds: 1.3,
    },
    diff: {
      table: "lane_periods",
      column: "effective_capacity_units",
      capacity_multiplier_applied: 0,
      rows_changed: 520,
      rows_in_window: 520,
      units_before: 102024,
      units_after: 0,
    },
    moved_the_plan: true,
    explanation: "e",
    warnings: [],
    timing: { total_seconds: 1.389 },
    cached: false,
    beta: true,
    label: "BETA",
    numeric_values_source: "src.pipeline.bench.run_head_to_head on a perturbed in-memory copy",
    period_semantics: "applied exactly as asked",
    ...overrides,
  };
}

describe("provenance chips", () => {
  it("maps each fact source prefix to its own chip", () => {
    expect(chipForSource("dataset_overview.lanes")?.label).toBe("from dataset");
    expect(chipForSource("benchmark.comparison")?.label).toBe("from optimizer run");
    expect(chipForSource("corpus.component-shortage-playbook")?.label).toBe("from planner documents");
    expect(chipForSource("glossary.days_of_inventory")?.label).toBe("glossary definition");
  });

  it("drops a source it does not recognise rather than inventing a label", () => {
    expect(chipForSource("something_new.section")).toBeNull();
    expect(chipForSource("")).toBeNull();
  });

  it("distinguishes model wording from deterministic wording", () => {
    expect(chipForAnswerSource("llm_grounded")?.key).toBe("llm");
    expect(chipForAnswerSource("template_after_ungrounded_number")?.key).toBe("template");
    expect(chipForAnswerSource("template_llm_disabled")?.key).toBe("template");
    expect(chipForAnswerSource("deterministic_refusal")?.key).toBe("deterministic");
    // A glossary answer is human-written text, not model output.
    expect(chipForAnswerSource("glossary_verbatim")?.key).toBe("deterministic");
  });

  it("deduplicates repeated sources and always says who wrote the words", () => {
    const chips = answerChips(
      answer({
        citations: [
          citation("dataset_overview.network"),
          citation("dataset_overview.lanes"),
          citation("benchmark.comparison"),
        ],
      }),
    );
    expect(chips.map((chip) => chip.key)).toEqual(["dataset", "optimizer", "llm"]);
  });

  it("marks a refusal as declined and never as an LLM explanation", () => {
    const chips = answerChips(
      answer({ route: "declined", reason: "business_forecast", answer_source: "deterministic_refusal" }),
    );
    expect(chips.map((chip) => chip.key)).toEqual(["refusal", "deterministic"]);
  });

  it("leads a what-if with the WHAT-IF chip, so a screenshot cannot pass as a benchmark", () => {
    const chips = whatIfChips(whatIf());
    expect(chips[0]).toEqual(WHAT_IF_CHIP);
    expect(chips[0].label).toContain("WHAT-IF");
    expect(chips.some((chip) => chip.key === "optimizer")).toBe(true);
  });
});

describe("what-if change labels", () => {
  it("states money changes with both the absolute and the relative move", () => {
    expect(changeLabel({ before: 100, after: 110, absolute: 10, percent: 0.1 }, "money")).toBe(
      "+$10.00 (+10.00%)",
    );
    expect(changeLabel({ before: 100, after: 90, absolute: -10, percent: -0.1 }, "money")).toBe(
      "−$10.00 (−10.00%)",
    );
  });

  it("reports a rate in percentage points, which is unambiguous", () => {
    expect(changeLabel({ before: 0.8247, after: 0.801685, absolute: -0.023015, percent: -0.027907 }, "rate")).toBe(
      "−2.30 pts",
    );
  });

  it("says 'no change' for an exact zero rather than '+$0.00'", () => {
    expect(changeLabel({ before: 5, after: 5, absolute: 0, percent: 0 }, "money")).toBe("no change");
  });

  it("renders a missing delta as an em dash, never NaN", () => {
    expect(changeLabel(undefined, "money")).toBe("—");
    expect(changeLabel({ before: null, after: null, absolute: null, percent: null }, "money")).toBe("—");
  });

  it("knows which direction is worse for each metric", () => {
    const up = { before: 1, after: 2, absolute: 1, percent: 1 };
    const down = { before: 2, after: 1, absolute: -1, percent: -0.5 };
    expect(changeDirection(up, true)).toBe("worse"); // cost up is worse
    expect(changeDirection(down, true)).toBe("better");
    expect(changeDirection(up, false)).toBe("better"); // fill rate up is better
    expect(changeDirection(down, false)).toBe("worse");
    expect(changeDirection({ before: 1, after: 1, absolute: 0, percent: 0 }, true)).toBe("none");
  });
});

describe("what-if metric rows", () => {
  it("renders before, after and change for every metric including tail risk", () => {
    const rows = whatIfMetricRows(whatIf());
    expect(rows.map((row) => row.key)).toEqual([
      "objective",
      "total_cost",
      "cvar_75",
      "fill_rate",
      "days_of_inventory",
    ]);
    const objective = rows[0];
    expect(objective.before).toBe("$95,445.45");
    expect(objective.after).toBe("$95,755.00");
    expect(objective.change).toBe("+$309.56 (+0.32%)");
    expect(objective.direction).toBe("worse");
    // CVaR-75 must be shown on BOTH sides: a mean-only answer to "what if my
    // warehouse dies" is a bad answer.
    const cvar = rows[2];
    expect(cvar.before).toBe("$19,649.69");
    expect(cvar.after).toBe("$19,720.37");
    const unchanged = rows.find((row) => row.key === "fill_rate");
    expect(unchanged?.change).toBe("no change");
    expect(unchanged?.direction).toBe("none");
  });
});

describe("what-if headline", () => {
  it("leads with the mechanism when the perturbation cannot reach the optimizer", () => {
    const result = whatIf({
      moved_the_plan: false,
      impact: { ...whatIf().impact, reaches_optimizer: false, why: "periods 3-6 do not include period 52" },
    });
    expect(whatIfHeadline(result)).toBe("No change — and not because the network absorbed it");
  });

  it("distinguishes 'absorbed it' from 'never reached it'", () => {
    expect(whatIfHeadline(whatIf({ moved_the_plan: false }))).toContain("absorbed it");
  });

  it("names the direction when the plan moved", () => {
    expect(whatIfHeadline(whatIf())).toBe("The plan changed: objective worse by +$309.56 (+0.32%)");
  });
});

describe("timing", () => {
  it("reports a real run in seconds", () => {
    expect(timingLabel(whatIf())).toBe("1.39s on this device");
  });

  it("never presents a cache read as optimizer latency", () => {
    const cached = whatIf({
      cached: true,
      timing: { total_seconds: 0.0, originally_measured_total_seconds: 1.298 },
    });
    expect(timingLabel(cached)).toBe("served from cache in 0.00s, originally measured 1.30s");
  });
});
