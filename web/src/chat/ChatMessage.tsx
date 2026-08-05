/**
 * One message in the transcript.
 *
 * The user's own text is rendered as text, never as markup — a chat box is an
 * injection surface, and the answer path already scans it server-side. React
 * escapes by default and nothing here uses `dangerouslySetInnerHTML`; the browser
 * check asserts that an HTML-looking question produces no element.
 *
 * An assistant message carries its provenance chips, its citations, and — when the
 * grounding validator rejected the model's wording — the fact that what is on
 * screen is the template instead.
 */

import { AlertTriangle, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { answerChips } from "../lib/chatDisplay";
import type { ChatAnswer } from "../lib/types";
import ProvenanceChips from "./ProvenanceChips";

export function UserMessage({ text }: { text: string }) {
  return (
    <li className="flex justify-end">
      <div className="max-w-[85%] rounded-md rounded-br-none border border-line bg-white px-3 py-2 text-sm text-ink shadow-sm">
        <p className="whitespace-pre-wrap break-words">{text}</p>
      </div>
    </li>
  );
}

export function NoticeMessage({ text, tone = "info" }: { text: string; tone?: "info" | "error" }) {
  const isError = tone === "error";
  return (
    <li>
      <div
        className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${
          isError ? "border-[#f3b7af] bg-[#fff5f3] text-bad" : "border-line bg-field text-[#536258]"
        }`}
      >
        {isError ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> : null}
        <span className="whitespace-pre-wrap break-words">{text}</span>
      </div>
    </li>
  );
}

export function AnswerMessage({ answer }: { answer: ChatAnswer }) {
  const [showSources, setShowSources] = useState(false);
  const chips = answerChips(answer);
  const flags = answer.injection_flags ?? [];
  // Why the template is on screen instead of the model's wording. The three cases
  // are genuinely different and saying "rejected" for an unreachable model would be
  // a small lie in the one place the panel is explaining itself.
  const fallbackReason =
    answer.answer_source === "template_after_llm_error"
      ? "The local model could not be reached"
      : answer.answer_source === "template_after_ungrounded_number"
        ? `The model stated ${answer.grounding.numbers_ungrounded} number(s) that are not in the facts, so its wording was rejected`
        : answer.answer_source === "template_after_short_llm_output"
          ? "The model's reply was unusable (empty or cut off)"
          : "";
  // Only claim a numeric provenance when the answer can actually contain a number.
  // A refusal states none, and the line read as though it did.
  const showsNumbers = answer.grounding.numbers_checked > 0 || (answer.citations?.length ?? 0) > 0;

  return (
    <li>
      <div className="rounded-md rounded-bl-none border border-line bg-white px-3 py-2.5 shadow-sm">
        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-ink">{answer.answer}</p>
        <ProvenanceChips chips={chips} />

        {flags.length ? (
          <div className="mt-2 flex items-start gap-2 rounded-md border border-[#f4c47a] bg-[#fff8eb] px-2.5 py-2 text-xs text-warn">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Prompt-injection patterns flagged and excluded from the model prompt, never executed:{" "}
              {flags.map((flag) => String(flag.pattern ?? "unknown")).join(", ")}.
            </span>
          </div>
        ) : null}

        {fallbackReason ? (
          <p className="mt-2 text-[11px] leading-relaxed text-warn">
            {fallbackReason}, so this is the deterministic template built from the same facts.
          </p>
        ) : null}

        {answer.notes?.length ? (
          <ul className="mt-2 list-disc pl-4 text-[11px] leading-relaxed text-[#6c786d]">
            {answer.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}

        {answer.citations?.length ? (
          <div className="mt-2 border-t border-line pt-2">
            <button
              type="button"
              onClick={() => setShowSources((value) => !value)}
              aria-expanded={showSources}
              className="text-[11px] font-semibold text-[#2f6f4e] underline decoration-dotted focus:outline-none focus:ring-2 focus:ring-[#b8cfbd]"
            >
              {showSources ? "Hide sources" : `Show ${answer.citations.length} source${answer.citations.length === 1 ? "" : "s"}`}
            </button>
            {showSources ? (
              <ul className="mt-2 grid gap-1.5">
                {answer.citations.map((citation) => (
                  <li key={citation.citation_id} className="rounded border border-line bg-field px-2 py-1.5 text-[11px] leading-snug">
                    <span className="font-semibold text-ink">[{citation.citation_id}]</span>{" "}
                    <span className="text-[#536258]">{citation.source}</span>
                    {citation.text_excerpt ? (
                      <p className="mt-0.5 text-[#4d5c51]">{citation.text_excerpt}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {showsNumbers ? (
          <p className="mt-2 text-[10px] leading-relaxed text-[#7c887e]">
            Numbers from: {answer.numeric_values_source}.
          </p>
        ) : null}
      </div>
    </li>
  );
}
