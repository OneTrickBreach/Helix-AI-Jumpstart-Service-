/**
 * Display formatting for the dataset view.
 *
 * Iteration 4, Phase 2. Small functions, but they are where a credible page turns
 * sloppy: "1 suppliers", "0.8360000000001", or a bare 44928 with no separator all
 * undermine numbers that are actually correct. Every one of these is unit-tested,
 * including the zero and singular cases that only show up on an edge-case dataset.
 *
 * Formatting only — nothing here computes a value. Numbers arrive already derived
 * from the API.
 */

/** `44928` -> `44,928`. Nullish renders as an em dash, never as "null" or "NaN". */
export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US");
}

/** `1284.7` -> `1,285 units`; respects singular. */
export function units(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Number(value.toFixed(digits));
  const label = Math.abs(rounded) === 1 ? "unit" : "units";
  return `${rounded.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${label}`;
}

/** `0.8366` -> `83.7%`. */
export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** `1.15` -> `$1.15`; small unit costs keep more precision than headline money. */
export function money(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** `9.44` -> `9.4 days`; `1` -> `1 day`. */
export function days(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Number(value.toFixed(digits));
  return `${rounded} ${Math.abs(rounded) === 1 ? "day" : "days"}`;
}

/**
 * `pluralize(1, "supplier")` -> `1 supplier`; `pluralize(5, "supplier")` -> `5 suppliers`.
 * Irregular plurals are passed explicitly: `pluralize(2, "factory", "factories")`.
 */
export function pluralize(
  value: number | null | undefined,
  singular: string,
  pluralForm?: string,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return `— ${pluralForm ?? `${singular}s`}`;
  const word = Math.abs(value) === 1 ? singular : (pluralForm ?? `${singular}s`);
  return `${value.toLocaleString("en-US")} ${word}`;
}

/** `18` and `27` -> `weeks 18–27`; a single period -> `week 18`. */
export function periodRange(
  from: number | null | undefined,
  to: number | null | undefined,
  unit = "week",
): string {
  if (from === null || from === undefined) return "—";
  if (to === null || to === undefined || to === from) return `${unit} ${from}`;
  return `${unit}s ${from}–${to}`;
}

/** `3` -> `3x`; `0` -> `0x` (a real zero-supply shock, not missing data). */
export function multiplier(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Number(value.toFixed(2));
  return `${rounded}x`;
}

/** `distribution_center` -> `Distribution center`. Schema names never reach the screen raw. */
export function humanizeKey(key: string): string {
  if (!key) return "";
  const spaced = key.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** `117163` -> `114.4 KB`. Used for the "download this table" affordance. */
export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

/** Renders an API `_showing` block as "showing top 12 of 288" / "showing all 30". */
export function showingLabel(
  showing: { shown: number; total: number; truncated: boolean } | null | undefined,
): string {
  if (!showing) return "";
  return showing.truncated
    ? `showing top ${count(showing.shown)} of ${count(showing.total)}`
    : `showing all ${count(showing.total)}`;
}
