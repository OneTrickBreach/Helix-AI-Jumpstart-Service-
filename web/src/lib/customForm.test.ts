import { describe, expect, it } from "vitest";

import {
  advancedLayout,
  annotateChanges,
  capacityWarning,
  changeLabel,
  coerceSetting,
  displayValue,
  formatChangeValue,
  formatSeconds,
  otherWarnings,
  releaseSimpleControl,
  scenarioNameFor,
  simpleControlOverridden,
  slugify,
  validationDisplay,
  valueAt,
} from "./customForm";
import type {
  CustomSettingsPayload,
  SettingSpec,
  SimpleControlSpec,
  ValidationWarning,
} from "./types";

const INERT_LABEL = "recorded in the dataset, not read by the optimizer";

function setting(overrides: Partial<SettingSpec> & { key: string }): SettingSpec {
  return {
    group: overrides.key.split(".")[0],
    kind: "float",
    label: overrides.key,
    reach: "unconditional",
    reach_label: "changes the optimizer's answer",
    reaches_optimizer: true,
    writes: [],
    ...overrides,
  } as SettingSpec;
}

const SETTINGS: SettingSpec[] = [
  setting({ key: "capacity.capacity_tightness" }),
  setting({
    key: "capacity.dc_throughput_units_per_period",
    kind: "int",
    reach: "recorded_not_read",
    reach_label: INERT_LABEL,
    reaches_optimizer: false,
  }),
  setting({ key: "demand.base_units_per_customer_period", kind: "int" }),
  setting({
    key: "service_targets.criticality_tier",
    kind: "str",
    choices: ["standard", "critical"],
    reach: "recorded_not_read",
    reach_label: INERT_LABEL,
    reaches_optimizer: false,
  }),
  setting({ key: "demand.lump_multiplier_range", kind: "range2" }),
];

const SCHEMA: CustomSettingsPayload = {
  base_scenario: "baseline",
  default_seed: 12345,
  name_rules: {
    prefix: "custom-",
    pattern: "^[a-z0-9][a-z0-9-]{0,39}$",
    max_length: 40,
    reserved: ["baseline"],
    note: "",
  },
  groups: ["capacity", "demand", "service_targets"],
  settings: SETTINGS,
  simple_controls: [],
  reach_labels: {},
  ledger: {},
  cannot_change_the_answer: { heading: INERT_LABEL, settings: [], count: 2 },
  excluded_from_6a: { keys: ["network.*"], reason: "" },
};

describe("naming", () => {
  it("turns what a planner types into the slug the server will store", () => {
    expect(slugify("Q3 Surge!")).toBe("q3-surge");
    expect(slugify("  spaces  everywhere  ")).toBe("spaces-everywhere");
    expect(slugify("already-fine")).toBe("already-fine");
  });

  it("never produces a leading or trailing hyphen, which the pattern refuses", () => {
    expect(slugify("--edge--")).toBe("edge");
    expect(slugify("!!!")).toBe("");
  });

  it("caps the slug at the length the API accepts", () => {
    expect(slugify("x".repeat(80))).toHaveLength(40);
  });

  it("shows the full stored name, so nobody is surprised by the prefix", () => {
    expect(scenarioNameFor("Q3 Surge")).toBe("custom-q3-surge");
  });

  it("returns an empty name rather than a bare prefix when there is nothing to slug", () => {
    expect(scenarioNameFor("!!!")).toBe("");
  });
});

describe("advanced layout", () => {
  it("separates the settings that cannot change the answer from the live ones", () => {
    const layout = advancedLayout(SCHEMA);
    const liveKeys = layout.groups.flatMap((group) => group.settings.map((item) => item.key));
    expect(liveKeys).toContain("capacity.capacity_tightness");
    expect(liveKeys).not.toContain("capacity.dc_throughput_units_per_period");
    expect(layout.cannotChange.map((item) => item.key)).toEqual([
      "capacity.dc_throughput_units_per_period",
      "service_targets.criticality_tier",
    ]);
  });

  it("carries the server's own heading rather than inventing one", () => {
    expect(advancedLayout(SCHEMA).heading).toBe(INERT_LABEL);
  });

  it("drops groups that would render empty", () => {
    const layout = advancedLayout(SCHEMA);
    expect(layout.groups.every((group) => group.settings.length > 0)).toBe(true);
    // every live setting in `service_targets` is inert here, so the group is gone
    expect(layout.groups.map((group) => group.group)).not.toContain("service_targets");
  });
});

