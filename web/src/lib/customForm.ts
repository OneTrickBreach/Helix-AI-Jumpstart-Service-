import type {
  ConfigChange,
  CustomSettingsPayload,
  Refusal,
  SettingSpec,
  SimpleControlSpec,
  ValidationPayload,
  ValidationWarning,
} from "./types";

/**
 * Pure logic behind the custom-scenario form.
 *
 * Deliberately holds **no** notion of what a setting means or what it can change:
 * every reach label, range and grouping comes from the ledger the API serves, so
 * the front end cannot drift out of step with the derivation that earned those
 * labels. If a setting stops being inert on the server, this file needs no edit.
 */

/** `"q3 Surge!"` -> `"q3-surge"`. A preview of what the server will store. */
export function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

/** What the saved scenario will actually be called. */
export function scenarioNameFor(name: string, prefix = "custom-"): string {
  const slug = slugify(name);
  return slug ? `${prefix}${slug}` : "";
}

export type SettingGroup = {
  group: string;
  settings: SettingSpec[];
};

/**
 * 🔴 Iteration 6b sequencing gate — REMOVE IN PHASE 3.
 *
 * Phase 1 makes the eight `network:` counts first-class, validated settings in the
 * API. It ships **no UI**. But this layout builds itself from `payload.groups`, so
 * the moment the API serves a `network` group these controls would appear in
 * Advanced as plain numeric inputs — and `AdvancedControl` renders no `note`, so
 * they would arrive with **no honesty label at all**.
 *
 * That breaks 6b guardrail 3 (every network control is labelled with its class)
 * and risks guardrail 4 (a resized problem compared against 81,789.36). A control
 * whose caveat is missing is exactly the kind of no-op-shaped hazard this iteration
 * exists to eliminate, so the group stays out of the form until Phase 3 renders the
 * three label classes properly.
 *
 * The whole tier is gated, including the inert `network.lines_per_plant`: showing
 * one network control under the inert heading while hiding its seven siblings
 * would be more confusing than showing none. The settings remain fully live and
 * validated over the API throughout — this gate is presentational only.
 */
const PENDING_UI_GROUPS = new Set(["network"]);

/**
 * Advanced-tier layout: live settings by group, then the ones that cannot move
 * the answer, collected separately.
 *
 * Decision 15: the inert settings are **shown**, under an explicit heading, not
 * hidden. Hiding them would be dishonest about what the dataset contains; showing
 * them as live controls would be worse.
 */
export function advancedLayout(payload: CustomSettingsPayload): {
  groups: SettingGroup[];
  cannotChange: SettingSpec[];
  heading: string;
} {
  const cannotChange = payload.settings.filter(
    (setting) => !setting.reaches_optimizer && !PENDING_UI_GROUPS.has(setting.group),
  );
  const live = payload.settings.filter(
    (setting) => setting.reaches_optimizer && !PENDING_UI_GROUPS.has(setting.group),
  );
  const groups = payload.groups
    .filter((group) => !PENDING_UI_GROUPS.has(group))
    .map((group) => ({
      group,
      settings: live.filter((setting) => setting.group === group),
    }))
    .filter((entry) => entry.settings.length > 0);
  return {
    groups,
    cannotChange,
    heading: payload.cannot_change_the_answer.heading,
  };
}

