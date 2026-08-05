/**
 * "Ask the plan" — the conversational analyst panel (Iteration 5, BETA).
 *
 * Sits *alongside* the results and dataset views, never replacing either: this is
 * an interrogation tool for the honest benchmark, not a substitute for it. It lives
 * in its own component because `App.tsx` and `DatasetView.tsx` are already
 * monolithic and absorbing a third surface into them would make all three worse.
 *
 * What it does and does not do:
 *   - Questions go to `POST /chat/ask`, which answers from the generated dataset
 *     and the recorded optimizer run. No number is ever produced by the model.
 *   - A what-if goes nowhere until the confirm card is accepted. The API enforces
 *     that as well, so the button is a courtesy, not the control.
 *   - The transcript is in-session only (decision 10). Nothing is persisted, and
 *     changing scenario starts a new one rather than leaving answers about one
 *     dataset sitting under the header of another.
 *   - `?replay=true` renders a real captured transcript with no API calls at all.
 *
 * The `BETA` chip in the header stays until the project sponsor has reviewed this
 * surface. It is a guardrail, not decoration.
 */

import { CornerDownLeft, FileClock, Loader2, MessageSquare, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  MAX_QUESTION_CHARS,
  askChat,
  fetchRecordedTranscript,
  whatIfStreamUrl,
} from "../lib/chatApi";
import type { ChatAnswer, ConfirmationCard, RecordedTranscript, WhatIfResult } from "../lib/types";
import BetaChip from "./BetaChip";
import { AnswerMessage, NoticeMessage, UserMessage } from "./ChatMessage";
import WhatIfConfirmCard, { type StageEvent } from "./WhatIfConfirmCard";
import WhatIfResultCard from "./WhatIfResultCard";

/**
 * Suggested starter questions, led by the one that prompted this whole iteration:
 * *"what if warehouse 4 is completely depleted?"* — which on the demo scenario is a
 * place that does not exist, and gets the premise corrected plus the offer of the
 * scenario that does have four distribution centers.
 */
const STARTER_QUESTIONS = [
  "What if warehouse 4 is completely depleted?",
  "What if DC-001 goes down?",
  "How many distribution centers are there?",
  "Why did the classical optimizer win?",
  "What does days of inventory mean?",
];

type Entry =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "answer"; answer: ChatAnswer }
  | {
      id: string;
      role: "confirm";
      card: ConfirmationCard;
      status: "pending" | "running" | "done" | "dismissed";
      stages: StageEvent[];
      error?: string;
    }
  | { id: string; role: "whatif"; result: WhatIfResult }
  | { id: string; role: "notice"; text: string; tone: "info" | "error" };

let sequence = 0;
const nextId = (prefix: string) => `${prefix}-${++sequence}`;