describe("reading values out of the resolved config", () => {
  const config = {
    capacity: { capacity_tightness: 1.3 },
    demand: { lump_multiplier_range: [1.4, 2.2], shock: null },
  };

  it("walks a dotted path", () => {
    expect(valueAt(config, "capacity.capacity_tightness")).toBe(1.3);
  });

  it("returns undefined rather than throwing on a missing path", () => {
    expect(valueAt(config, "nope.nothing.here")).toBeUndefined();
    expect(valueAt(config, "demand.shock.multiplier")).toBeUndefined();
  });

  it("renders a range as an editable pair", () => {
    expect(displayValue(setting({ key: "demand.lump_multiplier_range", kind: "range2" }), config)).toBe(
      "1.4, 2.2",
    );
  });

  it("renders an unset optional block as empty, not as 'null'", () => {
    expect(displayValue(setting({ key: "demand.shock" }), config)).toBe("");
  });
});

describe("coercing a form field back to the setting's type", () => {
  it("rounds an int and keeps a float", () => {
    expect(coerceSetting(setting({ key: "a", kind: "int" }), "42.7")).toBe(43);
    expect(coerceSetting(setting({ key: "a", kind: "float" }), "1.25")).toBe(1.25);
  });

  it("parses a two-value range", () => {
    expect(coerceSetting(setting({ key: "a", kind: "range2" }), "1.5, 2.4")).toEqual([1.5, 2.4]);
  });

  it("hands a half-typed range back untouched so the server refuses it in plain English", () => {
    expect(coerceSetting(setting({ key: "a", kind: "range2" }), "1.5,")).toBe("1.5,");
  });

  it("leaves a non-numeric entry alone rather than turning it into NaN", () => {
    expect(coerceSetting(setting({ key: "a", kind: "float" }), "lots")).toBe("lots");
  });

  it("passes a string setting straight through", () => {
    expect(coerceSetting(setting({ key: "a", kind: "str" }), "critical")).toBe("critical");
  });
});

describe("keeping Simple and Advanced honest about each other", () => {
  const control: SimpleControlSpec = {
    name: "holding_cost",
    label: "Inventory holding cost",
    kind: "scale",
    writes: ["costs.holding_cost.raw_component", "costs.holding_cost.finished_good"],
  };

  it("reports a Simple control as overridden once Advanced touches one of its settings", () => {
    expect(simpleControlOverridden(control, {})).toBe(false);
    expect(simpleControlOverridden(control, { "costs.holding_cost.finished_good": 2 })).toBe(true);
  });

  it("gives the Simple control back control by dropping its overrides", () => {
    const next = releaseSimpleControl(control, {
      "costs.holding_cost.finished_good": 2,
      "demand.noise_std": 0.3,
    });
    expect(next).toEqual({ "demand.noise_std": 0.3 });
  });
});

describe("validation display", () => {
  it("is quiet and non-blocking before anything has been previewed", () => {
    const display = validationDisplay(null);
    expect(display.blocking).toBe(false);
    expect(display.summary).toBe("");
  });

  it("shows a single refusal verbatim — the API wrote it to be actionable", () => {
    const display = validationDisplay({
      ok: false,
      refusals: [{ code: "above_maximum", field: "x", message: "Keep it at 1.0 or below." }],
      warnings: [],
    });
    expect(display.summary).toBe("Keep it at 1.0 or below.");
    expect(display.blocking).toBe(true);
  });

  it("counts multiple refusals rather than showing only the first", () => {
    const display = validationDisplay({
      ok: false,
      refusals: [
        { code: "a", message: "One." },
        { code: "b", message: "Two." },
      ],
      warnings: [],
    });
    expect(display.summary).toContain("2 things");
    expect(display.refusals).toHaveLength(2);
  });

  it("never blocks on a warning — a warning is information, not a refusal", () => {
    const display = validationDisplay({
      ok: true,
      refusals: [],
      warnings: [{ code: "settings_recorded_not_read", message: "One setting cannot change it." }],
    });
    expect(display.blocking).toBe(false);
    expect(display.ok).toBe(true);
    expect(display.summary).toBe("One setting cannot change it.");
  });
});

