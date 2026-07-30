/**
 * The network map — the hero visual of the dataset view.
 *
 * Iteration 4, Phase 4. Plain SVG, no graph library: the bundle is already over
 * Vite's 500 kB warning and one diagram does not justify another dependency.
 *
 * Left-to-right tiers (suppliers → factories → distribution centers → customers),
 * every real node drawn, every real lane drawn. Lanes disrupted by this scenario are
 * marked in amber, thickened, and dashed — three cues, not colour alone, so the
 * disruption survives a projector and colour-blind viewers.
 *
 * Every coordinate is layout; every label is a value from the API payload.
 */

import { useState } from "react";

import { humanizeKey, multiplier, pluralLabel } from "../lib/datasetFormat";
import type { DatasetLanes, DatasetNetwork } from "../lib/types";

const TIER_ORDER = ["supplier", "plant", "distribution_center", "customer"];

const NODE_WIDTH = 132;
const NODE_HEIGHT = 24;
const NODE_GAP = 6;
const COLUMN_GAP = 200;
const TOP_PADDING = 34;
const BOTTOM_PADDING = 12;
const MAX_HEIGHT = 250;

/**
 * Rows drawn per tier before the rest collapse into a "+N more" block.
 *
 * Level 1 has to stay above the fold on a 1440x900 laptop, and stress-large has 24
 * customers. Shrinking 24 rows to fit would make the labels unreadable, which
 * defeats the point, so the tier is capped and the remainder is stated honestly.
 */
const MAX_ROWS_PER_TIER = 9;

type HoverLane = {
  laneId: string;
  label: string;
  detail: string;
  disrupted: boolean;
  x: number;
  y: number;
};

