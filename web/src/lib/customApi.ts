import type {
  ApiResponse,
  CustomPreview,
  CustomSettingsPayload,
  RunCard,
  SavedScenario,
  ValidationPayload,
} from "./types";

const API_PREFIX = "/api";

/**
 * A refusal the API returned as 422 with the whole preview attached.
 *
 * Decision 11 is validate-then-refuse-in-plain-English, so the panel shows the
 * sentences the API wrote rather than inventing its own wording. Keeping the
 * payload on the error is what lets it do that.
 */
export class CustomScenarioRefused extends Error {
  readonly validation: ValidationPayload;
  readonly preview: CustomPreview | null;

  constructor(message: string, validation: ValidationPayload, preview: CustomPreview | null) {
    super(message);
    this.validation = validation;
    this.preview = preview;
  }
}

/** A conflict or protection refusal — 409 from the store. */
export class CustomScenarioConflict extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export type CustomScenarioRequest = {
  name: string;
  overrides?: Record<string, unknown>;
  simple?: Record<string, unknown>;
  seed?: number;
  description?: string | null;
  horizon?: number;
  include_ppo?: boolean;
  include_rationale?: boolean;
  overwrite?: boolean;
};

async function readError(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (response.status === 422 && detail && typeof detail === "object" && "validation" in detail) {
    const preview = detail as CustomPreview;
    throw new CustomScenarioRefused(
      preview.validation.refusals[0]?.message ?? "That configuration was refused.",
      preview.validation,
      preview,
    );
  }
  if (detail && typeof detail === "object" && "code" in detail) {
    throw new CustomScenarioConflict(
      String((detail as { code: string }).code),
      String((detail as { message?: string }).message ?? "That request was refused."),
    );
  }
  throw new Error(
    typeof detail === "string" ? detail : `Request failed (${response.status})`,
  );
}

export async function fetchCustomSettings(): Promise<CustomSettingsPayload> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom/settings`);
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<CustomSettingsPayload>;
  return payload.data;
}

/**
 * Resolve edits without writing or running anything.
 *
 * A 422 here is not an error to swallow: it carries the refusals the panel shows.
 */
export async function previewCustomScenario(
  body: CustomScenarioRequest,
): Promise<CustomPreview> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<CustomPreview>;
  return payload.data;
}

export async function saveCustomScenario(body: CustomScenarioRequest): Promise<SavedScenario> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<{ saved: SavedScenario }>;
  return payload.data.saved;
}

export async function fetchSavedScenarios(): Promise<SavedScenario[]> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom`);
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<{ scenarios: SavedScenario[] }>;
  return payload.data.scenarios;
}

export async function deleteCustomScenario(slug: string): Promise<string[]> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom/${encodeURIComponent(slug)}`, {
    method: "DELETE",
  });
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<{ removed: string[] }>;
  return payload.data.removed;
}

export async function clearCustomScenarios(): Promise<string[]> {
  const response = await fetch(`${API_PREFIX}/scenarios/custom`, { method: "DELETE" });
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<{ deleted: string[] }>;
  return payload.data.deleted;
}

/** The pre-run card for a scenario already on disk. Runs nothing. */
export async function fetchRunCard(
  scenario: string,
  options: { includePpo?: boolean; includeRationale?: boolean; horizon?: number } = {},
): Promise<RunCard> {
  const query = new URLSearchParams({ scenario });
  if (options.horizon !== undefined) query.set("horizon", String(options.horizon));
  if (options.includePpo !== undefined) query.set("include_ppo", String(options.includePpo));
  if (options.includeRationale !== undefined) {
    query.set("include_rationale", String(options.includeRationale));
  }
  const response = await fetch(`${API_PREFIX}/scenario-comparison/card?${query.toString()}`);
  if (!response.ok) await readError(response);
  const payload = (await response.json()) as ApiResponse<RunCard>;
  return payload.data;
}
