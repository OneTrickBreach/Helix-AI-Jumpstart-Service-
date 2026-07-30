/**
 * "Know Your Data" — the dataset transparency view.
 *
 * Iteration 4, Phase 3: navigation, layout and the Level-1 hero. Phase 4 replaces
 * the tier strip with a real network map and adds charts, the BOM tree, full tables
 * and CSV download.
 *
 * Three levels of progressive disclosure, and the split is deliberate:
 *   Level 1 (no scrolling): provenance badge, one sentence, six tiles, the network.
 *                           A viewer who reads only this understands the dataset.
 *   Level 2 (scroll):       section cards, one plain-English line each.
 *   Level 3 (Phase 4):      full tables, exact values, CSV download.
 *
 * Every number rendered here comes from the API payload. Nothing is computed in the
 * browser, and no text on this screen is LLM-generated.
 */

import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  DatabaseZap,
  Factory,
  Loader2,
  PackageSearch,
  ShieldCheck,
  Truck,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { DatasetNotGenerated, fetchDatasetOverview } from "./lib/api";
import {
  count,
  humanizeKey,
  percent,
  pluralLabel,
  pluralize,
  showingLabel,
  units,
} from "./lib/datasetFormat";
import type { DatasetOverview, ScenarioSummary } from "./lib/types";

type Props = {
  scenario: string;
  scenarios: ScenarioSummary[];
  onScenarioChange: (scenario: string) => void;
  onBack: () => void;
};

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: DatasetOverview }
  | { status: "empty"; message: string }
  | { status: "error"; message: string };

