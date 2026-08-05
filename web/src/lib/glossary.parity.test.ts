/**
 * The glossary exists twice on purpose, and must never differ.
 *
 * `web/src/lib/glossary.ts` is the literal the bundle ships, so the web build
 * needs no new input. `src/chat/glossary.json` is what the Python chat layer
 * reads, so Iteration 5 answers definition questions with the SAME sentence the
 * dataset view shows rather than a second, drifting set.
 *
 * This test is the thing that makes "same" true. Edit one, edit both.
 *
 * It reads the JSON from the repo, so web tests must run with the repository
 * root available (`make web-test` does this). A missing file fails loudly rather
 * than skipping — a parity test that quietly skips is worse than none.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { GLOSSARY, GLOSSARY_ORDER } from "./glossary";

// Resolved from the working directory (web/) rather than import.meta.url, which
// vitest does not always expose as a file: URL.
const CANONICAL_PATH = resolve(process.cwd(), "../src/chat/glossary.json");

type CanonicalGlossary = {
  order: string[];
  terms: Record<string, { term: string; definition: string; example?: string }>;
};

function loadCanonical(): CanonicalGlossary {
  let raw: string;
  try {
    raw = readFileSync(CANONICAL_PATH, "utf8");
  } catch (error) {
    throw new Error(
      `Could not read ${CANONICAL_PATH}. Run the web tests from the repository root ` +
        `(make web-test) so the Python glossary is reachable. Original error: ${String(error)}`,
    );
  }
  return JSON.parse(raw) as CanonicalGlossary;
}

describe("glossary parity with the Python chat layer", () => {
  const canonical = loadCanonical();

  it("covers exactly the same terms, in the same order", () => {
    expect(canonical.order).toEqual(GLOSSARY_ORDER);
    expect(Object.keys(canonical.terms).sort()).toEqual(Object.keys(GLOSSARY).sort());
  });

  it("uses identical wording for every term, definition and example", () => {
    for (const key of GLOSSARY_ORDER) {
      const mine = GLOSSARY[key];
      const theirs = canonical.terms[key];
      expect(theirs, `missing '${key}' in src/chat/glossary.json`).toBeDefined();
      expect(theirs.term).toBe(mine.term);
      expect(theirs.definition).toBe(mine.definition);
      expect(theirs.example ?? null).toBe(mine.example ?? null);
    }
  });
});
