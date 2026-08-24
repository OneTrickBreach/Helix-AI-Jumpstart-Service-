/**
 * Build your own scenario (Iteration 6a).
 *
 * The control panel Ryan asked for on 2026-08-19: open with baseline's values,
 * move the settings that define a scenario, run the real pipeline, name it and
 * save it so it comes back next time.
 *
 * Two rules this component exists to honour, both of them correctness rather than
 * polish (§0.6 puts them in the first slice):
 *
 * 1. **No control lies about what it can do.** The 15 settings that cannot move
 *    the optimizer's answer are shown in Advanced under an explicit heading, never
 *    as live controls in Simple, and a change list annotates them. The labels come
 *    from the server's ledger, which derived them from the running system.
 * 2. **A window that cannot reach the optimizer is called out before the run.**
 *    Lane capacity is read at exactly one period, so a narrow disruption window is
 *    a measured no-op. Saying so before spending the compute is the difference
 *    between an honest answer and a confident zero.
 */

import { AlertTriangle, Info, Loader2, Play, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  CustomScenarioConflict,
  CustomScenarioRefused,
  clearCustomScenarios,
  deleteCustomScenario,
  fetchCustomSettings,
  fetchSavedScenarios,
  previewCustomScenario,
  saveCustomScenario,
} from "../lib/customApi";
import type { CustomScenarioRequest } from "../lib/customApi";
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
  networkLayout,
  releaseSimpleControl,
  scenarioNameFor,
  simpleControlOverridden,
  validationDisplay,
} from "../lib/customForm";
import type {
  CustomPreview,
  CustomSettingsPayload,
  SavedScenario,
  SettingSpec,
  SimpleControlSpec,
} from "../lib/types";

/** Long enough to stop a slider drag firing a request per pixel; short enough to feel live. */
const PREVIEW_DEBOUNCE_MS = 350;

type Props = {
  /** Run a saved scenario through the real pipeline. */
  onRun: (scenario: string) => void;
  onClose: () => void;
  /** Called after any change to the saved set, so the dropdown can refresh. */
  onSavedSetChanged: () => void;
  /**
   * Decision 8's two opt-ins, owned by the parent so the panel and the results
   * header cannot disagree about what the next run will do.
   */
  includePpo: boolean;
  includeRationale: boolean;
  onIncludePpoChange: (value: boolean) => void;
  onIncludeRationaleChange: (value: boolean) => void;
};