describe("the capacity no-op warning gets its own block", () => {
  const warnings: ValidationWarning[] = [
    { code: "settings_recorded_not_read", message: "Two settings cannot change it." },
    {
      code: "capacity_window_misses_read_period",
      message: "The optimizer reads lane capacity at period 52 only.",
      detail: { capacity_read_period: 52 },
    },
  ];

  it("is picked out by code, not by position", () => {
    expect(capacityWarning(warnings)?.detail?.capacity_read_period).toBe(52);
  });

  it("is not repeated in the ordinary warning list", () => {
    expect(otherWarnings(warnings).map((item) => item.code)).toEqual([
      "settings_recorded_not_read",
    ]);
  });

  it("is absent when the window does reach the optimizer", () => {
    expect(capacityWarning([warnings[0]])).toBeUndefined();
  });

  it("is not repeated in the footer summary, which would read as two problems", () => {
    const display = validationDisplay({ ok: true, refusals: [], warnings: [warnings[1]] });
    expect(display.summary).toBe("");
  });

  it("still summarises the other warnings alongside it", () => {
    const display = validationDisplay({ ok: true, refusals: [], warnings });
    expect(display.summary).toBe("Two settings cannot change it.");
  });
});

describe("change row labels", () => {
  it("says a block name once instead of twice", () => {
    expect(changeLabel({ group: "lane_disruption", parameter: "lane_disruption" })).toBe(
      "lane_disruption",
    );
  });

  it("keeps the dotted path for an ordinary setting", () => {
    expect(changeLabel({ group: "demand", parameter: "noise_std" })).toBe("demand.noise_std");
  });
});

describe("the change list", () => {
  it("flags a change that cannot move the answer, with the server's own label", () => {
    const annotated = annotateChanges(
      [
        { group: "capacity", parameter: "capacity_tightness", baseline_value: 1.3, scenario_value: 1.1 },
        {
          group: "capacity",
          parameter: "dc_throughput_units_per_period",
          baseline_value: 9000,
          scenario_value: 12000,
        },
      ],
      SETTINGS,
    );
    expect(annotated[0].inert).toBe(false);
    expect(annotated[0].reachLabel).toBeNull();
    expect(annotated[1].inert).toBe(true);
    expect(annotated[1].reachLabel).toBe(INERT_LABEL);
  });

  it("does not claim a change is inert when the setting is unknown to the schema", () => {
    const annotated = annotateChanges(
      [{ group: "demand", parameter: "shock", baseline_value: null, scenario_value: { multiplier: 1.6 } }],
      SETTINGS,
    );
    expect(annotated[0].inert).toBe(false);
    expect(annotated[0].reachLabel).toBeNull();
  });

  it("renders a switched-on block readably instead of dumping JSON", () => {
    expect(
      formatChangeValue({ name: "custom_demand_spike", multiplier: 1.6, start_period: 30 }),
    ).toBe("multiplier 1.6, start period 30");
  });

  it("says 'not set' for an absent optional block", () => {
    expect(formatChangeValue(null)).toBe("not set");
  });

  it("renders a range with a dash", () => {
    expect(formatChangeValue([1.4, 2.2])).toBe("1.4 – 2.2");
  });
});

describe("the estimate wording", () => {
  it("does not put a decimal point on a sub-second run", () => {
    expect(formatSeconds(0.4)).toBe("under a second");
  });

  it("keeps one decimal where it is meaningful and drops it where it is not", () => {
    expect(formatSeconds(1.2)).toBe("about 1.2 seconds");
    expect(formatSeconds(23.7)).toBe("about 24 seconds");
  });

  it("switches to minutes past a minute", () => {
    expect(formatSeconds(95)).toBe("about 1 min 35 s");
    expect(formatSeconds(120)).toBe("about 2 min");
  });
});
