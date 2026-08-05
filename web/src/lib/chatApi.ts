/**
 * HTTP access for the conversational analyst (Iteration 5, BETA).
 *
 * Kept separate from `api.ts` so the chat surface — the highest-risk thing in this
 * repo for saying something wrong in front of a customer — can be read and
 * reviewed on its own. Every call goes to the same key-injecting nginx proxy as
 * everything else, so no credential reaches the browser.
 *
 * Nothing here interprets a payload. The panel renders what the API returned; the
 * numbers come from the generated data or from `run_head_to_head` on-device.
 */

import type { ApiResponse, ChatAnswer, Perturbation, RecordedTranscript } from "./types";

const API_PREFIX = "/api";

/** Matches the API's `question: str = Field(max_length=600)`. */
export const MAX_QUESTION_CHARS = 600;

/**
 * One id per page load, so the server's per-session what-if cap (Phase 5) applies
 * to this tab rather than to the whole machine.
 *
 * A reload deliberately starts a new session and therefore a new run budget: the
 * cap exists to stop a runaway component grinding through a demo, and the server's
 * sliding window — which is keyed on the caller's address and cannot be reset by
 * anything sent from here — is what actually protects the box.
 */
export const SESSION_ID: string =
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `s-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;

/** Ask one grounded question. Runs no optimizer and mutates nothing. */
export async function askChat(
  scenario: string,
  question: string,
  useLlm = true,
): Promise<ChatAnswer> {
  const response = await fetch(`${API_PREFIX}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-Id": SESSION_ID },
    body: JSON.stringify({ scenario, question, use_llm: useLlm }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Chat request failed: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<ChatAnswer>;
  return payload.data;
}

/**
 * There is deliberately no `POST /chat/whatif` wrapper here.
 *
 * The confirm card arrives inside the `/chat/ask` answer, and a confirmed run goes
 * through the SSE endpoint below so the panel can show the engine's real stage
 * boundaries. A second, unused path to the same endpoint would be dead code on the
 * most safety-critical call in the app.
 *
 * `confirmed` is enforced server-side either way: an unconfirmed request returns
 * the card and runs nothing, whatever this client does.
 */

/**
 * SSE URL for a confirmed what-if.
 *
 * Used instead of the plain POST so the panel can show the *real* stage boundaries
 * the engine reports (`base_forecast`, `base_optimize`, `perturb`,
 * `whatif_forecast`, `whatif_optimize`, and `cache/hit` when a result is already
 * in hand). No stage is announced before it starts — the same truthful-progress
 * rule the benchmark stepper follows.
 */
export function whatIfStreamUrl(
  scenario: string,
  perturbation: Perturbation,
  options: { horizon?: number; includePpo?: boolean; fresh?: boolean } = {},
): string {
  const query = new URLSearchParams({
    scenario,
    kind: perturbation.kind,
    from_period: String(perturbation.from_period),
    to_period: String(perturbation.to_period),
    horizon: String(options.horizon ?? 8),
    include_ppo: String(options.includePpo ?? false),
    confirmed: "true",
    fresh: String(options.fresh ?? false),
    // EventSource cannot set headers, so the session id rides in the query string.
    session_id: SESSION_ID,
  });
  if (perturbation.node_id) query.set("node_id", perturbation.node_id);
  if (perturbation.lane_id) query.set("lane_id", perturbation.lane_id);
  if (perturbation.capacity_multiplier !== undefined && perturbation.capacity_multiplier !== null) {
    query.set("capacity_multiplier", String(perturbation.capacity_multiplier));
  }
  if (perturbation.demand_multiplier !== undefined && perturbation.demand_multiplier !== null) {
    query.set("demand_multiplier", String(perturbation.demand_multiplier));
  }
  if (perturbation.scope) query.set("scope", perturbation.scope);
  if (perturbation.scope_id) query.set("scope_id", perturbation.scope_id);
  return `${API_PREFIX}/chat/whatif/stream?${query.toString()}`;
}

export const RECORDED_TRANSCRIPT_URL = "/demo-chat-transcript.json";

/** The recorded transcript used by `?replay=true` — no API, no GPU, no LLM. */
export async function fetchRecordedTranscript(): Promise<RecordedTranscript> {
  const response = await fetch(RECORDED_TRANSCRIPT_URL);
  if (!response.ok) {
    throw new Error(`Recorded chat transcript not found (${response.status})`);
  }
  return (await response.json()) as RecordedTranscript;
}