/** Read a dotted path out of a resolved config. */
export function valueAt(config: Record<string, unknown>, key: string): unknown {
  let node: unknown = config;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/**
 * The value an Advanced control should display.
 *
 * The resolved config is authoritative — it is what the server would save — so a
 * control reflects a Simple-tier edit without the two tiers needing to agree on
 * how to expand it. That is what keeps Simple and Advanced two views of one form
 * rather than two competing sources of truth.
 */
export function displayValue(
  setting: SettingSpec,
  resolvedConfig: Record<string, unknown>,
): string {
  const value = valueAt(resolvedConfig, setting.key);
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** Coerce a form field back into the type the setting expects. */
export function coerceSetting(setting: SettingSpec, raw: string): unknown {
  if (setting.kind === "str") return raw;
  if (setting.kind === "range2") {
    // An empty segment must not become 0: `Number("")` is 0, so "1.5," would
    // silently resolve to [1.5, 0] and come back as an inverted-range refusal
    // while the planner is still mid-type. Hand it back untouched instead.
    const segments = raw.split(",").map((part) => part.trim());
    const parts = segments.map((part) => (part === "" ? Number.NaN : Number(part)));
    return segments.length === 2 && parts.every((part) => !Number.isNaN(part)) ? parts : raw;
  }
  const numeric = Number(raw);
  if (Number.isNaN(numeric)) return raw;
  return setting.kind === "int" ? Math.round(numeric) : numeric;
}

/**
 * True when an Advanced edit has taken a Simple control's settings out of its reach.
 *
 * A `scale` control multiplies baseline's per-tier values, so once someone types a
 * single tier by hand the multiplier can no longer describe the state. Saying so is
 * better than showing a slider position that is a lie.
 */
export function simpleControlOverridden(
  control: SimpleControlSpec,
  overrides: Record<string, unknown>,
): boolean {
  return control.writes.some((key) => key in overrides);
}

/** Drop every override a Simple control owns, so the control governs again. */
export function releaseSimpleControl(
  control: SimpleControlSpec,
  overrides: Record<string, unknown>,
): Record<string, unknown> {
  const next = { ...overrides };
  for (const key of control.writes) delete next[key];
  return next;
}

// --- validation display ------------------------------------------------------

/** The capacity no-op warning, if it is present. It gets its own amber block. */
export function capacityWarning(
  warnings: ValidationWarning[],
): ValidationWarning | undefined {
  return warnings.find((warning) => warning.code === "capacity_window_misses_read_period");
}

/** Warnings other than the capacity one, which is rendered separately. */
export function otherWarnings(warnings: ValidationWarning[]): ValidationWarning[] {
  return warnings.filter((warning) => warning.code !== "capacity_window_misses_read_period");
}

export type ValidationDisplay = {
  ok: boolean;
  refusals: Refusal[];
  warnings: ValidationWarning[];
  /** The one line to put next to the Save button. */
  summary: string;
  blocking: boolean;
};

/**
 * Turn a validation payload into what the panel shows.
 *
 * The messages are the API's own sentences, never re-worded here: they were
 * written to be actionable by a planner, and a second vocabulary for the same
 * refusal is how a UI ends up disagreeing with its backend.
 */
export function validationDisplay(validation: ValidationPayload | null): ValidationDisplay {
  if (!validation) {
    return { ok: true, refusals: [], warnings: [], summary: "", blocking: false };
  }
  const refusals = validation.refusals ?? [];
  const warnings = validation.warnings ?? [];
  // The capacity warning gets its own amber block, so summarising it here too
  // printed the same long paragraph twice and made it read like two problems.
  const summarisable = otherWarnings(warnings);
  let summary = "";
  if (refusals.length === 1) summary = refusals[0].message;
  else if (refusals.length > 1) summary = `${refusals.length} things need fixing before this can be saved.`;
  else if (summarisable.length === 1) summary = summarisable[0].message;
  else if (summarisable.length > 1) summary = `${summarisable.length} things worth knowing before you run this.`;
  return {
    ok: refusals.length === 0,
    refusals,
    warnings,
    summary,
    blocking: refusals.length > 0,
  };
}

// --- the change list ---------------------------------------------------------

/** Render a config value for the "what did I change?" list. */
export function formatChangeValue(value: unknown): string {
  if (value === null || value === undefined) return "not set";
  if (Array.isArray(value)) return value.join(" – ");
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([key]) => key !== "name")
      .map(([key, item]) => `${key.replace(/_/g, " ")} ${String(item)}`);
    return entries.join(", ");
  }
  return String(value);
}

/**
 * Annotate each change with whether it can actually move the answer.
 *
 * §1.4's whole point: an inert setting visibly changes the dataset page and then
 * fails to change the result, which is nastier than doing nothing. A change list
 * that does not say which is which invites exactly that misreading.
 */
/**
 * The label for one row of the change list.
 *
 * A block-level change (switching a lane disruption on) arrives with the group and
 * the parameter both set to the block name, which renders as
 * `lane_disruption.lane_disruption`. Say it once.
 */
export function changeLabel(change: { group: string; parameter: string }): string {
  return change.group === change.parameter
    ? change.group
    : `${change.group}.${change.parameter}`;
}

export function annotateChanges(
  changes: ConfigChange[],
  settings: SettingSpec[],
): (ConfigChange & { reachLabel: string | null; inert: boolean })[] {
  const byKey = new Map(settings.map((setting) => [setting.key, setting]));
  return changes.map((change) => {
    const setting =
      byKey.get(`${change.group}.${change.parameter}`) ??
      byKey.get(change.parameter);
    if (!setting) {
      return { ...change, reachLabel: null, inert: false };
    }
    return {
      ...change,
      reachLabel: setting.reaches_optimizer ? null : setting.reach_label,
      inert: !setting.reaches_optimizer,
    };
  });
}

/** Seconds -> the wording the estimate uses on screen. */
export function formatSeconds(seconds: number): string {
  if (seconds < 1) return "under a second";
  if (seconds < 60) return `about ${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} seconds`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return rest ? `about ${minutes} min ${rest} s` : `about ${minutes} min`;
}
