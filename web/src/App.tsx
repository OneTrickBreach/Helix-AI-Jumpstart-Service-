import { AlertTriangle, CheckCircle2, Cpu, DatabaseZap, Loader2, Play, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fetchScenarios, scenarioStreamUrl } from "./lib/api";
import { buildMetricComparisons, winnerMessage } from "./lib/deltas";
import type { MetricComparison } from "./lib/deltas";
import type { Benchmark, Rationale, ScenarioComparison, ScenarioSummary } from "./lib/types";

const STAGES = ["ingest", "forecast", "baseline", "classical", "ppo", "rag", "done"];

type StageState = {
  stage: string;
  status: string;
  message?: string;
};

export default function App() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [scenario, setScenario] = useState("");
  const [horizon, setHorizon] = useState(8);
  const [ppoTimesteps, setPpoTimesteps] = useState(128);
  const [topK, setTopK] = useState(5);
  const [stages, setStages] = useState<StageState[]>([]);
  const [result, setResult] = useState<ScenarioComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const streamRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetchScenarios()
      .then((items) => {
        setScenarios(items);
        setScenario(items[0]?.scenario ?? "");
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    return () => streamRef.current?.close();
  }, []);

  const selectedScenario = scenarios.find((item) => item.scenario === scenario);

  function runScenario() {
    if (!scenario || running) {
      return;
    }
    streamRef.current?.close();
    setRunning(true);
    setError(null);
    setResult(null);
    setStages([]);
    const stream = new EventSource(scenarioStreamUrl({ scenario, horizon, ppoTimesteps, topK }));
    streamRef.current = stream;

    stream.addEventListener("stage", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as StageState;
      setStages((current) => [...current.filter((item) => item.stage !== data.stage), data]);
    });
    stream.addEventListener("done", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as { data: ScenarioComparison };
      setResult(payload.data);
      setStages((current) => [...current.filter((item) => item.stage !== "done"), { stage: "done", status: "complete" }]);
      setRunning(false);
      stream.close();
    });
    stream.addEventListener("error", (event) => {
      const messageEvent = event as MessageEvent;
      if (messageEvent.data) {
        const payload = JSON.parse(messageEvent.data) as { detail?: string };
        setError(payload.detail ?? "Scenario run failed");
        setRunning(false);
        stream.close();
      }
    });
    stream.onerror = () => {
      setError("Scenario stream disconnected");
      setRunning(false);
      stream.close();
    };
  }

  return (
    <main className="min-h-screen bg-field text-ink">
      <section className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#587060]">Helix AI Jumpstart MVP</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-normal sm:text-4xl">Scenario Comparison</h1>
              {selectedScenario?.description ? (
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#4d5c51]">{selectedScenario.description}</p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={runScenario}
              disabled={running || !scenario}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-ink px-5 text-sm font-semibold text-white shadow-soft transition hover:bg-[#263329] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(220px,1.2fr)_repeat(3,minmax(140px,0.5fr))]">
            <label className="control-label">
              Scenario
              <select value={scenario} onChange={(event) => setScenario(event.target.value)} className="control">
                {scenarios.map((item) => (
                  <option value={item.scenario} key={item.scenario}>
                    {item.scenario}
                  </option>
                ))}
              </select>
            </label>
            <NumberControl label="Horizon" min={1} max={52} value={horizon} onChange={setHorizon} />
            <NumberControl label="PPO timesteps" min={16} max={4096} value={ppoTimesteps} onChange={setPpoTimesteps} />
            <NumberControl label="Top K" min={1} max={10} value={topK} onChange={setTopK} />
          </div>
        </div>
      </section>

      <div className="mx-auto grid max-w-7xl gap-5 px-4 py-5 sm:px-6 lg:px-8">
        {error ? <ErrorBanner message={error} /> : null}
        <StageStepper stages={stages} running={running} />
        {result ? <ResultsView benchmark={result.benchmark} rationale={result.rationale} /> : <EmptyState running={running} />}
      </div>
    </main>
  );
}

function NumberControl({ label, min, max, value, onChange }: { label: string; min: number; max: number; value: number; onChange: (value: number) => void }) {
  return (
    <label className="control-label">
      {label}
      <input
        className="control"
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 border border-[#f3b7af] bg-[#fff5f3] px-4 py-3 text-sm text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function StageStepper({ stages, running }: { stages: StageState[]; running: boolean }) {
  const statusByStage = new Map(stages.map((stage) => [stage.stage, stage.status]));
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {STAGES.map((stage) => {
          const status = statusByStage.get(stage);
          const complete = status === "complete";
          const inProgress = status === "running";
          const touched = complete || inProgress;
          return (
            <div key={stage} className={`flex min-h-14 items-center gap-2 border px-3 py-2 text-sm ${touched ? "border-[#b8cfbd] bg-[#f3faf4]" : "border-line bg-white"}`}>
              {complete ? <CheckCircle2 className="h-4 w-4 text-good" /> : inProgress || running ? <Loader2 className="h-4 w-4 animate-spin text-[#6c786d]" /> : <span className="h-4 w-4 rounded-full border border-line" />}
              <span className="font-medium capitalize">{stage}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EmptyState({ running }: { running: boolean }) {
  return (
    <section className="grid min-h-72 place-items-center border border-dashed border-line bg-white text-center text-sm text-[#5d6b62]">
      <div className="flex flex-col items-center gap-3">
        {running ? <Loader2 className="h-7 w-7 animate-spin" /> : <DatabaseZap className="h-7 w-7" />}
        <p>{running ? "Running on-device comparison..." : "Select a scenario and run the comparison."}</p>
      </div>
    </section>
  );
}

function ResultsView({ benchmark, rationale }: { benchmark: Benchmark; rationale: Rationale }) {
  const metrics = useMemo(() => buildMetricComparisons(benchmark), [benchmark]);
  const winner = benchmark.winner.approach;
  return (
    <div className="grid gap-5">
      <section className="grid gap-4 bg-white px-4 py-4 shadow-soft">
        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-xl font-semibold">Before vs After</h2>
            <p className="text-sm text-[#536258]">{winnerMessage(benchmark)}</p>
          </div>
          <div className="text-sm font-medium text-[#536258]">PPO outcome: {benchmark.ppo_outcome}</div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard metric={metric} key={metric.key} />
          ))}
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <ApproachTable benchmark={benchmark} />
        <ResourcePanel benchmark={benchmark} />
      </section>

      <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <ApproachChart benchmark={benchmark} />
        <RationalePanel rationale={rationale} />
      </section>
    </div>
  );
}

function MetricCard({ metric }: { metric: MetricComparison }) {
  const toneClass = metric.tone === "good" ? "text-good" : metric.tone === "bad" ? "text-bad" : "text-[#5d6b62]";
  const arrow = metric.arrow === "up" ? "▲" : metric.arrow === "down" ? "▼" : "■";
  return (
    <article className="min-h-40 border border-line bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">{metric.label}</h3>
        <span className={`text-sm font-bold ${toneClass}`}>{arrow} {metric.deltaLabel}</span>
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-3">
        <div>
          <dt className="text-xs uppercase tracking-[0.12em] text-[#6d796f]">Before</dt>
          <dd className="mt-1 text-lg font-semibold">{metric.displayBefore}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-[0.12em] text-[#6d796f]">After</dt>
          <dd className="mt-1 text-lg font-semibold">{metric.displayAfter}</dd>
        </div>
      </dl>
    </article>
  );
}

function ApproachTable({ benchmark }: { benchmark: Benchmark }) {
  const winner = benchmark.winner.approach;
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <h2 className="text-lg font-semibold">Approaches</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead className="text-left text-xs uppercase tracking-[0.12em] text-[#667268]">
            <tr>
              <th className="border-b border-line py-2">Approach</th>
              <th className="border-b border-line py-2 text-right">Objective</th>
              <th className="border-b border-line py-2 text-right">Cost</th>
              <th className="border-b border-line py-2 text-right">Fill</th>
              <th className="border-b border-line py-2 text-right">Days</th>
              <th className="border-b border-line py-2 text-right">Latency</th>
            </tr>
          </thead>
          <tbody>
            {benchmark.comparison.map((row) => (
              <tr key={row.approach} className={row.approach === winner ? "bg-[#f3faf4]" : ""}>
                <td className="border-b border-line py-3 font-semibold capitalize">
                  {row.approach}
                  {row.approach === winner ? <span className="ml-2 text-xs text-good">winner</span> : null}
                </td>
                <td className="border-b border-line py-3 text-right">{row.objective.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                <td className="border-b border-line py-3 text-right">{money(row.total_cost)}</td>
                <td className="border-b border-line py-3 text-right">{(row.fill_rate * 100).toFixed(2)}%</td>
                <td className="border-b border-line py-3 text-right">{row.days_of_inventory.toFixed(2)}</td>
                <td className="border-b border-line py-3 text-right">{row.latency_seconds.toFixed(3)}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResourcePanel({ benchmark }: { benchmark: Benchmark }) {
  const winner = benchmark.winner.approach;
  const profile = benchmark.resource_profiles[winner] ?? {};
  const items = [
    ["API process peak RSS", `${number(profile.peak_process_rss_mb)} MB`],
    ["Allocation-rate proxy", `${number(profile.allocation_rate_gbps_proxy, 4)} GB/s (not DRAM BW)`],
    ["Solve latency", `${number(profile.wall_clock_seconds, 3)} s`],
    [
      "GPU util",
      profile.gpu_utilization_percent == null
        ? profile.gpu_metrics_status ?? "unavailable"
        : `${number(profile.gpu_utilization_percent)}%`,
    ],
    ["CPU util", `${number(profile.cpu_utilization_percent)}%`],
  ];
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <div className="flex items-center gap-2">
        <Cpu className="h-5 w-5" />
        <h2 className="text-lg font-semibold">On-device</h2>
      </div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        {items.map(([label, value]) => (
          <div className="border border-line px-3 py-3" key={label}>
            <dt className="text-xs uppercase tracking-[0.12em] text-[#667268]">{label}</dt>
            <dd className="mt-1 text-xl font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ApproachChart({ benchmark }: { benchmark: Benchmark }) {
  const data = benchmark.comparison.map((row) => ({
    approach: row.approach,
    objective: Number(row.objective.toFixed(2)),
  }));
  return (
    <section className="h-80 bg-white px-4 py-4 shadow-soft">
      <h2 className="text-lg font-semibold">Objective</h2>
      <ResponsiveContainer width="100%" height="82%">
        <BarChart data={data} margin={{ top: 20, right: 14, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#d7ddcf" vertical={false} />
          <XAxis dataKey="approach" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={72} />
          <Tooltip formatter={(value) => Number(value).toLocaleString()} />
          <Bar dataKey="objective" fill="#2f6f4e" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function RationalePanel({ rationale }: { rationale: Rationale }) {
  const flags = rationale.prompt_injection_flags ?? [];
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert className="h-5 w-5 text-warn" />
        <h2 className="text-lg font-semibold">ADVISORY ONLY</h2>
        <span className="border border-line px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[#667268]">
          {rationale.selected_approach}
        </span>
      </div>
      {flags.length ? (
        <div className="mt-4 border border-[#f4c47a] bg-[#fff8eb] px-3 py-3 text-sm text-warn">
          {flags.map((flag, index) => (
            <div key={`${flag.source_id}-${flag.pattern}-${index}`}>
              {flag.title ?? flag.source_id}: {flag.pattern}
            </div>
          ))}
        </div>
      ) : null}
      <p className="mt-4 text-sm leading-6 text-[#334139]">{rationale.advisory_rationale}</p>
      {rationale.citations?.length ? (
        <div className="mt-4 grid gap-2">
          {rationale.citations.map((citation, index) => (
            <div key={`${citation.source_id}-${index}`} className="border border-line px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">{citation.citation_id ?? `C${index + 1}`} · {citation.title}</span>
                {citation.prompt_injection_flagged ? <span className="text-xs font-semibold text-bad">flagged</span> : null}
              </div>
              <p className="mt-1 line-clamp-2 text-[#536258]">{citation.text_excerpt}</p>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function number(value: number | undefined, digits = 2): string {
  return Number(value ?? 0).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}
