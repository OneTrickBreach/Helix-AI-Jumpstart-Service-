/**
 * Display logic for the conversational analyst (Iteration 5, BETA).
 *
 * Two jobs, both pure and both unit-tested:
 *
 * 1. **Provenance chips.** Every message says where its content came from — the
 *    dataset, the recorded optimizer run, the planner documents, the glossary — and
 *    how the words were produced (a language model, or a deterministic template).
 *    A viewer should never have to guess which of those they are reading.
 * 2. **What-if metric rows.** Before, after, and the change, with the direction
 *    named in words as well as colour.
 *
 * Nothing here computes a supply-chain number: every value arrives from the API,
 * which got it from a file on disk or from `run_head_to_head`. The only arithmetic
 * is turning the API's own `absolute` delta into percentage points for a rate.
 */

import { days, money, percent } from "./datasetFormat";
import type { ChatAnswer, MetricDelta, WhatIfResult } from "./types";

export type ChipTone =
  | "dataset"
  | "optimizer"
  | "documents"
  | "glossary"
  | "llm"
  | "deterministic"
  | "whatif"
  | "refusal";

export type ProvenanceChip = {
  key: string;
  label: string;
  tone: ChipTone;
  /** Hover/`title` text: the honest long form of the chip. */
  title: string;
};

const DATA_CHIPS: Record<string, ProvenanceChip> = {
  dataset_overview: {
    key: "dataset",
    label: "from dataset",
    tone: "dataset",
    title: "Read from the generated scenario files on this device at request time.",
  },
  benchmark: {
    key: "optimizer",
    label: "from optimizer run",
    tone: "optimizer",
    title: "From the recorded on-device optimizer benchmark (run_head_to_head), not from the language model.",
  },
  corpus: {
    key: "documents",
    label: "from planner documents",
    tone: "documents",
    title: "Quoted from the on-device document corpus (supplier agreements, SOPs, playbooks). Prose, not a measurement.",
  },
  glossary: {
    key: "glossary",
    label: "glossary definition",
    tone: "glossary",
    title: "A fixed, human-written definition. No model involved.",
  },
};

const TEXT_CHIPS: Record<string, ProvenanceChip> = {
  llm: {
    key: "llm",
    label: "explained by LLM",
    tone: "llm",
    title:
      "The wording came from the on-device language model, which may only restate the facts above. Every number in it was checked against those facts before it was shown.",
  },
  template: {
    key: "template",
    label: "deterministic template",
    tone: "deterministic",
    title: "Fixed template text built from the retrieved facts. The model was not used, or its answer was rejected.",
  },
  deterministic: {
    key: "deterministic",
    label: "deterministic · no LLM",
    tone: "deterministic",
    title: "Written by rules from the dataset itself. The model was never called.",
  },
};

export const WHAT_IF_CHIP: ProvenanceChip = {
  key: "whatif",
  label: "WHAT-IF (synthetic perturbation)",
  tone: "whatif",
  title:
    "A real optimizer run on a synthetic perturbation of seeded demo data. This is NOT the recorded benchmark result and must not be quoted as one.",
};

const REFUSAL_CHIP: ProvenanceChip = {
  key: "refusal",
  label: "declined",
  tone: "refusal",
  title: "Out of scope. The system refuses rather than approximating an answer.",
};

/** `dataset_overview.lanes` -> the `from dataset` chip. Unknown prefixes are dropped. */
export function chipForSource(source: string): ProvenanceChip | null {
  const prefix = (source ?? "").split(".")[0];
  return DATA_CHIPS[prefix] ?? null;
}

/**
 * How the words were produced. Derived from `answer_source` rather than guessed:
 * `llm_grounded` is the only value where a model wrote what is on screen.
 */
export function chipForAnswerSource(answerSource: string): ProvenanceChip | null {
  if (answerSource === "llm_grounded") return TEXT_CHIPS.llm;
  if (answerSource.startsWith("template")) return TEXT_CHIPS.template;
  if (answerSource.startsWith("deterministic")) return TEXT_CHIPS.deterministic;
  if (answerSource === "glossary_verbatim") return TEXT_CHIPS.deterministic;
  return null;
}

/** The chips for one answer: where the content came from, then how it was written. */
export function answerChips(answer: ChatAnswer): ProvenanceChip[] {
  const chips: ProvenanceChip[] = [];
  const seen = new Set<string>();
  for (const citation of answer.citations ?? []) {
    const chip = chipForSource(citation.source);
    if (chip && !seen.has(chip.key)) {
      seen.add(chip.key);
      chips.push(chip);
    }
  }
  if (answer.route === "declined" && !seen.has(REFUSAL_CHIP.key)) {
    chips.push(REFUSAL_CHIP);
    seen.add(REFUSAL_CHIP.key);
  }
  const textChip = chipForAnswerSource(answer.answer_source ?? "");
  if (textChip && !seen.has(textChip.key)) {
    chips.push(textChip);
    seen.add(textChip.key);
  }
  return chips;
}

