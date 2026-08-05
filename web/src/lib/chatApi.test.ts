import { describe, expect, it } from "vitest";

import { MAX_QUESTION_CHARS, SESSION_ID, whatIfStreamUrl } from "./chatApi";
import type { Perturbation } from "./types";

const outage: Perturbation = {
  kind: "node_outage",
  scenario: "component-shortage-shock",
  from_period: 1,
  to_period: 52,
  node_id: "DC-001",
  seed: 12345,
};

describe("what-if stream URL", () => {
  it("asks for a confirmed run and carries the session id", () => {
    const url = new URL(whatIfStreamUrl("component-shortage-shock", outage), "http://x");
    expect(url.pathname).toBe("/api/chat/whatif/stream");
    expect(url.searchParams.get("confirmed")).toBe("true");
    expect(url.searchParams.get("node_id")).toBe("DC-001");
    // The per-session run cap is enforced server-side on this value, and
    // EventSource cannot send headers, so it has to be in the query string.
    expect(url.searchParams.get("session_id")).toBe(SESSION_ID);
  });

  it("omits parameters that do not apply to this perturbation kind", () => {
    const url = new URL(whatIfStreamUrl("component-shortage-shock", outage), "http://x");
    // A node outage has no multipliers, and the API validates the ones it receives.
    expect(url.searchParams.has("capacity_multiplier")).toBe(false);
    expect(url.searchParams.has("demand_multiplier")).toBe(false);
    expect(url.searchParams.has("scope")).toBe(false);
  });

  it("keeps a zero multiplier, which is a real value and not a missing one", () => {
    const closed: Perturbation = {
      ...outage,
      kind: "lane_disruption",
      node_id: undefined,
      lane_id: "LANE-0001",
      capacity_multiplier: 0,
    };
    const url = new URL(whatIfStreamUrl("component-shortage-shock", closed), "http://x");
    expect(url.searchParams.get("capacity_multiplier")).toBe("0");
    expect(url.searchParams.get("lane_id")).toBe("LANE-0001");
  });

  it("matches the API's own session id and question bounds", () => {
    // Server-side: `^[A-Za-z0-9._-]{4,64}$` and `max_length=600`.
    expect(SESSION_ID).toMatch(/^[A-Za-z0-9._-]{4,64}$/);
    expect(MAX_QUESTION_CHARS).toBe(600);
  });
});
