import type { ApiResponse, DatasetOverview, ScenarioSummary } from "./types";

const API_PREFIX = "/api";

/** Raised when the scenario exists but its data has not been generated (HTTP 409). */
export class DatasetNotGenerated extends Error {}

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  const response = await fetch(`${API_PREFIX}/scenarios`);
  if (!response.ok) {
    throw new Error(`Scenario list failed: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<{ scenarios: ScenarioSummary[] }>;
  return payload.data.scenarios;
}

/** Real captured snapshot used by `?replay=true`, so the demo needs no live GPU. */
export const DEMO_DATASET_OVERVIEW_URL = "/demo-dataset-overview.json";

/**
 * Load the recorded dataset overview instead of calling the API.
 *
 * This is a real payload captured from this device, not mock data — the same shape
 * `fetchDatasetOverview` returns, so replay and live render through identical code.
 */
export async function fetchRecordedDatasetOverview(): Promise<DatasetOverview> {
  const response = await fetch(DEMO_DATASET_OVERVIEW_URL);
  if (!response.ok) {
    throw new Error(`Recorded dataset snapshot not found (${response.status})`);
  }
  return (await response.json()) as DatasetOverview;
}

/**
 * Fetch the pre-aggregated dataset overview.
 *
 * The API distinguishes "no such scenario" (404) from "scenario exists but has no
 * generated data" (409), and the UI shows genuinely different things for each — a
 * 409 tells the viewer to run `make demo-data`, which is actionable.
 */
export async function fetchDatasetOverview(scenario: string): Promise<DatasetOverview> {
  const query = new URLSearchParams({ scenario });
  const response = await fetch(`${API_PREFIX}/dataset/overview?${query.toString()}`);
  if (response.status === 409) {
    const detail = await response.json().catch(() => null);
    throw new DatasetNotGenerated(
      detail?.detail ?? `No data generated for "${scenario}" yet.`,
    );
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Dataset overview failed: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<{
    dataset_overview: DatasetOverview;
  }>;
  return payload.data.dataset_overview;
}

/** Direct link to a raw CSV download, served through the key-injecting proxy. */
export function datasetTableUrl(scenario: string, table: string): string {
  const query = new URLSearchParams({ scenario, table });
  return `${API_PREFIX}/dataset/table?${query.toString()}`;
}

export function scenarioStreamUrl(params: {
  scenario: string;
  horizon: number;
  ppoTimesteps: number;
  topK: number;
  /**
   * Iteration 6a: omit both to get the server's default for the scenario kind —
   * full behaviour for the four recorded scenarios, the fast path for a custom
   * one. Only send them when the caller is deliberately choosing.
   */
  includePpo?: boolean;
  includeRationale?: boolean;
}): string {
  const query = new URLSearchParams({
    scenario: params.scenario,
    horizon: String(params.horizon),
    ppo_timesteps: String(params.ppoTimesteps),
    top_k: String(params.topK),
  });
  if (params.includePpo !== undefined) query.set("include_ppo", String(params.includePpo));
  if (params.includeRationale !== undefined) {
    query.set("include_rationale", String(params.includeRationale));
  }
  return `${API_PREFIX}/scenario-comparison/stream?${query.toString()}`;
}

