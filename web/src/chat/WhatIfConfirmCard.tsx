/**
 * The confirm-before-run card (Iteration 5 decision 6).
 *
 * Nothing runs until the button here is clicked. That is enforced by the API too —
 * `POST /chat/whatif` with `confirmed: false` returns this card and runs nothing —
 * so a misparsed question cannot burn GPU in front of a customer.
 *
 * The card states the system's reading back in the planner's own words, what it
 * would touch, and — the part that matters most on this dataset — whether the
 * perturbation can reach the optimizer at all. A window that misses the single
 * period at which lane capacity is read is a measured no-op, and saying so *before*
 * the run is the difference between an honest answer and a confident zero.
 */

import { AlertTriangle, Loader2, Play, X } from "lucide-react";

import { count, periodRange } from "../lib/datasetFormat";
import type { ConfirmationCard } from "../lib/types";
import BetaChip from "./BetaChip";

export type StageEvent = { stage: string; status: string };

const STAGE_LABELS: Record<string, string> = {
  cache: "cached result",
  base_forecast: "forecast (base)",
  base_optimize: "optimize (base)",
  perturb: "apply perturbation",
  whatif_forecast: "forecast (what-if)",
  whatif_optimize: "optimize (what-if)",
};

function footprint(card: ConfirmationCard): string {
  const impact = card.impact;
  if (card.perturbation.kind === "demand_multiplier") {
    return `${count(impact.demand_rows_affected)} demand rows across ${count(impact.series_affected)} series`;
  }
  const types = Object.entries(impact.lane_types_affected)
    .map(([type, n]) => `${n} ${type.replace(/_/g, " ")}`)
    .join(", ");
  return `${count(impact.lanes_affected_count)} lane${impact.lanes_affected_count === 1 ? "" : "s"}${types ? ` (${types})` : ""}`;
}

export default function WhatIfConfirmCard({
  card,
  status,
  stages,
  error,
  busy = false,
  onRun,
  onDismiss,
}: {
  card: ConfirmationCard;
  status: "pending" | "running" | "done" | "dismissed";
  stages: StageEvent[];
  error?: string;
  /** Something else is already in flight; one run at a time keeps the caches sane. */
  busy?: boolean;
  onRun: () => void;
  onDismiss: () => void;
}) {
  const unreachable = !card.impact.reaches_optimizer;
  return (
    <li>
      <section
        className="rounded-md border-2 border-dashed border-violet-400 bg-violet-50/60"
        aria-label="What-if confirmation"
      >
        <div
          className="h-2 rounded-t-[3px]"
          style={{
            backgroundImage:
              "repeating-linear-gradient(45deg, #c4b5fd 0 8px, #ede9fe 8px 16px)",
          }}
        />
        <div className="px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-800">
              What-if · confirm before running
            </span>
            <BetaChip />
          </div>

          <p className="mt-2 text-sm font-semibold leading-6 text-ink">{card.reading}</p>

          <dl className="mt-2 grid gap-1 text-[11px] leading-relaxed text-[#4d5c51]">
            <div className="flex gap-1.5">
              <dt className="font-semibold">Touches</dt>
              <dd>{footprint(card)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="font-semibold">Periods</dt>
              <dd>
                {periodRange(card.perturbation.from_period, card.perturbation.to_period, "period")} of this
                scenario
              </dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="font-semibold">Estimate</dt>
              <dd title={card.estimate_basis}>~{card.estimated_seconds}s · {card.estimate_basis}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="font-semibold">Fixed</dt>
              <dd>
                seed {card.perturbation.seed} · PPO {card.ppo_included ? "included" : "excluded"} · nothing else
                changed
              </dd>
            </div>
          </dl>

          {card.warnings.map((warning) => (
            <div
              key={warning}
              className="mt-2 flex items-start gap-2 rounded-md border border-[#f4c47a] bg-[#fff8eb] px-2.5 py-2 text-xs leading-snug text-warn"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{warning}</span>
            </div>
          ))}

          {status === "pending" ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={onRun}
                disabled={busy}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-violet-700 px-3 text-xs font-semibold text-white transition hover:bg-violet-800 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                <Play className="h-3.5 w-3.5" />
                {unreachable ? "Run it anyway" : "Run it on the optimizer"}
              </button>
              <button
                type="button"
                onClick={onDismiss}
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-white px-3 text-xs font-medium text-[#536258] transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
              >
                <X className="h-3.5 w-3.5" />
                Not what I meant
              </button>
            </div>
          ) : null}

          {status === "dismissed" ? (
            <p className="mt-3 text-[11px] font-medium text-[#6c786d]">
              Dismissed — nothing was run. Rephrase the question and I&rsquo;ll read it again.
            </p>
          ) : null}

          {status === "running" ? (
            <div className="mt-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-violet-800">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Running on the real optimizer…
              </div>
              <ul className="mt-1.5 grid gap-0.5 text-[11px] text-[#4d5c51]">
                {stages.map((event) => (
                  <li key={`${event.stage}-${event.status}`}>
                    {event.status === "complete" || event.status === "hit" ? "✓" : "…"}{" "}
                    {STAGE_LABELS[event.stage] ?? event.stage}
                    {event.status === "hit" ? " (already computed)" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {error ? (
            <p className="mt-3 text-[11px] font-medium text-bad">The run failed: {error}</p>
          ) : null}
        </div>
      </section>
    </li>
  );
}