/**
 * The chips for a what-if result.
 *
 * The WHAT-IF chip is first and unconditional: `is_what_if` is true on every
 * payload this renders, and the whole point of the chip is that a screenshot of
 * this card cannot be mistaken for a benchmark result.
 */
export function whatIfChips(result: WhatIfResult): ProvenanceChip[] {
  const chips: ProvenanceChip[] = [WHAT_IF_CHIP];
  chips.push({
    key: "optimizer",
    label: "real optimizer run",
    tone: "optimizer",
    title: `Both sides computed by run_head_to_head on this device, seed ${result.seed}, horizon ${result.horizon}.`,
  });
  chips.push({
    key: "deterministic",
    label: "deterministic · no LLM",
    tone: "deterministic",
    title: "The perturbation was read by rules and the numbers came from the optimizer. No model wrote any of this.",
  });
  return chips;
}

// ---------------------------------------------------------------------------
// what-if metric rows
// ---------------------------------------------------------------------------

export type WhatIfMetricRow = {
  key: string;
  label: string;
  before: string;
  after: string;
  change: string;
  /** "worse" / "better" / "none" — the direction, named rather than only coloured. */
  direction: "worse" | "better" | "none";
};

type MetricSpec = {
  key: string;
  label: string;
  format: "money" | "rate" | "days";
  lowerIsBetter: boolean;
};

export const WHAT_IF_METRICS: MetricSpec[] = [
  { key: "objective", label: "Objective", format: "money", lowerIsBetter: true },
  { key: "total_cost", label: "Total cost", format: "money", lowerIsBetter: true },
  { key: "cvar_75", label: "Tail risk (CVaR-75)", format: "money", lowerIsBetter: true },
  { key: "fill_rate", label: "Fill rate", format: "rate", lowerIsBetter: false },
  { key: "days_of_inventory", label: "Days of inventory", format: "days", lowerIsBetter: true },
];

function formatValue(value: number | null, format: MetricSpec["format"]): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (format === "money") return money(value, 2);
  if (format === "rate") return percent(value, 2);
  return days(value, 2);
}

/**
 * The change, in words.
 *
 * A rate is reported in percentage points, because "fill rate fell 2.79%" reads as
 * 2.79 points to some viewers and 2.79% *of* the rate to others. Points are
 * unambiguous, and the absolute delta the API already computed is what they are.
 */
export function changeLabel(delta: MetricDelta | undefined, format: MetricSpec["format"]): string {
  if (!delta || delta.absolute === null || delta.absolute === undefined) return "—";
  if (delta.absolute === 0) return "no change";
  const sign = delta.absolute > 0 ? "+" : "−";
  const magnitude = Math.abs(delta.absolute);
  if (format === "rate") {
    return `${sign}${(magnitude * 100).toFixed(2)} pts`;
  }
  const relative =
    delta.percent === null || delta.percent === undefined
      ? ""
      : ` (${sign}${(Math.abs(delta.percent) * 100).toFixed(2)}%)`;
  if (format === "days") {
    return `${sign}${magnitude.toFixed(2)} days${relative}`;
  }
  return `${sign}${money(magnitude, 2)}${relative}`;
}

export function changeDirection(
  delta: MetricDelta | undefined,
  lowerIsBetter: boolean,
): WhatIfMetricRow["direction"] {
  if (!delta || delta.absolute === null || delta.absolute === undefined || delta.absolute === 0) {
    return "none";
  }
  const wentUp = delta.absolute > 0;
  return wentUp === lowerIsBetter ? "worse" : "better";
}

export function whatIfMetricRows(result: WhatIfResult): WhatIfMetricRow[] {
  return WHAT_IF_METRICS.map((spec) => {
    const delta = result.deltas?.[spec.key];
    return {
      key: spec.key,
      label: spec.label,
      before: formatValue(delta?.before ?? null, spec.format),
      after: formatValue(delta?.after ?? null, spec.format),
      change: changeLabel(delta, spec.format),
      direction: changeDirection(delta, spec.lowerIsBetter),
    };
  });
}

/**
 * The one-line summary above the metric table.
 *
 * When the perturbation could not reach the optimizer at all, that fact leads —
 * a planner must never read "no change" as resilience.
 */
export function whatIfHeadline(result: WhatIfResult): string {
  if (!result.impact?.reaches_optimizer) {
    return "No change — and not because the network absorbed it";
  }
  if (!result.moved_the_plan) {
    return "The optimizer absorbed it: the plan did not change";
  }
  const delta = result.deltas?.objective;
  const direction = (delta?.absolute ?? 0) > 0 ? "worse" : "better";
  return `The plan changed: objective ${direction} by ${changeLabel(delta, "money")}`;
}

/** How long the run took, and whether the figure is a cache read rather than a run. */
export function timingLabel(result: WhatIfResult): string {
  const total = Number(result.timing?.total_seconds ?? 0);
  if (result.cached) {
    const original = result.timing?.originally_measured_total_seconds;
    const measured =
      original === null || original === undefined ? "" : `, originally measured ${Number(original).toFixed(2)}s`;
    return `served from cache in ${total.toFixed(2)}s${measured}`;
  }
  return `${total.toFixed(2)}s on this device`;
}