export default function ChatPanel({
  scenario,
  replay = false,
  onClose,
}: {
  scenario: string;
  replay?: boolean;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState<RecordedTranscript | null>(null);
  const streamRef = useRef<EventSource | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => () => streamRef.current?.close(), []);

  // Load the recorded transcript once, in replay mode only.
  useEffect(() => {
    if (!replay) return;
    let cancelled = false;
    fetchRecordedTranscript()
      .then((data) => {
        if (!cancelled) setTranscript(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setEntries((current) => [
          ...current,
          {
            id: nextId("notice"),
            role: "notice",
            tone: "error",
            text: `The recorded transcript could not be loaded (${err instanceof Error ? err.message : String(err)}).`,
          },
        ]);
      });
    return () => {
      cancelled = true;
    };
  }, [replay]);

  /**
   * A transcript belongs to one dataset, so switching scenario starts a new one —
   * answers about `baseline` must never sit under a `stress-large` header. It says
   * so rather than silently emptying.
   *
   * Two cases are deliberately *not* a switch: the first load, where the scenario
   * arrives as "" and is then filled in (there is nothing to lose), and replay,
   * where the panel is pinned to the recording's own scenario.
   */
  const previousScenario = useRef<string>(scenario);
  useEffect(() => {
    if (replay || previousScenario.current === scenario) return;
    const had = previousScenario.current;
    previousScenario.current = scenario;
    if (!had) return;
    streamRef.current?.close();
    setBusy(false);
    setEntries([
      {
        id: nextId("notice"),
        role: "notice",
        tone: "info",
        text: `Scenario changed to ${scenario}. Starting a new transcript — answers about the previous dataset would be misleading under this one.`,
      },
    ]);
  }, [replay, scenario]);

  // Scroll the transcript container itself rather than calling scrollIntoView on a
  // sentinel: that also scrolls every scrollable ancestor, which would yank the
  // results or dataset view sitting next to the panel.
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [entries]);

  const starters = useMemo(() => {
    if (replay) return (transcript?.entries ?? []).map((entry) => entry.question);
    return STARTER_QUESTIONS;
  }, [replay, transcript]);

  /**
   * What the header claims the answers are grounded in.
   *
   * In replay it is the recording's own scenario, not the app's: with the backend
   * blocked the scenario list never loads, and the header read "grounded in no
   * scenario selected" above answers that were plainly about `component-shortage-shock`.
   */
  const groundedScenario = replay ? (transcript?.scenario ?? scenario) : scenario;

  const push = useCallback((entry: Entry) => setEntries((current) => [...current, entry]), []);

  const patchConfirm = useCallback((id: string, patch: Partial<Extract<Entry, { role: "confirm" }>>) => {
    setEntries((current) =>
      current.map((entry) => (entry.id === id && entry.role === "confirm" ? { ...entry, ...patch } : entry)),
    );
  }, []);

  /** Replay: answer from the captured transcript, with no API call at all. */
  const answerFromRecording = useCallback(
    (question: string) => {
      const recorded = (transcript?.entries ?? []).find(
        (entry) => entry.question.trim().toLowerCase() === question.trim().toLowerCase(),
      );
      if (!recorded) {
        push({
          id: nextId("notice"),
          role: "notice",
          tone: "info",
          text:
            "This is a recorded transcript, so only the captured questions can be answered. Pick one of the " +
            "suggestions above, or open the live demo to ask your own.",
        });
        return;
      }
      // Same two entries a live answer produces, in the same order, from the same
      // components — the recording only replaces the network call.
      push({ id: nextId("answer"), role: "answer", answer: recorded.answer });
      if (recorded.kind === "whatif") {
        push({
          id: nextId("confirm"),
          role: "confirm",
          card: recorded.confirmation,
          status: "pending",
          stages: [],
        });
      }
    },
    [push, transcript],
  );

  const submit = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || busy) return;
      setDraft("");
      push({ id: nextId("user"), role: "user", text });

      if (replay) {
        answerFromRecording(text);
        return;
      }

      if (!scenario) {
        // The scenario list failed to load, so there is no dataset to answer from.
        // Say that instead of posting an empty scenario and surfacing a 422.
        push({
          id: nextId("notice"),
          role: "notice",
          tone: "error",
          text:
            "No scenario is loaded, so there is nothing on disk for me to answer from. Pick a scenario on " +
            "the results screen (or check the API is up) and ask again.",
        });
        return;
      }

      setBusy(true);
      try {
        const answer = await askChat(scenario, text);
        push({ id: nextId("answer"), role: "answer", answer });
        const parse = answer.what_if?.parse;
        if (parse?.outcome === "parsed" && parse.confirmation) {
          push({
            id: nextId("confirm"),
            role: "confirm",
            card: parse.confirmation,
            status: "pending",
            stages: [],
          });
        } else if (
          parse &&
          parse.outcome !== "parsed" &&
          parse.message &&
          !answer.answer.includes(parse.message)
        ) {
          // The parser can say something the answer did not — most often the exact
          // clarifying question ("by how much?"). Shown only when it is genuinely
          // additive: for an unknown place the answer already carries the parser's
          // correction verbatim, and repeating it would print two identical
          // sentences on screen.
          push({ id: nextId("notice"), role: "notice", tone: "info", text: parse.message });
        }
      } catch (err: unknown) {
        push({
          id: nextId("notice"),
          role: "notice",
          tone: "error",
          text: `That question could not be answered (${err instanceof Error ? err.message : String(err)}). Nothing was run.`,
        });
      } finally {
        setBusy(false);
      }
    },
    [answerFromRecording, busy, push, replay, scenario],
  );

  /** Explicit confirmation. Streams the engine's real stage boundaries. */
  const run = useCallback(
    (id: string, card: ConfirmationCard) => {
      if (replay) {
        const recorded = (transcript?.entries ?? []).find(
          (entry) => entry.kind === "whatif" && entry.confirmation.fingerprint === card.fingerprint,
        );
        if (recorded && recorded.kind === "whatif") {
          patchConfirm(id, { status: "done" });
          push({ id: nextId("whatif"), role: "whatif", result: recorded.result });
        } else {
          patchConfirm(id, { status: "pending", error: "no recorded result for this perturbation" });
        }
        return;
      }

      streamRef.current?.close();
      setBusy(true);
      patchConfirm(id, { status: "running", stages: [], error: undefined });
      const stream = new EventSource(whatIfStreamUrl(scenario, card.perturbation));
      streamRef.current = stream;

      stream.addEventListener("stage", (event) => {
        const data = JSON.parse((event as MessageEvent).data) as StageEvent;
        setEntries((current) =>
          current.map((entry) =>
            entry.id === id && entry.role === "confirm"
              ? { ...entry, stages: [...entry.stages.filter((s) => s.stage !== data.stage), data] }
              : entry,
          ),
        );
      });
      stream.addEventListener("done", (event) => {
        const result = JSON.parse((event as MessageEvent).data) as WhatIfResult;
        patchConfirm(id, { status: "done" });
        push({ id: nextId("whatif"), role: "whatif", result });
        setBusy(false);
        stream.close();
      });
      stream.addEventListener("error", (event) => {
        const messageEvent = event as MessageEvent;
        if (!messageEvent.data) return;
        const payload = JSON.parse(messageEvent.data) as { detail?: string };
        patchConfirm(id, { status: "pending", error: payload.detail ?? "the run failed" });
        setBusy(false);
        stream.close();
      });
      stream.onerror = () => {
        patchConfirm(id, { status: "pending", error: "the connection dropped before the run finished" });
        setBusy(false);
        stream.close();
      };
    },
    [patchConfirm, push, replay, scenario, transcript],
  );

  return (
    <aside
      className="flex w-full flex-col border-t border-line bg-field lg:sticky lg:top-0 lg:h-screen lg:w-[420px] lg:shrink-0 lg:border-l lg:border-t-0"
      aria-label="Ask the plan (beta)"
    >
      <header className="border-b border-line bg-white px-3 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-[#2f6f4e]" />
            <h2 className="text-sm font-semibold">Ask the plan</h2>
            <BetaChip />
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close the chat panel"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line bg-white text-[#536258] transition hover:bg-field focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1 text-[11px] leading-snug text-[#5d6b62]">
          Grounded in <strong>{groundedScenario || "no scenario selected"}</strong>: the generated dataset and
          the recorded on-device run. The model reads and explains; it never calculates a number.
        </p>
        {replay ? (
          <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-sm border border-line bg-field px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#536258]">
            <FileClock className="h-3 w-3" />
            Recorded transcript · {transcript?.scenario ?? scenario}
          </p>
        ) : null}
      </header>

      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {entries.length === 0 ? (
          <div className="rounded-md border border-dashed border-line bg-white px-3 py-3 text-xs leading-relaxed text-[#536258]">
            <p className="font-semibold text-ink">Ask about this dataset, this run, or a what-if.</p>
            <p className="mt-1">
              I can count and quote anything in the generated data, explain the recorded optimizer result, define
              the jargon on screen, and re-run the real optimizer on a perturbation you confirm first. If I
              can&rsquo;t model something, I say so rather than estimating.
            </p>
          </div>
        ) : null}

        <ul className="grid gap-3" aria-live="polite">
          {entries.map((entry) => {
            if (entry.role === "user") return <UserMessage key={entry.id} text={entry.text} />;
            if (entry.role === "answer") return <AnswerMessage key={entry.id} answer={entry.answer} />;
            if (entry.role === "notice")
              return <NoticeMessage key={entry.id} text={entry.text} tone={entry.tone} />;
            if (entry.role === "whatif") return <WhatIfResultCard key={entry.id} result={entry.result} />;
            return (
              <WhatIfConfirmCard
                key={entry.id}
                card={entry.card}
                status={entry.status}
                stages={entry.stages}
                error={entry.error}
                busy={busy}
                onRun={() => run(entry.id, entry.card)}
                onDismiss={() => patchConfirm(entry.id, { status: "dismissed" })}
              />
            );
          })}
        </ul>
        {busy ? (
          <p className="mt-3 flex items-center gap-2 text-xs text-[#6c786d]">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Working on it — reading the data on this device…
          </p>
        ) : null}
      </div>

      <div className="border-t border-line bg-white px-3 py-2.5">
        {starters.length ? (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {starters.map((question) => (
              <button
                key={question}
                type="button"
                disabled={busy}
                onClick={() => submit(question)}
                className="rounded-full border border-line bg-field px-2.5 py-1 text-[11px] font-medium text-[#42504a] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
              >
                {question}
              </button>
            ))}
          </div>
        ) : null}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit(draft);
          }}
          className="flex items-end gap-2"
        >
          <label className="flex-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#667268]">
            Your question
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value.slice(0, MAX_QUESTION_CHARS))}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit(draft);
                }
              }}
              rows={2}
              disabled={busy || replay}
              placeholder={
                replay
                  ? "Recorded transcript — pick a captured question above"
                  : "e.g. what if DC-002 is knocked out from period 40?"
              }
              className="mt-1 w-full resize-none rounded-md border border-line bg-white px-2.5 py-2 text-xs font-normal normal-case tracking-normal text-ink placeholder:text-[#8d998f] focus:outline-none focus:ring-2 focus:ring-[#b8cfbd] disabled:bg-field"
            />
          </label>
          <button
            type="submit"
            disabled={busy || replay || !draft.trim()}
            className="mb-0.5 inline-flex h-9 items-center gap-1.5 rounded-md bg-ink px-3 text-xs font-semibold text-white transition hover:bg-[#263329] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <CornerDownLeft className="h-3.5 w-3.5" />
            Ask
          </button>
        </form>
        <p className="mt-1.5 text-[10px] leading-relaxed text-[#7c887e]">
          Seeded synthetic data, on-device. Every figure traces to a file on disk or to an optimizer run here —
          never to the language model. What-ifs run only after you confirm them.
        </p>
      </div>
    </aside>
  );
}
