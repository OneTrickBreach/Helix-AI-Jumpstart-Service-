/**
 * The what-if result card.
 *
 * The hard requirement this card exists to meet: **a screenshot of it cannot be
 * mistaken for a benchmark result.** So it looks deliberately unlike the results
 * screen — hatched violet header, dashed border, a WHAT-IF chip, a BETA chip, both
 * columns labelled, and a footer that says in words that this is a synthetic
 * perturbation and not the recorded benchmark.
 *
 * Every number here came from `run_head_to_head` running twice on this device: once
 * on the scenario as generated, once on an in-memory perturbed copy. Nothing was
 * written to disk and no language model touched any figure.
 */

import { AlertTriangle, Copy } from "lucide-react";

import { count, multiplier, periodRange } from "../lib/datasetFormat";
import { timingLabel, whatIfChips, whatIfHeadline, whatIfMetricRows } from "../lib/chatDisplay";
import type { WhatIfResult } from "../lib/types";
import BetaChip from "./BetaChip";
import ProvenanceChips from "./ProvenanceChips";

const DIRECTION_CLASS = {
  worse: "text-bad",
  better: "text-good",
  none: "text-[#6c786d]",
} as const;

function diffSentence(result: WhatIfResult): string {
  const diff = result.diff;
  const applied =
    diff.demand_multiplier_applied !== undefined
      ? `multiplier ${multiplier(diff.demand_multiplier_applied)}`
      : `capacity ${multiplier(diff.capacity_multiplier_applied)}`;
  return (
    `${count(diff.rows_changed)} of ${count(diff.rows_in_window)} rows in ${diff.table}.${diff.column} rewritten in memory ` +
    `(${applied}): ${count(diff.units_before)} units → ${count(diff.units_after)} units.`
  );
}

export default function WhatIfResultCard({ result }: { result: WhatIfResult }) {
  const rows = whatIfMetricRows(result);
  const unreachable = !result.impact.reaches_optimizer;
  return (
    <li>
      <section
        className="rounded-md border-2 border-dashed border-violet-500 bg-white"
        aria-label="What-if result (synthetic perturbation)"
        data-what-if="true"
      >
        <div
          className="h-2 rounded-t-[3px]"
          style={{
            backgroundImage:
              "repeating-linear-gradient(45deg, #a78bfa 0 8px, #ddd6fe 8px 16px)",
          }}
        />
        <div className="px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-800">
              What-if result · synthetic perturbation
            </span>
            <BetaChip />
          </div>

          <p className="mt-2 text-sm font-semibold leading-6 text-ink">{result.reading}</p>
          <p className={`mt-1 text-sm font-bold ${unreachable ? "text-warn" : "text-ink"}`}>
            {whatIfHeadline(result)}
          </p>

          {unreachable ? (
            <div className="mt-2 flex items-start gap-2 rounded-md border-2 border-warn/70 bg-[#fff8eb] px-2.5 py-2 text-xs leading-snug text-warn">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                <strong>Do not read this as resilience.</strong> {result.impact.why}
              </span>
            </div>
          ) : null}

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[320px] border-collapse text-xs">
              {/* Visible, not sr-only: it is the line that keeps a screenshot cropped
                  tightly around the table from reading as a benchmark result. */}
              <caption className="pb-1.5 text-left text-[10px] leading-snug text-violet-800">
                What-if versus base, both computed by the on-device optimizer on seeded synthetic data
              </caption>
              <thead className="text-left text-[10px] uppercase tracking-[0.1em] text-[#667268]">
                <tr>
                  <th className="border-b border-line py-1.5">Metric</th>
                  <th className="border-b border-line py-1.5 text-right">Base (as generated)</th>
                  <th className="border-b border-line py-1.5 text-right">What-if</th>
                  <th className="border-b border-line py-1.5 text-right">Change</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key}>
                    <td className="whitespace-nowrap border-b border-line py-1.5 pr-2 font-medium">{row.label}</td>
                    <td className="border-b border-line py-1.5 text-right tabular-nums">{row.before}</td>
                    <td className="border-b border-line py-1.5 text-right tabular-nums">{row.after}</td>
                    <td
                      className={`border-b border-line py-1.5 text-right tabular-nums font-semibold ${DIRECTION_CLASS[row.direction]}`}
                    >
                      {row.change}
                      {row.direction === "none" ? "" : ` ${row.direction}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-2 text-[11px] leading-relaxed text-[#4d5c51]">
            Winner both sides: {result.base.winner} → {result.what_if.winner}. PPO{" "}
            {result.ppo_included ? "included" : `excluded (${result.what_if.ppo_outcome})`}.
          </p>

          <div className="mt-2 rounded-md border border-line bg-field px-2.5 py-2 text-[11px] leading-relaxed text-[#4d5c51]">
            <p className="font-semibold text-ink">What was changed</p>
            <p className="mt-0.5">{diffSentence(result)}</p>
            {result.diff.lane_ids?.length ? (
              <p className="mt-0.5">
                Lanes: {result.diff.lane_ids.slice(0, 6).join(", ")}
                {result.diff.lane_ids.length > 6 ? ` +${result.diff.lane_ids.length - 6} more` : ""}
              </p>
            ) : null}
            <p className="mt-0.5">
              Window: {periodRange(result.perturbation.from_period, result.perturbation.to_period, "period")}
              {result.impact.capacity_read_period !== null
                ? ` · optimizer reads lane capacity at period ${result.impact.capacity_read_period} only`
                : ""}
            </p>
          </div>

          <ProvenanceChips chips={whatIfChips(result)} />

          {result.warnings.map((warning) => (
            <p key={warning} className="mt-1.5 text-[10px] leading-relaxed text-[#6c786d]">
              ⚠ {warning}
            </p>
          ))}

          <p className="mt-2 flex flex-wrap items-center gap-1 border-t border-line pt-2 text-[10px] leading-relaxed text-[#7c887e]">
            <Copy className="h-3 w-3" />
            <span>
              seed {result.seed} · horizon {result.horizon} · {timingLabel(result)} ·{" "}
              {result.numeric_values_source}
            </span>
          </p>
          <p className="mt-1 text-[10px] font-semibold leading-relaxed text-violet-800">
            This is a what-if, not the recorded benchmark result for this scenario. Do not quote it as one.
          </p>
        </div>
      </section>
    </li>
  );
}
