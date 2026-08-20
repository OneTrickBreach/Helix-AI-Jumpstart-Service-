import { AlertTriangle, CheckCircle2, Cpu, DatabaseZap, FileClock, Loader2, MessageSquare, Play, ShieldAlert, Table2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import BetaChip from "./chat/BetaChip";
import ChatPanel from "./chat/ChatPanel";
import CustomScenarioPanel from "./custom/CustomScenarioPanel";
import DatasetView from "./DatasetView";
import { fetchScenarios, scenarioStreamUrl } from "./lib/api";
import { buildMetricComparisons, winnerMessage } from "./lib/deltas";
import type { MetricComparison } from "./lib/deltas";
import type { Benchmark, Rationale, ScenarioComparison, ScenarioSummary } from "./lib/types";

const DEMO_REPLAY_URL = "/demo-replay.json";

/** The fifth dropdown entry. A sentinel, not a scenario the API knows about. */
const BUILD_YOUR_OWN = "__custom__";
const CUSTOM_PREFIX = "custom-";

const STAGES = ["ingest", "forecast", "baseline", "classical", "ppo", "rag", "done"];

type StageState = {
  stage: string;
  status: string;
  message?: string;
};

type View = "results" | "dataset";

/**
 * URL-param view switching instead of a router.
 *
 * One extra view does not justify a router dependency, a larger bundle, or nginx
 * SPA-rewrite changes — and it matches the existing `?replay=true` pattern. The URL
 * stays bookmarkable so `?view=dataset&scenario=X` can be shared directly. Revisit
 * if a third view appears.
 */
function readViewFromUrl(): { view: View; scenario: string | null; replay: boolean; chat: boolean } {
  const params = new URLSearchParams(window.location.search);
  return {
    view: params.get("view") === "dataset" ? "dataset" : "results",
    scenario: params.get("scenario"),
    replay: params.get("replay") === "true",
    chat: params.get("chat") === "true",
  };
}

function writeViewToUrl(view: View, scenario: string) {
  const params = new URLSearchParams(window.location.search);
  if (view === "dataset") {
    params.set("view", "dataset");
    if (scenario) params.set("scenario", scenario);
  } else {
    params.delete("view");
    params.delete("scenario");
  }
  const query = params.toString();
  window.history.pushState({}, "", query ? `?${query}` : window.location.pathname);
}

/** `?chat=true` so a chat-open walkthrough can be linked to directly. */
function writeChatToUrl(open: boolean) {
  const params = new URLSearchParams(window.location.search);
  if (open) params.set("chat", "true");
  else params.delete("chat");
  const query = params.toString();
  window.history.pushState({}, "", query ? `?${query}` : window.location.pathname);
}

/** True when the page was opened in recorded-demo mode. */
function isReplayMode(): boolean {
  return readViewFromUrl().replay;
}

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
  const [view, setView] = useState<View>(() => readViewFromUrl().view);
  const [chatOpen, setChatOpen] = useState<boolean>(() => readViewFromUrl().chat);
  const [customOpen, setCustomOpen] = useState(false);
  const streamRef = useRef<EventSource | null>(null);

  useEffect(() => {
    fetchScenarios()
      .then((items) => {
        setScenarios(items);
        // A scenario named in the URL wins, so a shared dataset link opens on the
        // scenario it was shared for rather than snapping back to the first one.
        //
        // If the URL names a scenario that does not exist, keep the bad name rather
        // than quietly substituting a real one: this whole view exists to tell you
        // precisely which data you are looking at, so showing baseline under a URL
        // that says something else would be the one unforgivable bug here. The API
        // returns 404 and the view surfaces an honest error.
        const { view: urlView, scenario: requested } = readViewFromUrl();
        const known = items.find((item) => item.scenario === requested);
        if (known) {
          setScenario(known.scenario);
        } else if (urlView === "dataset" && requested) {
          setScenario(requested);
        } else {
          setScenario(items[0]?.scenario ?? "");
        }
      })
      .catch((err: unknown) => {
        // Replay exists for the case where the backend is unavailable. Surfacing
        // "Scenario list failed" next to a working recorded run would break the
        // GPU-free walkthrough with an error the viewer cannot act on, so in replay
        // mode the missing list is expected rather than an error.
        if (isReplayMode()) return;
        setError(err instanceof Error ? err.message : String(err));
      });
  }, []);

  // Keep the back/forward buttons working without pulling in a router.
  useEffect(() => {
    const onPopState = () => {
      const state = readViewFromUrl();
      setView(state.view);
      setChatOpen(state.chat);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  /**
   * Re-read the scenario list after a custom scenario is saved or deleted.
   *
   * `GET /scenarios` unions the configs on disk with the generated data
   * directories, so a saved custom scenario appears here with no new discovery
   * code — the same list the four recorded scenarios come from.
   */
  const refreshScenarios = useCallback(() => {
    fetchScenarios()
      .then(setScenarios)
      .catch(() => undefined);
  }, []);

  const toggleChat = useCallback((open: boolean) => {
    setChatOpen(open);
    writeChatToUrl(open);
  }, []);

  const openDataset = useCallback(() => {
    setView("dataset");
    writeViewToUrl("dataset", scenario);
  }, [scenario]);

  const openResults = useCallback(() => {
    setView("results");
    writeViewToUrl("results", scenario);
  }, [scenario]);

  const changeDatasetScenario = useCallback((next: string) => {
    setScenario(next);
    writeViewToUrl("dataset", next);
  }, []);

  useEffect(() => {
    return () => streamRef.current?.close();
  }, []);

  const selectedScenario = scenarios.find((item) => item.scenario === scenario);
  // Grouped in the dropdown so a custom result can never be mistaken for one of
  // the four recorded ones (guardrail 2). The `custom-` prefix does the work.
  const recordedScenarios = scenarios.filter((item) => !item.scenario.startsWith(CUSTOM_PREFIX));
  const customScenarios = scenarios.filter((item) => item.scenario.startsWith(CUSTOM_PREFIX));

  const loadReplay = useCallback(async () => {
    if (running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setStages([]);
    try {
      const response = await fetch(DEMO_REPLAY_URL);
      if (!response.ok) throw new Error(`Replay file not found (${response.status})`);
      const payload = (await response.json()) as ScenarioComparison;
      // Simulate stages one by one for visual effect
      for (const stage of STAGES.filter((s) => s !== "done")) {
        setStages((prev) => [...prev.filter((item) => item.stage !== stage), { stage, status: "running" }]);
        await new Promise((resolve) => setTimeout(resolve, 300));
        setStages((prev) => [...prev.filter((item) => item.stage !== stage), { stage, status: "complete" }]);
      }
      setStages((prev) => [...prev, { stage: "done", status: "complete" }]);
      setResult(payload);
      setScenario(payload.benchmark.scenario);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [running]);

  // Auto-replay when ?replay=true is in the URL (for recorded fallback demo)
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("replay") === "true") {
      loadReplay();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function runScenario(target?: string) {
    const runFor = target ?? scenario;
    if (!runFor || running) {
      return;
    }
    if (target && target !== scenario) {
      // Saving and running in one action: select it too, so the header, the
      // dataset button and the chat panel all agree with what just ran.
      setScenario(target);
    }
    streamRef.current?.close();
    setRunning(true);
    setError(null);
    setResult(null);
    setStages([]);
    const stream = new EventSource(
      scenarioStreamUrl({ scenario: runFor, horizon, ppoTimesteps, topK }),
    );
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

  /**
   * The chat panel sits *beside* whichever view is open — it does not replace
   * either, and neither view knows it exists. Closed by default so every Iteration
   * 4 layout guarantee (Level 1 above the fold) holds unchanged unless a viewer
   * deliberately opens it.
   */
  const withChat = (body: JSX.Element) => (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <div className="min-w-0 flex-1">{body}</div>
      {customOpen && !isReplayMode() ? (
        <CustomScenarioPanel
          onClose={() => setCustomOpen(false)}
          onSavedSetChanged={refreshScenarios}
          onRun={(target) => {
            setCustomOpen(false);
            runScenario(target);
          }}
        />
      ) : null}
      {chatOpen ? (
        <ChatPanel scenario={scenario} replay={isReplayMode()} onClose={() => toggleChat(false)} />
      ) : (
        // The floating button is fixed to the bottom-right, which is exactly where
        // the custom panel puts its Save / Save & run bar — it was intercepting
        // those clicks outright. Shift it clear of the panel rather than hiding it:
        // unmounting the chat surface would lose an open transcript, and Ryan
        // parked that feature as-is (decision 12).
        <AskThePlanButton onClick={() => toggleChat(true)} shifted={customOpen} />
      )}
    </div>
  );

  if (view === "dataset") {
    return withChat(
      <DatasetView
        scenario={scenario}
        scenarios={scenarios}
        onScenarioChange={changeDatasetScenario}
        onBack={openResults}
        replay={isReplayMode()}
        // Reachable from this screen too. It is the screen a planner is looking at
        // when they decide they want different conditions — and the one Ryan
        // singled out. Omitted in replay, where every API call is blocked.
        onOpenCustom={isReplayMode() ? undefined : () => setCustomOpen(true)}
        customOpen={customOpen}
      />,
    );
  }

  return withChat(
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
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => runScenario()}
                disabled={running || !scenario}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-ink px-5 text-sm font-semibold text-white shadow-soft transition hover:bg-[#263329] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Run
              </button>
              <button
                type="button"
                onClick={openDataset}
                disabled={!scenario}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line bg-white px-4 text-sm font-medium text-[#536258] transition hover:bg-field disabled:cursor-not-allowed disabled:opacity-60"
                title="See the dataset this plan runs on"
              >
                <Table2 className="h-4 w-4" />
                View the dataset
              </button>
              <button
                type="button"
                onClick={loadReplay}
                disabled={running}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line bg-white px-4 text-sm font-medium text-[#536258] transition hover:bg-field disabled:cursor-not-allowed disabled:opacity-60"
                title="Load a pre-recorded demo run (no live GPU required)"
              >
                <FileClock className="h-4 w-4" />
                Replay
              </button>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(220px,1.2fr)_repeat(3,minmax(140px,0.5fr))]">
            <label className="control-label">
              Scenario
              <select
                value={customOpen ? BUILD_YOUR_OWN : scenario}
                onChange={(event) => {
                  const next = event.target.value;
                  if (next === BUILD_YOUR_OWN) {
                    setCustomOpen(true);
                    return;
                  }
                  setCustomOpen(false);
                  setScenario(next);
                }}
                className="control"
                data-testid="scenario-select"
              >
                <optgroup label="Recorded benchmark scenarios">
                  {recordedScenarios.map((item) => (
                    <option value={item.scenario} key={item.scenario}>
                      {item.scenario}
                    </option>
                  ))}
                </optgroup>
                {customScenarios.length ? (
                  <optgroup label="Your custom scenarios">
                    {customScenarios.map((item) => (
                      <option value={item.scenario} key={item.scenario}>
                        {item.scenario}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {/* Not offered in replay: `?replay=true` is the walkthrough that needs
                    no backend at all, and every /api/ call is blocked. Building a
                    scenario requires the API, so offering the control there would
                    hand a viewer a panel that can only say "Failed to fetch". */}
                {isReplayMode() ? null : <option value={BUILD_YOUR_OWN}>Custom scenario…</option>}
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
        {result ? (
          <>
            {result.benchmark.scenario.startsWith(CUSTOM_PREFIX) ? <CustomResultBanner result={result} /> : null}
            <ResultsView benchmark={result.benchmark} rationale={result.rationale} />
          </>
        ) : (
          <EmptyState running={running} />
        )}
      </div>
    </main>,
  );
}

/**
 * The way into the chat panel, on both views.
 *
 * One control rather than a button per header: `DatasetView` owns its own sticky
 * header and does not need to know the panel exists. The `BETA` chip rides along
 * here too, so the label is visible before the panel is even opened.
 */
/**
 * A custom result must never be quotable as one of the four recorded benchmark
 * results (guardrail 2). The scenario name already carries `custom-`; this states
 * it in words, and repeats the no-op warning if the run carried one — an
 * unchanged objective has to be explained *after* the run as well as before it.
 */
function CustomResultBanner({ result }: { result: ScenarioComparison }) {
  const warning = (result.warnings ?? []).find(
    (item) => item.code === "capacity_window_misses_read_period",
  );
  const settings = result.run_settings;
  return (
    <section className="grid gap-3" data-testid="custom-result-banner">
      <div className="rounded-md border border-[#c8d6cb] bg-[#eef5ef] p-3">
        <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#2f6d4f]">
          Custom scenario · not a recorded benchmark result
        </p>
        <p className="mt-1 text-sm leading-6 text-[#4d5c51]">
          <strong className="font-mono">{result.benchmark.scenario}</strong> was built on this box and
          run on the real pipeline. The four recorded benchmark results are unchanged; do not quote
          this figure as one of them.
          {settings?.excluded.length
            ? ` Excluded from this run: ${settings.excluded.join(", ")}.`
            : ""}
        </p>
      </div>
      {warning ? (
        <div className="rounded-md border border-[#d9b45f] bg-[#fdf7e6] p-3" data-testid="custom-result-noop">
          <p className="flex items-start gap-2 text-sm font-semibold text-[#7a5b12]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            Do not read this as resilience
          </p>
          <p className="mt-1 text-sm leading-6 text-[#6b5a2a]">{warning.message}</p>
        </div>
      ) : null}
    </section>
  );
}

function AskThePlanButton({ onClick, shifted = false }: { onClick: () => void; shifted?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Ask a grounded question about this dataset or this run (beta)"
      className={`fixed bottom-5 z-30 inline-flex h-11 items-center gap-2 rounded-full border border-line bg-white px-4 text-sm font-semibold text-ink shadow-soft transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd] ${
        shifted ? "right-5 lg:right-[31.5rem]" : "right-5"
      }`}
    >
      <MessageSquare className="h-4 w-4 text-[#2f6f4e]" />
      Ask the plan
      <BetaChip />
    </button>
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
  const stateByStage = new Map(stages.map((s) => [s.stage, s]));
  return (
    <section className="bg-white px-4 py-4 shadow-soft">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {STAGES.map((stage) => {
          const s = stateByStage.get(stage);
          const complete = s?.status === "complete";
          const inProgress = s?.status === "running";
          const touched = complete || inProgress;
          return (
            <div key={stage} className={`flex min-h-14 items-center gap-2 border px-3 py-2 text-sm ${touched ? "border-[#b8cfbd] bg-[#f3faf4]" : "border-line bg-white"}`}>
              {complete ? <CheckCircle2 className="h-4 w-4 text-good" /> : inProgress ? <Loader2 className="h-4 w-4 animate-spin text-[#6c786d]" /> : <span className="h-4 w-4 rounded-full border border-line" />}
              <div className="flex flex-col">
                <span className="font-medium capitalize">{stage}</span>
                {inProgress && s?.message ? <span className="text-[10px] leading-tight text-[#6c786d]">{s.message}</span> : null}
              </div>
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

function PlanSummary({ benchmark, rationale }: { benchmark: Benchmark; rationale: Rationale }) {
  const winner = benchmark.winner.approach;
  const before = benchmark.plans.baseline.metrics;
  const after = benchmark.plans[winner]?.metrics ?? before;
  const costDelta = before.total_cost !== 0 ? ((after.total_cost - before.total_cost) / before.total_cost * 100) : 0;
  const costBetter = costDelta < 0;
  const advisory = rationale.advisory_rationale ?? "";
  const shortAdvisory = advisory.replace(/^ADVISORY ONLY:\s*/i, "").slice(0, 280) + (advisory.length > 280 ? "..." : "");
  return (
    <section className="border-2 border-good/30 bg-gradient-to-br from-[#f3faf4] to-white px-5 py-5 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-good">Why this plan</p>
          <h2 className="mt-1 text-2xl font-bold capitalize">{benchmark.scenario.replace(/-/g, " ")}</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-md border border-good/30 bg-white px-3 py-1.5 text-sm font-bold capitalize text-good">
            Winner: {winner}
          </span>
          <span className="rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold text-[#536258]">
            On NVIDIA GB10
          </span>
        </div>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <div className="border border-line bg-white px-4 py-3">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#667268]">Total cost</p>
          <p className="mt-1 text-xl font-bold">{money(before.total_cost)} → {money(after.total_cost)}</p>
          <p className={`mt-0.5 text-sm font-bold ${costBetter ? "text-good" : costDelta > 0 ? "text-bad" : "text-[#667268]"}`}>
            {costDelta >= 0 ? "+" : ""}{costDelta.toFixed(1)}%
          </p>
        </div>
        <div className="border border-line bg-white px-4 py-3">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#667268]">Fill rate</p>
          <p className="mt-1 text-xl font-bold">{(before.fill_rate * 100).toFixed(1)}% → {(after.fill_rate * 100).toFixed(1)}%</p>
          <p className={`mt-0.5 text-sm font-bold ${after.fill_rate >= before.fill_rate ? "text-good" : "text-bad"}`}>
            {after.fill_rate >= before.fill_rate ? "+" : ""}{((after.fill_rate - before.fill_rate) * 100).toFixed(1)} pts
          </p>
        </div>
        <div className="border border-line bg-white px-4 py-3">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-[#667268]">Days of inventory</p>
          <p className="mt-1 text-xl font-bold">{before.days_of_inventory.toFixed(1)} → {after.days_of_inventory.toFixed(1)} days</p>
          <p className={`mt-0.5 text-sm font-bold ${after.days_of_inventory <= before.days_of_inventory ? "text-good" : "text-bad"}`}>
            {after.days_of_inventory <= before.days_of_inventory ? "▼" : "▲"} {Math.abs(after.days_of_inventory - before.days_of_inventory).toFixed(1)}
          </p>
        </div>
      </div>
      <p className="mt-4 text-sm leading-6 text-[#334139]">{shortAdvisory}</p>
      <p className="mt-2 text-[10px] leading-relaxed text-[#667268]">
        All numbers from the on-device optimizer benchmark. Advisory text is an LLM-generated explanation, not computed math.
        {/* Carry-forward guardrail: a bare "-7.2%" reads as money saved against the
            viewer's real costs. It is not — the comparator is an untuned heuristic
            on seeded synthetic data. */}
        <br />
        Percentages compare the tuned optimizer against the <strong>naive reorder-point + shortest-route baseline</strong> on
        this seeded synthetic scenario — not against a customer&rsquo;s actual costs.
      </p>
    </section>
  );
}

function ResultsView({ benchmark, rationale }: { benchmark: Benchmark; rationale: Rationale }) {
  const metrics = useMemo(() => buildMetricComparisons(benchmark), [benchmark]);
  const winner = benchmark.winner.approach;
  return (
    <div className="grid gap-5">
      <PlanSummary benchmark={benchmark} rationale={rationale} />
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
