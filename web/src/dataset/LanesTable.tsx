/**
 * Lanes, with a per-period disruption strip so capacity drops read as a timeline.
 *
 * Lead time is spelled out in days rather than left as a bare number, and the
 * disruption strip marks affected periods with both colour and a dot pattern so it
 * survives a projector.
 */

import { count, days, humanizeKey, money, multiplier } from "../lib/datasetFormat";
import type { DatasetLanes } from "../lib/types";

export default function LanesTable({
  lanes,
  periodUnit,
}: {
  lanes: DatasetLanes;
  periodUnit: string;
}) {
  const disruptedById = new Map(lanes.disruption_timeline.map((entry) => [entry.lane_id, entry]));

  return (
    <div className="grid gap-4">
      {lanes.disruption_timeline.length ? (
        <div>
          <p className="text-sm font-semibold">When the disrupted lanes are affected</p>
          <div className="mt-2 grid gap-2">
            {lanes.disruption_timeline.map((entry) => (
              <div key={entry.lane_id} className="grid gap-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
                  <span className="font-semibold">
                    {entry.lane_id} · {entry.from} → {entry.to} ({humanizeKey(entry.sku_scope)})
                  </span>
                  <span className="text-warn">
                    capacity {multiplier(entry.min_capacity_multiplier)} · lead time{" "}
                    {multiplier(entry.max_lead_time_multiplier)} · {periodUnit}s{" "}
                    {entry.from_period}–{entry.to_period}
                  </span>
                </div>
                <PeriodStrip
                  totalPeriods={lanes.periods_covered}
                  from={entry.from_period}
                  to={entry.to_period}
                  label={`${entry.lane_id} disrupted from ${periodUnit} ${entry.from_period} to ${entry.to_period} of ${lanes.periods_covered}`}
                />
              </div>
            ))}
          </div>
          <p className="mt-1 text-xs text-[#6d796f]">
            Each strip is the full {count(lanes.periods_covered)} {periodUnit}s; the amber block is
            when that lane is restricted.
          </p>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <caption className="sr-only">
            Shipping lanes with delivery time, cost per unit and capacity
          </caption>
          <thead className="text-left text-xs uppercase tracking-[0.1em] text-[#667268]">
            <tr>
              <th scope="col" className="border-b border-line py-2">Lane</th>
              <th scope="col" className="border-b border-line py-2">Route</th>
              <th scope="col" className="border-b border-line py-2">Carries</th>
              <th scope="col" className="border-b border-line py-2 text-right">Delivery time</th>
              <th scope="col" className="border-b border-line py-2 text-right">Cost per unit</th>
              <th scope="col" className="border-b border-line py-2 text-right">Capacity / period</th>
            </tr>
          </thead>
          <tbody>
            {lanes.table.map((row) => {
              const disrupted = disruptedById.has(row.lane_id);
              return (
                <tr key={row.lane_id} className={disrupted ? "bg-[#fff8eb]" : ""}>
                  <td className="border-b border-line py-2 font-medium">
                    {row.lane_id}
                    {disrupted ? (
                      <span className="ml-2 rounded-sm border border-[#f4c47a] px-1.5 py-0.5 text-[10px] font-semibold uppercase text-warn">
                        disrupted
                      </span>
                    ) : null}
                  </td>
                  <td className="border-b border-line py-2">
                    {row.from} → {row.to}
                    <span className="block text-xs text-[#6d796f]">{row.plain_label}</span>
                  </td>
                  <td className="border-b border-line py-2">{humanizeKey(row.sku_scope)}</td>
                  <td className="border-b border-line py-2 text-right tabular-nums">
                    {days(row.lead_time_days)}
                  </td>
                  <td className="border-b border-line py-2 text-right tabular-nums">
                    {money(row.cost_per_unit, 2)}
                  </td>
                  <td className="border-b border-line py-2 text-right tabular-nums">
                    {count(row.capacity_units_per_period)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[#6d796f]">
        {lanes.table_showing.note}, ranked by {lanes.table_showing.ranked_by}.
      </p>
    </div>
  );
}

function PeriodStrip({
  totalPeriods,
  from,
  to,
  label,
}: {
  totalPeriods: number;
  from: number;
  to: number;
  label: string;
}) {
  const startPct = ((from - 1) / Math.max(1, totalPeriods)) * 100;
  const widthPct = ((to - from + 1) / Math.max(1, totalPeriods)) * 100;
  return (
    <div
      className="relative h-3 w-full overflow-hidden rounded-sm border border-line bg-[#eef1e9]"
      role="img"
      aria-label={label}
      title={label}
    >
      <div
        className="absolute inset-y-0 bg-[#a15c07]"
        style={{
          left: `${startPct}%`,
          width: `${widthPct}%`,
          // Pattern as well as colour, so the block is legible without colour.
          backgroundImage:
            "repeating-linear-gradient(45deg, rgba(255,255,255,0.45) 0 3px, transparent 3px 6px)",
        }}
      />
    </div>
  );
}