export default function CustomScenarioPanel({
  onRun,
  onClose,
  onSavedSetChanged,
  includePpo,
  includeRationale,
  onIncludePpoChange,
  onIncludeRationaleChange,
}: Props) {
  const [schema, setSchema] = useState<CustomSettingsPayload | null>(null);
  const [saved, setSaved] = useState<SavedScenario[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [simple, setSimple] = useState<Record<string, unknown>>({});
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [seed, setSeed] = useState(12345);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [preview, setPreview] = useState<CustomPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const debounce = useRef<number | null>(null);

  const refreshSaved = useCallback(() => {
    fetchSavedScenarios()
      .then(setSaved)
      .catch(() => setSaved([]));
  }, []);

  useEffect(() => {
    fetchCustomSettings()
      .then(setSchema)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    refreshSaved();
  }, [refreshSaved]);

  // The preview is the single source of truth for the resolved config, the change
  // list and the validation verdict — the same endpoint the save path runs, so what
  // is shown here is what would be written. Debounced because it is on the `light`
  // rate bucket and a slider drag would otherwise spend the whole allowance.
  useEffect(() => {
    if (!schema) return;
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      setPreviewing(true);
      previewCustomScenario({
        name: name.trim() || "draft",
        simple,
        overrides,
        seed,
        description: description.trim() || null,
        include_ppo: includePpo,
        include_rationale: includeRationale,
      })
        .then((payload) => {
          setPreview(payload);
          setError(null);
        })
        .catch((err: unknown) => {
          if (err instanceof CustomScenarioRefused && err.preview) {
            setPreview(err.preview);
            setError(null);
            return;
          }
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => setPreviewing(false));
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [schema, name, description, simple, overrides, seed, includePpo, includeRationale]);

  const validation = validationDisplay(preview?.validation ?? null);
  const capacity = capacityWarning(validation.warnings);
  const rest = otherWarnings(validation.warnings);
  const layout = useMemo(() => (schema ? advancedLayout(schema) : null), [schema]);
  const network = useMemo(() => (schema ? networkLayout(schema) : null), [schema]);
  const changes = useMemo(
    () => (preview && schema ? annotateChanges(preview.config_changes, schema.settings) : []),
    [preview, schema],
  );
  const targetName = scenarioNameFor(name, schema?.name_rules.prefix ?? "custom-");
  const canSave = Boolean(name.trim()) && validation.ok && !busy;

  const request = (): CustomScenarioRequest => ({
    name: name.trim(),
    simple,
    overrides,
    seed,
    description: description.trim() || null,
    include_ppo: includePpo,
    include_rationale: includeRationale,
  });

  async function handleSave(runAfter: boolean) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await saveCustomScenario(request());
      setNotice(
        `Saved as ${result.scenario}. It is now in the scenario dropdown.`,
      );
      refreshSaved();
      onSavedSetChanged();
      if (runAfter) onRun(result.scenario);
    } catch (err: unknown) {
      if (err instanceof CustomScenarioRefused) setError(err.message);
      else if (err instanceof CustomScenarioConflict) setError(err.message);
      else setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(slug: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteCustomScenario(slug);
      setNotice(`Deleted custom-${slug}.`);
      refreshSaved();
      onSavedSetChanged();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleClearAll() {
    setBusy(true);
    setError(null);
    try {
      const deleted = await clearCustomScenarios();
      setNotice(
        deleted.length
          ? `Deleted ${deleted.length} custom scenario${deleted.length === 1 ? "" : "s"}. The four recorded scenarios are untouched.`
          : "There were no custom scenarios to delete.",
      );
      refreshSaved();
      onSavedSetChanged();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function setSimpleValue(control: SimpleControlSpec, value: unknown) {
    // An Advanced edit on the same settings would otherwise win silently and make
    // this control show a value that is not in effect.
    setOverrides((current) => releaseSimpleControl(control, current));
    setSimple((current) => ({ ...current, [control.name]: value }));
  }

  if (error && !schema) {
    return (
      <aside className="w-full shrink-0 border-l border-line bg-white p-4 lg:w-[30rem]" data-testid="custom-panel">
        <PanelHeader onClose={onClose} />
        <p className="mt-4 rounded-md border border-[#d8b4a0] bg-[#fdf6f1] p-3 text-sm text-[#8a4b2a]">{error}</p>
      </aside>
    );
  }

  return (
    <aside
      // relative z-40 so the action bar sits above the fixed z-30 chat button even
      // on a viewport too narrow for the shift to help.
      className="relative z-40 flex w-full shrink-0 flex-col border-l border-line bg-white lg:w-[30rem]"
      data-testid="custom-panel"
    >
      <div className="sticky top-0 z-10 border-b border-line bg-white px-4 py-3">
        <PanelHeader onClose={onClose} />
        <p className="mt-1 text-xs leading-5 text-[#6b7a70]">
          Starts from <strong>{schema?.base_scenario ?? "baseline"}</strong>. Everything you change is
          listed below, and the result is labelled as custom — never as one of the four recorded
          benchmark results.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {/* --- saved scenarios: load, delete, clear all ---------------------- */}
        {/* Deliberately FIRST. Ryan asked for save *and* delete on 2026-08-19, and
            when this sat at the bottom of the panel's scroll area — behind the
            change list and the estimate, as a bare icon — a reviewer could not
            find it at all. Load/delete is also the first thing you want on a
            second visit, before building anything new. */}
        <section className="rounded-md border border-line bg-field p-3" data-testid="custom-saved">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#587060]">
              Your saved scenarios ({saved.length})
            </h3>
            {saved.length ? (
              <button
                type="button"
                onClick={handleClearAll}
                disabled={busy}
                className="rounded border border-[#d8b4a0] px-2 py-1 text-xs font-semibold text-[#8a4b2a] transition hover:bg-[#fdf6f1] disabled:opacity-50"
                data-testid="custom-clear-all"
              >
                Delete all
              </button>
            ) : null}
          </div>
          {saved.length ? (
            <ul className="mt-2 space-y-1" data-testid="custom-saved-list">
              {saved.map((item) => (
                <li
                  key={item.scenario}
                  className="flex items-center justify-between gap-2 rounded border border-line bg-white px-2 py-1.5"
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left font-mono text-xs text-[#2f6d4f] underline"
                    onClick={() => onRun(item.scenario)}
                    title="Run this scenario again"
                  >
                    {item.scenario}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(item.slug)}
                    disabled={busy}
                    className="inline-flex shrink-0 items-center gap-1 rounded border border-[#d8b4a0] px-2 py-0.5 text-xs font-semibold text-[#8a4b2a] transition hover:bg-[#fdf6f1] disabled:opacity-50"
                    aria-label={`Delete ${item.scenario}`}
                    data-testid={`custom-delete-${item.slug}`}
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs leading-5 text-[#6b7a70]">
              Nothing saved yet. Build one below and click <strong>Save</strong>; it will appear here
              and in the scenario dropdown, with a <strong>Delete</strong> button beside it. Saved
              scenarios live on this box and are visible to anyone who can reach it.
            </p>
          )}
        </section>

        {/* --- name and seed ------------------------------------------------ */}
        <label className="control-label">
          Name this scenario
          <input
            className="control"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="q3-surge"
            data-testid="custom-name"
            maxLength={64}
          />
        </label>
        {targetName ? (
          <p className="mt-1 text-xs text-[#6b7a70]" data-testid="custom-target-name">
            Will be saved as <code className="font-mono">{targetName}</code>
          </p>
        ) : null}

        <label className="control-label mt-3">
          Description (optional)
          <input
            className="control"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Q3 surge with tighter lanes"
            maxLength={280}
          />
        </label>

        {/* --- Simple tier -------------------------------------------------- */}
        <h3 className="mt-5 text-sm font-semibold uppercase tracking-[0.12em] text-[#587060]">
          The controls
        </h3>
        <div className="mt-2 space-y-3">
          {(schema?.simple_controls ?? []).map((control) => (
            <SimpleControl
              key={control.name}
              control={control}
              value={simple[control.name]}
              overridden={simpleControlOverridden(control, overrides)}
              onChange={(value) => setSimpleValue(control, value)}
            />
          ))}
        </div>

        {/* --- Network tier (Iteration 6b) ---------------------------------- */}
        {network && network.classes.length > 0 && preview ? (
          <section className="mt-5" data-testid="custom-network">
            <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#587060]">
              The network
            </h3>
            <p className="mt-1 text-xs leading-5 text-[#6b7a70]" data-testid="custom-network-reason">
              {network.reason}
            </p>
            <div className="mt-2 space-y-3">
              {network.classes.map((entry) => (
                <div
                  key={entry.answerClass}
                  className="rounded-md border border-line bg-field p-2"
                  data-testid={`network-class-${entry.answerClass}`}
                >
                  <p
                    className="text-xs leading-5 text-[#6b5a2a]"
                    data-testid={`network-class-label-${entry.answerClass}`}
                  >
                    {entry.label}
                  </p>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {entry.settings.map((setting) => (
                      <NetworkCount
                        key={setting.key}
                        setting={setting}
                        value={displayValue(setting, preview.resolved_config)}
                        onChange={(raw) =>
                          setOverrides((current) => {
                            // Clearing the field must not read as "zero of these".
                            // `Number("")` is 0, so an empty box would otherwise fire
                            // the warehouse-less-network refusal at a planner who was
                            // only mid-retype. Drop the override instead.
                            if (raw.trim() === "") {
                              const { [setting.key]: _dropped, ...rest } = current;
                              return rest;
                            }
                            return { ...current, [setting.key]: coerceSetting(setting, raw) };
                          })
                        }
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {/* --- Advanced tier ------------------------------------------------ */}
        <button
          type="button"
          className="mt-5 text-sm font-semibold text-[#2f6d4f] underline"
          onClick={() => setShowAdvanced((open) => !open)}
          data-testid="custom-advanced-toggle"
        >
          {showAdvanced ? "Hide" : "Show"} all {schema?.settings.length ?? 67} settings
        </button>

        {showAdvanced && layout && preview ? (
          <div className="mt-3 space-y-4" data-testid="custom-advanced">
            <label className="control-label">
              Random seed (reproducible)
              <input
                className="control"
                type="number"
                value={seed}
                onChange={(event) => setSeed(Number(event.target.value))}
              />
            </label>
            {layout.groups.map((group) => (
              <section key={group.group}>
                <h4 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6b7a70]">
                  {group.group.replace(/_/g, " ")}
                </h4>
                <div className="mt-1 space-y-2">
                  {group.settings.map((setting) => (
                    <AdvancedControl
                      key={setting.key}
                      setting={setting}
                      value={displayValue(setting, preview.resolved_config)}
                      onChange={(raw) =>
                        setOverrides((current) => ({
                          ...current,
                          [setting.key]: coerceSetting(setting, raw),
                        }))
                      }
                    />
                  ))}
                </div>
              </section>
            ))}

            {/* Decision 15. This heading is the whole point of the section. */}
            <section
              className="rounded-md border border-[#d9d0b8] bg-[#fbf8ee] p-3"
              data-testid="custom-inert-settings"
            >
              <h4 className="flex items-start gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7a6a3a]">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span data-testid="custom-inert-heading">{layout.heading}</span>
              </h4>
              <p className="mt-1 text-xs leading-5 text-[#6b6349]">
                These {layout.cannotChange.length} settings are part of the dataset and show up on the
                dataset page, but the forecast and the optimizer never read them — so changing one
                cannot change the result. They are editable so the saved scenario is complete and
                honest, not because they are levers.
              </p>
              <div className="mt-2 space-y-2">
                {layout.cannotChange.map((setting) => (
                  <AdvancedControl
                    key={setting.key}
                    setting={setting}
                    value={displayValue(setting, preview.resolved_config)}
                    onChange={(raw) =>
                      setOverrides((current) => ({
                        ...current,
                        [setting.key]: coerceSetting(setting, raw),
                      }))
                    }
                  />
                ))}
              </div>
            </section>
          </div>
        ) : null}

        {/* --- the capacity no-op warning ----------------------------------- */}
        {capacity ? (
          <div
            className="mt-5 rounded-md border border-[#d9b45f] bg-[#fdf7e6] p-3"
            data-testid="custom-capacity-warning"
          >
            <p className="flex items-start gap-2 text-sm font-semibold text-[#7a5b12]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              This disruption will not change the answer
            </p>
            <p className="mt-1 text-sm leading-6 text-[#6b5a2a]">{capacity.message}</p>
            <p className="mt-2 text-sm font-semibold text-[#7a5b12]">
              Do not read an unchanged result as resilience.
            </p>
          </div>
        ) : null}

        {rest.length ? (
          <ul className="mt-3 space-y-2" data-testid="custom-warnings">
            {rest.map((warning) => (
              <li
                key={warning.code + (warning.field ?? "")}
                className="rounded-md border border-[#cfd8cf] bg-[#f7faf7] p-2 text-xs leading-5 text-[#4d5c51]"
              >
                {warning.message}
              </li>
            ))}
          </ul>
        ) : null}

        {/* --- refusals ----------------------------------------------------- */}
        {validation.refusals.length ? (
          <ul className="mt-4 space-y-2" data-testid="custom-refusals">
            {validation.refusals.map((refusal) => (
              <li
                key={refusal.code + (refusal.field ?? "")}
                className="rounded-md border border-[#d8b4a0] bg-[#fdf6f1] p-2 text-sm leading-6 text-[#8a4b2a]"
              >
                {refusal.message}
              </li>
            ))}
          </ul>
        ) : null}

        {/* --- what did I change? ------------------------------------------- */}
        {changes.length ? (
          <div className="mt-5" data-testid="custom-changes">
            <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#587060]">
              What you changed ({changes.length})
            </h3>
            <ul className="mt-2 space-y-1">
              {changes.map((change) => (
                <li key={`${change.group}.${change.parameter}`} className="text-xs leading-5 text-[#4d5c51]">
                  <span className="font-medium">{changeLabel(change)}</span>{" "}
                  {formatChangeValue(change.baseline_value)} → {formatChangeValue(change.scenario_value)}
                  {change.inert ? (
                    <span className="ml-1 rounded bg-[#f3edda] px-1 py-0.5 text-[10px] font-semibold uppercase text-[#7a6a3a]">
                      {change.reachLabel}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {/* --- the estimate, with its basis --------------------------------- */}
        {preview ? (
          <div className="mt-5 rounded-md border border-line bg-field p-3" data-testid="custom-estimate">
            <p className="text-sm font-semibold text-ink">
              A run should take {formatSeconds(preview.run_estimate.total_seconds)}
            </p>
            <ul className="mt-1 space-y-0.5">
              {preview.run_estimate.components.map((component) => (
                <li key={component.stage} className="text-xs leading-5 text-[#6b7a70]">
                  {component.stage} {component.seconds}s — {component.basis}
                </li>
              ))}
            </ul>
            {preview.run_estimate.excluded.length ? (
              <p className="mt-1 text-xs text-[#6b7a70]">
                Excluded: {preview.run_estimate.excluded.join(", ")}. Seed {preview.seed}.
              </p>
            ) : null}
          </div>
        ) : null}

      </div>

      {/* --- actions -------------------------------------------------------- */}
      <div className="sticky bottom-0 border-t border-line bg-white px-4 py-3">
        {notice ? (
          <p className="mb-2 text-xs leading-5 text-[#2f6d4f]" data-testid="custom-notice">
            {notice}
          </p>
        ) : null}
        {error ? (
          <p className="mb-2 text-xs leading-5 text-[#8a4b2a]" data-testid="custom-error">
            {error}
          </p>
        ) : null}
        {validation.summary && !error ? (
          <p className="mb-2 text-xs leading-5 text-[#6b7a70]" data-testid="custom-validation-summary">
            {validation.summary}
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleSave(false)}
            disabled={!canSave}
            className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-[#536258] transition hover:bg-field disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="custom-save"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </button>
          <button
            type="button"
            onClick={() => handleSave(true)}
            disabled={!canSave}
            className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md bg-ink px-3 text-sm font-semibold text-white shadow-soft transition hover:bg-[#263329] disabled:cursor-not-allowed disabled:opacity-60"
            data-testid="custom-save-run"
          >
            <Play className="h-4 w-4" />
            Save &amp; run
          </button>
        </div>
        <p className="mt-2 text-[10px] leading-4 text-[#8a9690]">
          {previewing ? "Checking…" : "Synthetic, seeded, on-device data. Not customer data."}
        </p>
      </div>
    </aside>
  );
}

function PanelHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#587060]">
          Custom scenario
        </p>
        <h2 className="text-lg font-semibold text-ink">Build your own</h2>
      </div>
      <button type="button" onClick={onClose} aria-label="Close custom scenario panel">
        <X className="h-4 w-4 text-[#6b7a70]" />
      </button>
    </div>
  );
}

/**
 * One Simple-tier control.
 *
 * A `group` control is several fields behind one idea — "demand spike: 1.6x for
 * 8 weeks from week 20" is one thing a planner says — so it renders as a small
 * fieldset rather than pretending to be a slider.
 */
function SimpleControl({
  control,
  value,
  overridden,
  onChange,
}: {
  control: SimpleControlSpec;
  value: unknown;
  overridden: boolean;
  onChange: (value: unknown) => void;
}) {
  const enabled = value !== undefined && value !== null;
  if (control.kind === "group") {
    const fields = (value as Record<string, number> | undefined) ?? {};
    return (
      <div className="rounded-md border border-line bg-field p-2" data-testid={`simple-${control.name}`}>
        <label className="flex items-center gap-2 text-sm font-medium text-ink">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => onChange(event.target.checked ? {} : null)}
          />
          {control.label}
        </label>
        {control.help ? <p className="mt-1 text-xs leading-5 text-[#6b7a70]">{control.help}</p> : null}
        {enabled ? (
          <div className="mt-2 grid grid-cols-2 gap-2">
            {(control.fields ?? []).map((field) => (
              <label key={field} className="text-xs text-[#4d5c51]">
                {field.replace(/_/g, " ")}
                <input
                  className="control mt-0.5"
                  value={fields[field] ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...fields,
                      [field]:
                        event.target.value === ""
                          ? undefined
                          : field.includes("type")
                            ? event.target.value
                            : Number(event.target.value),
                    })
                  }
                />
              </label>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <label className="control-label" data-testid={`simple-${control.name}`}>
      <span className="flex items-baseline justify-between gap-2">
        <span>
          {control.label}
          {control.kind === "scale" ? " (x baseline)" : ""}
        </span>
        {overridden ? (
          <span className="text-[10px] font-semibold uppercase text-[#7a6a3a]">set in advanced</span>
        ) : null}
      </span>
      <input
        className="control"
        type="number"
        value={value === undefined || value === null ? "" : String(value)}
        min={control.minimum}
        max={control.maximum}
        step="any"
        placeholder={control.kind === "scale" ? "1" : "baseline"}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
      />
      {control.help ? <span className="mt-0.5 text-xs leading-5 text-[#6b7a70]">{control.help}</span> : null}
    </label>
  );
}

/**
 * One network count.
 *
 * 🔴 The bounds are shown as `min`/`max` hints but the field is **not clamped**, on
 * purpose. Decision 4's whole point is that the refusal *teaches*: typing 0 into
 * "Distribution centers" is how a planner reaches the sentence explaining that a
 * warehouse-less network scores 68,565.25 at 92.01% fill because the optimizer has
 * no per-node capacity. A control that silently snapped 0 back to 1 would hide the
 * most valuable thing this iteration measured.
 */
function NetworkCount({
  setting,
  value,
  onChange,
}: {
  setting: SettingSpec;
  value: string;
  onChange: (raw: string) => void;
}) {
  return (
    <label className="block text-xs text-[#4d5c51]" data-testid={`network-${setting.key}`}>
      <span className="block font-medium text-ink">{setting.label}</span>
      <input
        className="control mt-0.5"
        type="number"
        inputMode="numeric"
        value={value}
        min={setting.minimum}
        max={setting.maximum}
        step={1}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="mt-0.5 block text-[10px] leading-4 text-[#6b7a70]">
        {setting.minimum}–{setting.maximum}
      </span>
    </label>
  );
}

/** One Advanced-tier setting, carrying its own honesty label when it has one. */
function AdvancedControl({
  setting,
  value,
  onChange,
}: {
  setting: SettingSpec;
  value: string;
  onChange: (raw: string) => void;
}) {
  return (
    <label className="block text-xs text-[#4d5c51]" data-testid={`setting-${setting.key}`}>
      <span className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[11px]">{setting.key}</span>
        {setting.reaches_optimizer ? null : (
          <span
            className="shrink-0 text-[10px] font-semibold uppercase text-[#7a6a3a]"
            data-testid={`reach-${setting.key}`}
          >
            no effect on the result
          </span>
        )}
        {/* A network count reached through Advanced must carry the same caveat it
            carries in the Network group, or Advanced becomes the dishonest path. */}
        {setting.comparable_to_baseline === false ? (
          <span
            className="shrink-0 text-[10px] font-semibold uppercase text-[#7a6a3a]"
            data-testid={`not-comparable-${setting.key}`}
          >
            resizes the problem
          </span>
        ) : null}
      </span>
      {setting.choices?.length ? (
        <select className="control mt-0.5" value={value} onChange={(event) => onChange(event.target.value)}>
          {setting.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      ) : (
        <input
          className="control mt-0.5"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          inputMode={setting.kind === "str" || setting.kind === "range2" ? "text" : "decimal"}
        />
      )}
    </label>
  );
}