export default function DatasetView({
  scenario,
  scenarios,
  onScenarioChange,
  onBack,
}: Props) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback((name: string) => {
    if (!name) return;
    let cancelled = false;
    setState({ status: "loading" });
    fetchDatasetOverview(name)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // A 409 is not a failure — it means "nothing generated yet", which the
        // viewer can fix. Anything else is a real error and says so.
        if (err instanceof DatasetNotGenerated) {
          setState({ status: "empty", message: err.message });
        } else {
          setState({
            status: "error",
            message: err instanceof Error ? err.message : String(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(scenario), [scenario, load]);

  const provenance = state.status === "ready" ? state.data.provenance : null;

  return (
    <main className="min-h-screen bg-field text-ink">
      <StickyHeader
        scenario={scenario}
        scenarios={scenarios}
        onScenarioChange={onScenarioChange}
        onBack={onBack}
        badgeText={provenance?.badge_text}
      />

      <div className="mx-auto grid max-w-7xl gap-5 px-4 py-5 sm:px-6 lg:px-8">
        {state.status === "loading" ? <LoadingState scenario={scenario} /> : null}
        {state.status === "empty" ? <EmptyState message={state.message} /> : null}
        {state.status === "error" ? (
          <ErrorState message={state.message} onRetry={() => load(scenario)} />
        ) : null}
        {state.status === "ready" ? <DatasetBody data={state.data} /> : null}
      </div>
    </main>
  );
}

/**
 * The provenance badge lives here so it survives scrolling. A page this legible
 * invites the viewer to assume the data is real; it is seeded synthetic data, and
 * that must never be more than a glance away.
 */
function StickyHeader({
  scenario,
  scenarios,
  onScenarioChange,
  onBack,
  badgeText,
}: {
  scenario: string;
  scenarios: ScenarioSummary[];
  onScenarioChange: (scenario: string) => void;
  onBack: () => void;
  badgeText?: string;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-[#536258] transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to results
          </button>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#587060]">
              Know your data
            </p>
            <h1 className="text-lg font-semibold leading-tight sm:text-xl">
              The dataset behind this plan
            </h1>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <ProvenanceBadge text={badgeText} compact />
          <label className="control-label">
            Scenario
            <select
              value={scenario}
              onChange={(event) => onScenarioChange(event.target.value)}
              className="control"
            >
              {/* An unknown scenario from the URL stays visible and selected rather
                  than leaving the control blank while an error is shown below. */}
              {scenarios.every((item) => item.scenario !== scenario) && scenario ? (
                <option value={scenario}>{scenario} (not found)</option>
              ) : null}
              {scenarios.map((item) => (
                <option key={item.scenario} value={item.scenario}>
                  {item.scenario}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </header>
  );
}

export function ProvenanceBadge({ text, compact = false }: { text?: string; compact?: boolean }) {
  // Amber, not green: this is a caveat, not a reassurance.
  const label = text ?? "Synthetic demo dataset · generated on-device · not customer data";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-md border border-[#f4c47a] bg-[#fff8eb] font-semibold text-warn ${
        compact ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm"
      }`}
      title="This is seeded synthetic data generated on this device. It is not customer data."
    >
      <ShieldCheck className={compact ? "h-4 w-4 shrink-0" : "h-5 w-5 shrink-0"} />
      {label}
    </span>
  );
}

function LoadingState({ scenario }: { scenario: string }) {
  return (
    <section className="grid min-h-72 place-items-center border border-dashed border-line bg-white text-center text-sm text-[#5d6b62]">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-7 w-7 animate-spin" />
        <p>Reading the dataset for {scenario} from disk…</p>
      </div>
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <section className="grid min-h-72 place-items-center border border-dashed border-line bg-white px-6 text-center">
      <div className="flex max-w-xl flex-col items-center gap-3">
        <DatabaseZap className="h-8 w-8 text-[#5d6b62]" />
        <h2 className="text-lg font-semibold">No data generated yet</h2>
        <p className="text-sm leading-6 text-[#536258]">{message}</p>
        <code className="rounded-md border border-line bg-field px-3 py-2 text-sm font-semibold">
          make demo-data
        </code>
      </div>
    </section>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="grid min-h-72 place-items-center border border-[#f3b7af] bg-[#fff5f3] px-6 text-center">
      <div className="flex max-w-xl flex-col items-center gap-3">
        <AlertTriangle className="h-8 w-8 text-bad" />
        <h2 className="text-lg font-semibold text-bad">Could not load the dataset</h2>
        <p className="text-sm leading-6 text-[#7a3b33]">{message}</p>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 items-center rounded-md bg-ink px-4 text-sm font-semibold text-white transition hover:bg-[#263329]"
        >
          Try again
        </button>
      </div>
    </section>
  );
}

function DatasetBody({ data }: { data: DatasetOverview }) {
  return (
    <div className="grid gap-5">
      {/* ---------------- Level 1: everything above the fold ---------------- */}
      <HeroSummary data={data} />
      <GlanceTiles data={data} />
      <NetworkStrip data={data} />

      {/* ---------------- Level 2: scroll ---------------- */}
      <ScenarioCard data={data} />
      <div className="grid gap-5 lg:grid-cols-2">
        <ProductsCard data={data} />
        <DemandCard data={data} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <LanesCard data={data} />
        <CapacityCard data={data} />
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <CostsCard data={data} />
        <ServiceTargetsCard data={data} />
        <InventoryCard data={data} />
      </div>
      <PipelineCard data={data} />
      <ProvenanceFooter data={data} />
    </div>
  );
}

function HeroSummary({ data }: { data: DatasetOverview }) {
  return (
    <section className="border-2 border-[#b8cfbd] bg-white px-5 py-5 shadow-soft">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#587060]">
        {data.provenance.scenario.replace(/-/g, " ")}
      </p>
      <p className="mt-2 text-lg font-semibold leading-8 sm:text-xl sm:leading-9">
        {data.narrative.one_sentence_summary}
      </p>
      <p className="mt-3 text-sm leading-6 text-[#4d5c51]">
        {data.narrative.scenario_sentence}
      </p>
    </section>
  );
}

function GlanceTiles({ data }: { data: DatasetOverview }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {data.at_a_glance.map((tile) => (
        <article
          key={tile.key}
          className="border border-line bg-white px-4 py-3"
          title={tile.plain_english_note}
        >
          <p className="text-xs font-bold uppercase tracking-[0.1em] text-[#667268]">
            {tile.label}
          </p>
          <p className="mt-1 text-2xl font-bold leading-tight">
            {typeof tile.value === "number" ? count(tile.value) : (tile.value ?? "—")}
          </p>
          <p className="mt-0.5 text-xs text-[#6d796f]">{tile.unit ?? " "}</p>
        </article>
      ))}
    </section>
  );
}

/**
 * Placeholder for Phase 4's network map: the real tiers and counts, drawn as a
 * left-to-right chain. Real data, simple rendering — not a mock.
 */
function NetworkStrip({ data }: { data: DatasetOverview }) {
  const icons: Record<string, typeof Factory> = {
    supplier: Boxes,
    plant: Factory,
    distribution_center: PackageSearch,
    customer: Truck,
  };
  const disrupted = data.lanes.disrupted_lane_count;
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">How the network is laid out</h2>
        <p className="text-sm text-[#536258]">
          {pluralize(data.lanes.lane_count, "shipping lane")} connect them
          {disrupted > 0 ? ` · ${pluralize(disrupted, "lane")} disrupted in this scenario` : ""}
        </p>
      </div>
      <div className="mt-4 flex flex-wrap items-stretch gap-2">
        {data.network.tiers.map((tier, index) => {
          const Icon = icons[tier.tier] ?? Boxes;
          return (
            <div key={tier.tier} className="flex flex-1 items-stretch gap-2">
              <div className="flex min-w-36 flex-1 flex-col items-center justify-center gap-1 border border-line bg-field px-3 py-4 text-center">
                <Icon className="h-6 w-6 text-[#2f6f4e]" />
                <p className="text-2xl font-bold leading-none">{count(tier.count)}</p>
                <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[#667268]">
                  {pluralLabel(tier.plain_label, tier.count)}
                </p>
              </div>
              {index < data.network.tiers.length - 1 ? (
                <div className="flex items-center text-xl text-[#9fb0a4]" aria-hidden="true">
                  →
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Card({
  title,
  line,
  children,
}: {
  title: string;
  line?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <h2 className="text-lg font-semibold">{title}</h2>
      {line ? <p className="mt-1 text-sm leading-6 text-[#536258]">{line}</p> : null}
      {children ? <div className="mt-3">{children}</div> : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-line px-3 py-2">
      <dt className="text-xs uppercase tracking-[0.1em] text-[#667268]">{label}</dt>
      <dd className="mt-1 text-base font-semibold">{value}</dd>
    </div>
  );
}

function ScenarioCard({ data }: { data: DatasetOverview }) {
  const diff = data.scenario_diff;
  return (
    <Card
      title="What makes this scenario different"
      line={
        diff.is_baseline
          ? data.narrative.scenario_sentence
          : `Compared with the "${diff.vs}" scenario.`
      }
    >
      {diff.changes.length ? (
        <ul className="grid gap-2">
          {diff.changes.map((change, index) => (
            <li
              key={`${change.kind}-${index}`}
              className="border-l-4 border-[#f4c47a] bg-[#fff8eb] px-3 py-2 text-sm leading-6"
            >
              {change.plain_english}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-[#536258]">
          {diff.is_baseline
            ? "No disruption is applied to this scenario."
            : "No structural change was found against the baseline dataset."}
        </p>
      )}
      {!diff.is_baseline && diff.config_changes.length ? (
        <p className="mt-3 text-sm text-[#536258]">
          {pluralize(diff.config_changes.length, "other setting")} also{" "}
          {diff.config_changes.length === 1 ? "differs" : "differ"} from the baseline —
          expand the tables below to compare exact values.
        </p>
      ) : null}
    </Card>
  );
}

function ProductsCard({ data }: { data: DatasetOverview }) {
  const products = data.products;
  return (
    <Card
      title="Products"
      line={`${pluralize(products.sku_count, "product")} in total, built up through ${pluralize(
        products.bom_max_tier_depth,
        "level",
      )} of parts.`}
    >
      <dl className="grid gap-2 sm:grid-cols-3">
        {Object.entries(products.sku_count_by_type).map(([type, value]) => (
          <Stat
            key={type}
            label={products.sku_type_labels[type] ?? humanizeKey(type)}
            value={count(value)}
          />
        ))}
      </dl>
      <p className="mt-3 text-xs text-[#6d796f]">
        {pluralize(products.bom_row_count, "recipe line")} across{" "}
        {pluralize(products.bom_parent_count, "parent product")}.
      </p>
    </Card>
  );
}

function DemandCard({ data }: { data: DatasetOverview }) {
  const demand = data.demand;
  return (
    <Card
      title="Demand history"
      line={`${pluralize(demand.series_count, "demand series", "demand series")} over ${pluralize(
        demand.history_periods,
        demand.period_unit,
      )}, ${count(demand.total_rows)} rows in all.`}
    >
      <dl className="grid gap-2 sm:grid-cols-3">
        <Stat label="Total units ordered" value={units(demand.total_units_finished_goods)} />
        <Stat
          label="Demand shock window"
          value={
            demand.shock_window
              ? `${demand.period_unit}s ${demand.shock_window.from_period}–${demand.shock_window.to_period}`
              : "none"
          }
        />
        <Stat label="Forecast method" value={demand.lumpy_series_count ? "mixed" : "AutoETS"} />
      </dl>
      <p className="mt-3 text-sm leading-6 text-[#536258]">
        {data.narrative.forecast_method_sentence}
      </p>
    </Card>
  );
}

function LanesCard({ data }: { data: DatasetOverview }) {
  const lanes = data.lanes;
  return (
    <Card
      title="Shipping lanes"
      line={`${pluralize(lanes.lane_count, "lane")} carry goods between locations, tracked for ${pluralize(
        lanes.periods_covered,
        "period",
      )}.`}
    >
      <dl className="grid gap-2 sm:grid-cols-3">
        {Object.entries(lanes.count_by_type).map(([type, value]) => (
          <Stat
            key={type}
            label={lanes.lane_type_labels[type] ?? humanizeKey(type)}
            value={count(value)}
          />
        ))}
      </dl>
      <p className="mt-3 text-xs text-[#6d796f]">
        Delivery takes {lanes.lead_time_days_range.min}–{lanes.lead_time_days_range.max} days
        depending on the lane. {showingLabel(lanes.table_showing)}.
      </p>
    </Card>
  );
}

function CapacityCard({ data }: { data: DatasetOverview }) {
  const capacity = data.capacity;
  return (
    <Card
      title="Making capacity"
      line={`${pluralize(
        capacity.production_line_count,
        "production line",
      )} can build up to ${units(capacity.total_throughput_units_per_period)} each period.`}
    >
      <dl className="grid gap-2 sm:grid-cols-2">
        {capacity.storage_by_node_type
          .filter((row) => row.storage_capacity_units > 0)
          .map((row) => (
            <Stat
              key={row.node_type}
              label={`${row.plain_label} storage`}
              value={units(row.storage_capacity_units)}
            />
          ))}
      </dl>
    </Card>
  );
}

function CostsCard({ data }: { data: DatasetOverview }) {
  const costs = data.costs;
  return (
    <Card
      title="Where the money is"
      line="The cost settings fed into the optimizer — these are inputs, not results."
    >
      {/* Never let input costs be mistaken for the measured costs on the results screen. */}
      <p className="mb-3 border-l-4 border-[#9fb0a4] bg-field px-3 py-2 text-xs font-semibold uppercase tracking-[0.08em] text-[#4d5c51]">
        Input parameters — not measured results
      </p>
      <dl className="grid gap-2">
        <Stat
          label="Transport cost per unit"
          value={`$${costs.transport.cost_per_unit_min} – $${costs.transport.cost_per_unit_max}`}
        />
        {costs.by_sku_type.map((entry) => {
          const holding = entry.parameters.find((p) => p.parameter === "unit_holding_cost");
          return holding ? (
            <Stat
              key={entry.sku_type}
              label={`${entry.plain_label} holding cost`}
              value={`$${holding.min} – $${holding.max}`}
            />
          ) : null;
        })}
      </dl>
    </Card>
  );
}

function ServiceTargetsCard({ data }: { data: DatasetOverview }) {
  const targets = data.service_targets;
  return (
    <Card
      title="Service promises"
      line={`${pluralize(targets.customer_count, "customer")} with promised service levels on ${pluralize(
        targets.sku_count,
        "product",
      )}.`}
    >
      <dl className="grid gap-2">
        <Stat
          label="Orders to fill on time"
          value={
            targets.fill_rate_target_range.min === targets.fill_rate_target_range.max
              ? percent(targets.fill_rate_target_range.min, 1)
              : `${percent(targets.fill_rate_target_range.min, 1)} – ${percent(
                  targets.fill_rate_target_range.max,
                  1,
                )}`
          }
        />
        {Object.entries(targets.criticality_tiers).map(([tier, value]) => (
          <Stat key={tier} label={`${humanizeKey(tier)} tier`} value={count(value)} />
        ))}
      </dl>
    </Card>
  );
}

function InventoryCard({ data }: { data: DatasetOverview }) {
  const inventory = data.initial_inventory;
  return (
    <Card
      title="Stock on day one"
      line={`${units(inventory.total_on_hand_units)} on hand before the plan starts.`}
    >
      <dl className="grid gap-2">
        <Stat label="Already shipped, in transit" value={units(inventory.total_in_transit_units)} />
        <Stat
          label="Days of cover"
          value={
            inventory.days_of_cover_estimate === null
              ? "—"
              : `${inventory.days_of_cover_estimate} days`
          }
        />
      </dl>
      <p className="mt-3 text-xs leading-5 text-[#6d796f]">{inventory.basis}</p>
    </Card>
  );
}

function PipelineCard({ data }: { data: DatasetOverview }) {
  return (
    <Card title="How this data becomes the plan" line={data.narrative.pipeline_sentence}>
      <div className="grid gap-2 sm:grid-cols-3">
        {Object.entries(data.pipeline_link.stage_inputs).map(([stage, tables]) => (
          <div key={stage} className="border border-line px-3 py-2">
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-[#667268]">
              {humanizeKey(stage)}
            </p>
            <p className="mt-1 text-sm leading-6">
              {tables.map((table) => humanizeKey(table)).join(", ")}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-[#6d796f]">{data.pipeline_link.note}</p>
    </Card>
  );
}

function ProvenanceFooter({ data }: { data: DatasetOverview }) {
  const provenance = data.provenance;
  return (
    <section className="border border-line bg-white px-4 py-4">
      <ProvenanceBadge text={provenance.badge_text} />
      <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Seed" value={String(provenance.effective_seed ?? "—")} />
        <Stat label="Generated by" value={provenance.generator ?? "—"} />
        <Stat label="Generated at (UTC)" value={provenance.generated_at_utc ?? "—"} />
        <Stat label="Stored at" value={provenance.data_location} />
      </dl>
      <p className="mt-3 text-xs leading-5 text-[#6d796f]">
        {data.narrative.provenance_sentence} {provenance.byte_identical_claim} Regenerate with{" "}
        <code className="font-semibold">{provenance.regeneration_command}</code>.
      </p>
    </section>
  );
}
