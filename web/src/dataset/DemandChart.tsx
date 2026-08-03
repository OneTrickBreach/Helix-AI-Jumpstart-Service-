/**
 * Demand over time, with the scenario's shock window shaded and labelled.
 *
 * Recharts is already in the bundle. The shock window is drawn as a ReferenceArea
 * with a visible label, so "when does this scenario bite" is answered by the picture
 * rather than only by the prose above it.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { count, percent } from "../lib/datasetFormat";
import type { DatasetDemand, DatasetProducts } from "../lib/types";

export default function DemandChart({
  demand,
  products,
}: {
  demand: DatasetDemand;
  products: DatasetProducts;
}) {
  const data = demand.units_per_period;
  const shock = demand.shock_window;
  const unit = demand.period_unit;

  return (
    <div className="grid gap-4">
      <div>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm font-semibold">
            Units ordered each {unit}, across every customer and product
          </p>
          {shock ? (
            <p className="text-xs font-semibold text-warn">
              Shaded: demand runs at {shock.multipliers.map((m) => `${m}x`).join(", ")} in{" "}
              {unit}s {shock.from_period}–{shock.to_period}
            </p>
          ) : (
            <p className="text-xs text-[#6d796f]">No demand shock in this scenario</p>
          )}
        </div>
        <div className="mt-2 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid stroke="#d7ddcf" vertical={false} />
              <XAxis
                dataKey="period"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 12 }}
                label={{
                  value: `${unit} number`,
                  position: "insideBottom",
                  offset: -2,
                  fontSize: 11,
                }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={64}
                tick={{ fontSize: 12 }}
                tickFormatter={(value: number) => count(value)}
              />
              <Tooltip
                formatter={(value: number) => [`${count(value)} units`, "Ordered"]}
                labelFormatter={(label) => `${unit} ${label}`}
              />
              {shock ? (
                <ReferenceArea
                  x1={shock.from_period}
                  x2={shock.to_period}
                  fill="#a15c07"
                  fillOpacity={0.14}
                  stroke="#a15c07"
                  strokeOpacity={0.5}
                  label={{ value: "demand shock", position: "insideTop", fontSize: 11, fill: "#8a4f06" }}
                />
              ) : null}
              <Area
                type="monotone"
                dataKey="units"
                stroke="#2f6f4e"
                strokeWidth={2}
                fill="#2f6f4e"
                fillOpacity={0.16}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <p className="text-sm font-semibold">Which products drive that demand</p>
        <ul className="mt-2 grid gap-1.5">
          {products.top_by_demand_share.slice(0, 6).map((row) => (
            <li key={row.sku_id} className="flex items-center gap-3 text-sm">
              <span className="w-20 shrink-0 font-medium">{row.sku_id}</span>
              <span className="h-3 flex-1 overflow-hidden rounded-sm bg-[#eef1e9]">
                <span
                  className="block h-full rounded-sm bg-[#2f6f4e]"
                  style={{ width: `${Math.max(1, row.share_of_finished_good_demand * 100)}%` }}
                />
              </span>
              <span className="w-28 shrink-0 text-right tabular-nums text-[#536258]">
                {percent(row.share_of_finished_good_demand, 1)} · {count(row.units)}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-[#6d796f]">
          {products.top_by_demand_share_showing.note}, ranked by total units ordered.
        </p>
      </div>
    </div>
  );
}
