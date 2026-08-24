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
  const cannotChange = payload.settings.filter((setting) => !setting.reaches_optimizer);
  const live = payload.settings.filter((setting) => setting.reaches_optimizer);
  const groups = payload.groups
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
/**
 * How long a single refusal or warning may be before the sticky footer summarises
 * it by count instead of repeating it verbatim.
 *
 * 🔴 The footer summary exists because the refusal list can scroll out of view, so
 * echoing a SHORT message there is genuinely useful — that is 6a's behaviour and it
 * is kept. But Iteration 6b's network refusals are three sentences that quote
 * measured figures ("…scores 68,565.25 at 92.01% fill…"), and repeating one of
 * those in full put the same long paragraph on screen twice, directly under itself.
 * Exactly the failure the comment inside `validationDisplay` already records for
 * warnings; this applies the same rule to refusals.
 */
const FOOTER_SUMMARY_MAX = 140;

export function validationDisplay(validation: ValidationPayload | null): ValidationDisplay {
  if (!validation) {
    return { ok: true, refusals: [], warnings: [], summary: "", blocking: false };
  }
  const refusals = validation.refusals ?? [];
  const warnings = validation.warnings ?? [];
  // The capacity warning gets its own amber block, so summarising it here too
  // printed the same long paragraph twice and made it read like two problems.
  const summarisable = otherWarnings(warnings);
  const brief = (message: string) => message.length <= FOOTER_SUMMARY_MAX;
  let summary = "";
  if (refusals.length === 1) {
    summary = brief(refusals[0].message)
      ? refusals[0].message
      : "1 thing needs fixing before this can be saved — see the reason above.";
  } else if (refusals.length > 1) {
    summary = `${refusals.length} things need fixing before this can be saved.`;
  } else if (summarisable.length === 1) {
    summary = brief(summarisable[0].message)
      ? summarisable[0].message
      : "1 thing is worth knowing before you run this — see the note above.";
  } else if (summarisable.length > 1) {
    summary = `${summarisable.length} things worth knowing before you run this.`;
  }
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

/**
 * Iteration 6b Phase 3 — the Network group's own layout.
 *
 * 🔴 The split comes from the payload's `network_tier.classes`, never from a list
 * kept here. §1.2's two classes are a *measured* property (a network-shape count
 * leaves total demand bit-identical; a problem-size count does not), and the
 * server derives them. Hard-coding the split in the form would let it drift from
 * what the ledger proved and put a "safe to compare" label on a resized network.
 *
 * `network.lines_per_plant` is deliberately absent from every class: it is inert,
 * so it belongs under Advanced's existing "recorded in the dataset, not read by
 * the optimizer" heading and must never appear here as a live control (decision 7).
 */
export function networkLayout(payload: CustomSettingsPayload): {
  classes: { answerClass: string; label: string; settings: SettingSpec[] }[];
  inert: SettingSpec[];
  reason: string;
} {
  const tier = payload.network_tier;
  const byKey = new Map(payload.settings.map((setting) => [setting.key, setting]));
  const classes = Object.entries(tier?.classes ?? {})
    .map(([answerClass, keys]) => ({
      answerClass,
      label: tier?.answer_class_labels?.[answerClass] ?? "",
      settings: keys
        .map((key) => byKey.get(key))
        .filter((setting): setting is SettingSpec => Boolean(setting)),
    }))
    .filter((entry) => entry.settings.length > 0);

  const classed = new Set(classes.flatMap((entry) => entry.settings.map((s) => s.key)));
  const inert = (tier?.keys ?? [])
    .map((key) => byKey.get(key))
    .filter(
      (setting): setting is SettingSpec =>
        Boolean(setting) && !classed.has(setting!.key) && !setting!.reaches_optimizer,
    );

  return { classes, inert, reason: tier?.reason ?? "" };
}
