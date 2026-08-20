import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Iteration 6a decision 12 — the chat surface is untouched.
 *
 * Ryan parked the chat bot on 2026-08-19, so Phase 4 built nothing for it. Custom
 * scenarios are *visible* to the chat layer for free, because the scenario list it
 * reads is the same one the dropdown reads — but visible is not the same as
 * claimed, and this pins the difference on the front end.
 *
 * The Python half lives in `tests/test_iteration6a_chat_regression.py`. It cannot
 * cover these files: `web/` is not copied into the api image, and a guardrail that
 * silently skips is not a guardrail.
 */

const CHAT_DIR = join(__dirname);

function source(name: string): string {
  return readFileSync(join(CHAT_DIR, name), "utf-8");
}

describe("the chat panel gained nothing from Iteration 6a", () => {
  const CHAT_FILES = [
    "ChatPanel.tsx",
    "ChatMessage.tsx",
    "WhatIfConfirmCard.tsx",
    "WhatIfResultCard.tsx",
    "ProvenanceChips.tsx",
    "BetaChip.tsx",
  ];

  it.each(CHAT_FILES)("%s carries no custom-scenario control", (file) => {
    const text = source(file);
    for (const token of ["customApi", "CustomScenarioPanel", "customForm", "scenarios/custom"]) {
      expect(text).not.toContain(token);
    }
  });

  it("still carries its BETA label, which Ryan has not asked to remove", () => {
    expect(source("ChatPanel.tsx")).toContain("BetaChip");
  });

  it("does not offer to build, save or delete a scenario", () => {
    const text = source("ChatPanel.tsx").toLowerCase();
    for (const phrase of ["save scenario", "build your own", "new scenario", "delete scenario"]) {
      expect(text).not.toContain(phrase);
    }
  });
});