export default function NetworkMap({
  network,
  lanes,
  periodUnit,
}: {
  network: DatasetNetwork;
  lanes: DatasetLanes;
  periodUnit: string;
}) {
  const [hover, setHover] = useState<HoverLane | null>(null);

  const tiers = TIER_ORDER.filter((tier) => (network.nodes_by_type[tier] ?? 0) > 0);

  // Nodes touching a disruption are never hidden: the overlay is the whole reason
  // this map earns its place, so it must survive the row cap.
  const disruptionNodes = new Set(
    lanes.disruption_timeline.flatMap((entry) => [entry.from, entry.to]),
  );
  const hiddenByTier = new Map<string, number>();
  const nodesByTier = new Map(
    tiers.map((tier) => {
      const all = network.node_list.filter((node) => node.node_type === tier);
      if (all.length <= MAX_ROWS_PER_TIER) {
        hiddenByTier.set(tier, 0);
        return [tier, all] as const;
      }
      const pinned = all.filter((node) => disruptionNodes.has(node.node_id));
      const rest = all.filter((node) => !disruptionNodes.has(node.node_id));
      const shown = [...pinned, ...rest].slice(0, MAX_ROWS_PER_TIER - 1);
      hiddenByTier.set(tier, all.length - shown.length);
      // Keep the original ordering so the column does not look shuffled.
      const order = new Map(all.map((node, index) => [node.node_id, index]));
      shown.sort((a, b) => (order.get(a.node_id) ?? 0) - (order.get(b.node_id) ?? 0));
      return [tier, shown] as const;
    }),
  );

  const rowsForTier = (tier: string) =>
    (nodesByTier.get(tier)?.length ?? 0) + ((hiddenByTier.get(tier) ?? 0) > 0 ? 1 : 0);
  const tallest = Math.max(1, ...tiers.map((tier) => rowsForTier(tier)));
  const rowStride = NODE_HEIGHT + NODE_GAP;
  const naturalHeight = TOP_PADDING + tallest * rowStride + BOTTOM_PADDING;
  const height = Math.min(naturalHeight, MAX_HEIGHT);
  // Squeeze rows rather than clip nodes when a tier is tall (stress-large: 24 customers).
  const scale = naturalHeight > MAX_HEIGHT ? (MAX_HEIGHT - TOP_PADDING - BOTTOM_PADDING) / (tallest * rowStride) : 1;
  const width = tiers.length * NODE_WIDTH + (tiers.length - 1) * COLUMN_GAP;

  const columnX = (index: number) => index * (NODE_WIDTH + COLUMN_GAP);
  const positions = new Map<string, { x: number; y: number; cx: number; cy: number }>();
  tiers.forEach((tier, tierIndex) => {
    const nodes = nodesByTier.get(tier) ?? [];
    const columnHeight = rowsForTier(tier) * rowStride * scale;
    const offset = TOP_PADDING + ((height - TOP_PADDING - BOTTOM_PADDING) - columnHeight) / 2;
    nodes.forEach((node, rowIndex) => {
      const x = columnX(tierIndex);
      const y = offset + rowIndex * rowStride * scale;
      positions.set(node.node_id, {
        x,
        y,
        cx: x + NODE_WIDTH / 2,
        cy: y + (NODE_HEIGHT * scale) / 2,
      });
    });
  });

  const disruptedById = new Map(lanes.disruption_timeline.map((entry) => [entry.lane_id, entry]));
  const drawableEdges = network.edges.filter(
    (edge) => positions.has(edge.from) && positions.has(edge.to),
  );
  const nodeHeight = NODE_HEIGHT * scale;
  const fontScale = scale < 0.7 ? 8 : 10;
  const hiddenNodeTotal = [...hiddenByTier.values()].reduce((sum, n) => sum + n, 0);

  return (
    <div className="relative">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 pb-2 text-xs text-[#536258]">
        <Legend swatch={<span className="inline-block h-0.5 w-6 bg-[#9fb0a4]" />} label="Shipping lane" />
        <Legend
          swatch={
            <span
              className="inline-block h-1 w-6"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(90deg,#a15c07 0 4px,transparent 4px 7px)",
              }}
            />
          }
          label="Disrupted in this scenario"
        />
        <span>Hover a lane for its delivery time and cost.</span>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label={`Network map: ${tiers
            .map((tier) => `${network.nodes_by_type[tier]} ${tier.replace(/_/g, " ")}`)
            .join(", ")}, connected by ${lanes.lane_count} shipping lanes${
            lanes.disrupted_lane_count
              ? `, of which ${lanes.disrupted_lane_count} are disrupted in this scenario`
              : ""
          }.`}
          className="min-w-[760px]"
        >
          <g>
            {tiers.map((tier, index) => {
              const label = network.tiers.find((entry) => entry.tier === tier);
              const countForTier = network.nodes_by_type[tier] ?? 0;
              return (
                <text
                  key={`head-${tier}`}
                  x={columnX(index) + NODE_WIDTH / 2}
                  y={20}
                  textAnchor="middle"
                  className="fill-[#3c4a41] text-[13px] font-semibold"
                >
                  {countForTier}{" "}
                  {pluralLabel(label?.plain_label ?? tier.replace(/_/g, " "), countForTier)}
                </text>
              );
            })}
          </g>

          {/* Lanes first so nodes sit on top of them. */}
          <g>
            {drawableEdges.map((edge) => {
              const from = positions.get(edge.from)!;
              const to = positions.get(edge.to)!;
              const startX = from.x + NODE_WIDTH;
              const endX = to.x;
              const midX = (startX + endX) / 2;
              const disruption = disruptedById.get(edge.lane_id);
              const isDisrupted = Boolean(disruption);
              const isHovered = hover?.laneId === edge.lane_id;
              return (
                <path
                  key={edge.lane_id}
                  d={`M ${startX} ${from.cy} C ${midX} ${from.cy}, ${midX} ${to.cy}, ${endX} ${to.cy}`}
                  fill="none"
                  stroke={isDisrupted ? "#a15c07" : "#9fb0a4"}
                  strokeWidth={isDisrupted ? 2.4 : isHovered ? 2 : 1}
                  strokeDasharray={isDisrupted ? "5 3" : undefined}
                  strokeOpacity={isDisrupted ? 0.95 : isHovered ? 0.9 : 0.42}
                  onMouseEnter={() =>
                    setHover({
                      laneId: edge.lane_id,
                      label: `${edge.from} → ${edge.to}`,
                      detail: disruption
                        ? `${humanizeKey(edge.sku_scope)} · ${edge.lead_time_days} days · $${edge.cost_per_unit}/unit · capacity ${multiplier(
                            disruption.min_capacity_multiplier,
                          )} for ${periodUnit}s ${disruption.from_period}–${disruption.to_period}`
                        : `${humanizeKey(edge.sku_scope)} · ${edge.lead_time_days} days · $${edge.cost_per_unit}/unit · capacity ${edge.capacity_units_per_period.toLocaleString("en-US")}/period`,
                      disrupted: isDisrupted,
                      x: midX,
                      y: (from.cy + to.cy) / 2,
                    })
                  }
                  onMouseLeave={() => setHover(null)}
                >
                  <title>{`${edge.lane_id}: ${edge.from} to ${edge.to}, ${edge.lead_time_days} days`}</title>
                </path>
              );
            })}
          </g>

          <g>
            {tiers.map((tier, tierIndex) =>
              (nodesByTier.get(tier) ?? []).map((node) => {
                const pos = positions.get(node.node_id)!;
                const touchesDisruption = lanes.disruption_timeline.some(
                  (entry) => entry.from === node.node_id || entry.to === node.node_id,
                );
                return (
                  <g key={node.node_id}>
                    <rect
                      x={pos.x}
                      y={pos.y}
                      width={NODE_WIDTH}
                      height={nodeHeight}
                      rx={4}
                      fill={touchesDisruption ? "#fff8eb" : "#ffffff"}
                      stroke={touchesDisruption ? "#a15c07" : "#d7ddcf"}
                      strokeWidth={touchesDisruption ? 1.8 : 1}
                    />
                    <text
                      x={pos.x + 8}
                      y={pos.y + nodeHeight / 2 + 3}
                      className="fill-[#17201a] font-medium"
                      style={{ fontSize: fontScale }}
                    >
                      {node.node_id}
                    </text>
                    {scale > 0.75 ? (
                      <text
                        x={pos.x + NODE_WIDTH - 8}
                        y={pos.y + nodeHeight / 2 + 3}
                        textAnchor="end"
                        className="fill-[#7c8a80]"
                        style={{ fontSize: fontScale - 1 }}
                      >
                        {node.region}
                      </text>
                    ) : null}
                    <title>{`${node.name} (${node.node_id}), ${node.region}`}</title>
                  </g>
                );
              }),
            )}
            {tiers.map((tier, tierIndex) => {
              const hidden = hiddenByTier.get(tier) ?? 0;
              if (!hidden) return null;
              const shownCount = nodesByTier.get(tier)?.length ?? 0;
              const columnHeight = rowsForTier(tier) * rowStride * scale;
              const offset =
                TOP_PADDING + ((height - TOP_PADDING - BOTTOM_PADDING) - columnHeight) / 2;
              const y = offset + shownCount * rowStride * scale;
              return (
                <g key={`more-${tier}`}>
                  <rect
                    x={columnX(tierIndex)}
                    y={y}
                    width={NODE_WIDTH}
                    height={nodeHeight}
                    rx={4}
                    fill="#f6f7f3"
                    stroke="#c3ccbb"
                    strokeDasharray="4 3"
                  />
                  <text
                    x={columnX(tierIndex) + NODE_WIDTH / 2}
                    y={y + nodeHeight / 2 + 3}
                    textAnchor="middle"
                    className="fill-[#6d796f] font-medium"
                    style={{ fontSize: fontScale }}
                  >
                    +{hidden} more
                  </text>
                  <title>{`${hidden} further locations, listed in the table below`}</title>
                </g>
              );
            })}
            {tiers.map((_, index) =>
              index < tiers.length - 1 ? (
                <text
                  key={`arrow-${index}`}
                  x={columnX(index) + NODE_WIDTH + COLUMN_GAP / 2}
                  y={20}
                  textAnchor="middle"
                  className="fill-[#9fb0a4] text-[13px]"
                  aria-hidden="true"
                >
                  →
                </text>
              ) : null,
            )}
          </g>
        </svg>
      </div>

      {hover ? (
        <div
          className={`pointer-events-none absolute z-10 max-w-xs rounded-md border px-3 py-2 text-xs shadow-soft ${
            hover.disrupted
              ? "border-[#f4c47a] bg-[#fff8eb] text-[#6b4405]"
              : "border-line bg-white text-[#334139]"
          }`}
          style={{ left: `${Math.min(70, (hover.x / width) * 100)}%`, top: 8 }}
        >
          <p className="font-semibold">
            {hover.laneId} · {hover.label}
          </p>
          <p className="mt-0.5">{hover.detail}</p>
        </div>
      ) : null}

      {drawableEdges.length < lanes.lane_count || hiddenNodeTotal > 0 ? (
        <p className="pt-2 text-xs text-[#6d796f]">
          Drawing {drawableEdges.length} of {lanes.lane_count} lanes
          {hiddenNodeTotal > 0
            ? ` — ${hiddenNodeTotal} more locations are folded into the "+N more" blocks to keep the map readable`
            : ""}
          . Every location and lane is in the tables below.
        </p>
      ) : null}
    </div>
  );
}

function Legend({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      {swatch}
      {label}
    </span>
  );
}
