/**
 * Level 3: click-to-expand detail, with a per-table CSV download.
 *
 * Uses a real <button> with aria-expanded rather than a styled div, so the whole
 * disclosure layer is keyboard reachable — a demo shown on someone else's laptop
 * should not require a mouse.
 *
 * The download link goes through the same authenticated proxy as everything else;
 * nginx injects the key server-side, so no credential reaches the browser.
 */

import { ChevronDown, ChevronRight, Download } from "lucide-react";
import { useId, useState } from "react";

import { datasetTableUrl } from "../lib/api";

export default function Expander({
  label,
  scenario,
  table,
  tableLabel,
  defaultOpen = false,
  children,
}: {
  label: string;
  scenario?: string;
  table?: string;
  tableLabel?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className="border-t border-line pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={panelId}
          className="inline-flex items-center gap-2 rounded-md px-1 py-1 text-sm font-semibold text-[#2f6f4e] transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
        >
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {open ? `Hide ${label}` : `Show ${label}`}
        </button>
        {scenario && table ? (
          <a
            href={datasetTableUrl(scenario, table)}
            download
            className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-[#536258] transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
          >
            <Download className="h-3.5 w-3.5" />
            Download {tableLabel ?? table}.csv
          </a>
        ) : null}
      </div>
      <div id={panelId} hidden={!open} className="mt-3">
        {open ? children : null}
      </div>
    </div>
  );
}
