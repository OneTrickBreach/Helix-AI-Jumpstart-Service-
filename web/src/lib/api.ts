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
}): string {
  const query = new URLSearchParams({
    scenario: params.scenario,
    horizon: String(params.horizon),
    ppo_timesteps: String(params.ppoTimesteps),
    top_k: String(params.topK),
  });
  return `${API_PREFIX}/scenario-comparison/stream?${query.toString()}`;
}

