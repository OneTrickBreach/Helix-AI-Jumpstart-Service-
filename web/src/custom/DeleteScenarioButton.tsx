/**
 * Delete the custom scenario you are currently looking at.
 *
 * The panel has a saved list with a Delete beside each entry, but that is the
 * wrong place to *only* have it: to delete the scenario on screen you had to
 * switch the dropdown away from it first. A reviewer looking straight at
 * `custom-test` reported, correctly, that there was no delete option.
 *
 * Two-step by design. Deleting removes the config, the generated data, the
 * recorded artifact and the vector-store collection — it is not undoable, so it
 * does not happen on a single stray click. An inline confirm is used rather than
 * `window.confirm` so the wording can name what goes.
 */

import { Loader2, Trash2 } from "lucide-react";
import { useState } from "react";

import { deleteCustomScenario } from "../lib/customApi";

const CUSTOM_PREFIX = "custom-";

export default function DeleteScenarioButton({
  scenario,
  onDeleted,
  compact = false,
}: {
  scenario: string;
  /** Called after a successful delete, so the caller can pick a new selection. */
  onDeleted: (deleted: string) => void;
  compact?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!scenario.startsWith(CUSTOM_PREFIX)) return null;

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteCustomScenario(scenario.slice(CUSTOM_PREFIX.length));
      setConfirming(false);
      onDeleted(scenario);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const height = compact ? "h-10" : "h-11";

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className={`inline-flex ${height} items-center justify-center gap-2 rounded-md border border-[#d8b4a0] bg-white px-4 text-sm font-medium text-[#8a4b2a] transition hover:bg-[#fdf6f1]`}
        title={`Delete ${scenario} — its config, data and recorded result`}
        data-testid="delete-selected-scenario"
      >
        <Trash2 className="h-4 w-4" />
        Delete
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2" data-testid="delete-confirm">
      <span className="text-sm text-[#8a4b2a]">
        {error ?? `Delete ${scenario} and its data?`}
      </span>
      <button
        type="button"
        onClick={remove}
        disabled={busy}
        className={`inline-flex ${height} items-center justify-center gap-2 rounded-md bg-[#8a4b2a] px-3 text-sm font-semibold text-white transition hover:bg-[#73401f] disabled:opacity-60`}
        data-testid="delete-confirm-yes"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        Yes, delete
      </button>
      <button
        type="button"
        onClick={() => {
          setConfirming(false);
          setError(null);
        }}
        disabled={busy}
        className={`inline-flex ${height} items-center justify-center rounded-md border border-line bg-white px-3 text-sm font-medium text-[#536258] transition hover:bg-field disabled:opacity-60`}
        data-testid="delete-confirm-no"
      >
        Cancel
      </button>
    </div>
  );
}
