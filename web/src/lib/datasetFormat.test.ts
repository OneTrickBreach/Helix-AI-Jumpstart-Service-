import { describe, expect, it } from "vitest";

import {
  bytes,
  count,
  days,
  humanizeKey,
  money,
  multiplier,
  percent,
  periodRange,
  pluralize,
  showingLabel,
  units,
} from "./datasetFormat";
import { GLOSSARY, GLOSSARY_ORDER, lookupTerm } from "./glossary";

describe("count", () => {
  it("adds thousands separators", () => {
    expect(count(44928)).toBe("44,928");
    expect(count(0)).toBe("0");
  });

  it("renders missing values as a dash, never NaN or null", () => {
    expect(count(null)).toBe("—");
    expect(count(undefined)).toBe("—");
    expect(count(Number.NaN)).toBe("—");
  });
});

describe("pluralize", () => {
  it("uses the singular for exactly one", () => {
    expect(pluralize(1, "supplier")).toBe("1 supplier");
    expect(pluralize(1, "factory", "factories")).toBe("1 factory");
  });

  it("uses the plural for zero and for many", () => {
    expect(pluralize(0, "supplier")).toBe("0 suppliers");
    expect(pluralize(5, "supplier")).toBe("5 suppliers");
    expect(pluralize(2, "factory", "factories")).toBe("2 factories");
  });

  it("separates thousands", () => {
    expect(pluralize(15808, "lane")).toBe("15,808 lanes");
  });
});

describe("units", () => {
  it("rounds and labels", () => {
    expect(units(1284.7)).toBe("1,285 units");
    expect(units(1)).toBe("1 unit");
    expect(units(0)).toBe("0 units");
  });

  it("keeps requested precision", () => {
    expect(units(18.106, 2)).toBe("18.11 units");
  });
});

describe("percent", () => {
  it("scales and rounds", () => {
    expect(percent(0.8366)).toBe("83.7%");
    expect(percent(0.96, 0)).toBe("96%");
    expect(percent(0)).toBe("0.0%");
  });
});

describe("money", () => {
  it("formats unit costs with cents", () => {
    expect(money(1.15)).toBe("$1.15");
  });

  it("keeps extra precision when asked", () => {
    expect(money(0.4326, 4)).toBe("$0.4326");
  });
});

describe("days", () => {
  it("handles singular and plural", () => {
    expect(days(9.44)).toBe("9.4 days");
    expect(days(1)).toBe("1 day");
    expect(days(0)).toBe("0 days");
  });
});

describe("periodRange", () => {
  it("renders a real range", () => {
    expect(periodRange(18, 27)).toBe("weeks 18–27");
  });

  it("collapses a single period", () => {
    expect(periodRange(18, 18)).toBe("week 18");
    expect(periodRange(18, null)).toBe("week 18");
  });

  it("respects a different period unit", () => {
    expect(periodRange(3, 6, "month")).toBe("months 3–6");
  });

  it("renders a dash when there is no window", () => {
    expect(periodRange(null, null)).toBe("—");
  });
});

describe("multiplier", () => {
  it("keeps a genuine zero rather than showing it as missing", () => {
    expect(multiplier(0)).toBe("0x");
  });

  it("trims trailing zeros", () => {
    expect(multiplier(3)).toBe("3x");
    expect(multiplier(2.4)).toBe("2.4x");
    expect(multiplier(1.75)).toBe("1.75x");
  });

  it("still dashes on missing data", () => {
    expect(multiplier(null)).toBe("—");
  });
});

describe("humanizeKey", () => {
  it("turns schema names into sentence case", () => {
    expect(humanizeKey("distribution_center")).toBe("Distribution center");
    expect(humanizeKey("lane_periods")).toBe("Lane periods");
  });

  it("survives an empty key", () => {
    expect(humanizeKey("")).toBe("");
  });
});

describe("bytes", () => {
  it("scales units", () => {
    expect(bytes(512)).toBe("512 B");
    expect(bytes(117163)).toBe("114.4 KB");
    expect(bytes(6_500_000)).toBe("6.2 MB");
  });
});

describe("showingLabel", () => {
  it("says what was withheld when truncated", () => {
    expect(showingLabel({ shown: 12, total: 288, truncated: true })).toBe(
      "showing top 12 of 288",
    );
  });

  it("says so when nothing was withheld", () => {
    expect(showingLabel({ shown: 30, total: 30, truncated: false })).toBe("showing all 30");
  });

  it("renders nothing when absent", () => {
    expect(showingLabel(null)).toBe("");
  });
});

describe("glossary", () => {
  it("orders every defined term exactly once", () => {
    expect([...GLOSSARY_ORDER].sort()).toEqual(Object.keys(GLOSSARY).sort());
    expect(new Set(GLOSSARY_ORDER).size).toBe(GLOSSARY_ORDER.length);
  });

  it("defines every term in one plain sentence", () => {
    for (const key of GLOSSARY_ORDER) {
      const entry = GLOSSARY[key];
      expect(entry.term.length).toBeGreaterThan(0);
      expect(entry.definition.trim().endsWith(".")).toBe(true);
      // One sentence: at most one terminal period inside the definition body.
      expect(entry.definition.slice(0, -1).includes(". ")).toBe(false);
    }
  });

  it("keeps jargon out of the definitions themselves", () => {
    // A definition that needs another glossary entry to be understood has failed.
    const jargon = [
      "echelon",
      "(s,S)",
      "(s, S)",
      "stochastic",
      "heuristic",
      "SKU",
      "latency",
      "replenishment",
    ];
    for (const key of GLOSSARY_ORDER) {
      const { term, definition } = GLOSSARY[key];
      for (const word of jargon) {
        if (term.toLowerCase().includes(word.toLowerCase())) continue;
        expect(definition.toLowerCase()).not.toContain(word.toLowerCase());
      }
    }
  });

  it("looks terms up by key", () => {
    expect(lookupTerm("lane")?.term).toBe("Lane");
    expect(lookupTerm("not_a_term")).toBeUndefined();
  });
});
