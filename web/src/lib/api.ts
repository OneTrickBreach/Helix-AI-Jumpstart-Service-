import type { ApiResponse, ScenarioSummary } from "./types";

const API_PREFIX = "/api";

export async function fetchScenarios(): Promise<ScenarioSummary[]> {
  const response = await fetch(`${API_PREFIX}/scenarios`);
  if (!response.ok) {
    throw new Error(`Scenario list failed: ${response.status}`);
  }
  const payload = (await response.json()) as ApiResponse<{ scenarios: ScenarioSummary[] }>;
  return payload.data.scenarios;
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

