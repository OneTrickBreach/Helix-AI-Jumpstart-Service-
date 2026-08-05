/**
 * Provenance chips — where a message's content came from, and who wrote the words.
 *
 * On screen at all times, on every message, because the four things this panel can
 * put in a bubble are not equally strong evidence: a figure read from the dataset,
 * a figure from the recorded optimizer run, a sentence quoted from a planner
 * document, and a paragraph phrased by a language model. Colour alone does not
 * carry it — each chip has a word and a hover explanation.
 */

import type { ProvenanceChip } from "../lib/chatDisplay";

const TONE_CLASS: Record<ProvenanceChip["tone"], string> = {
  dataset: "border-[#b8cfbd] bg-[#f3faf4] text-[#2f6f4e]",
  optimizer: "border-[#9fc0a8] bg-[#eef7f0] text-[#1b7f45]",
  documents: "border-line bg-field text-[#536258]",
  glossary: "border-line bg-white text-[#536258]",
  llm: "border-[#f4c47a] bg-[#fff8eb] text-warn",
  deterministic: "border-line bg-white text-[#536258]",
  whatif: "border-violet-400 bg-violet-100 text-violet-800",
  refusal: "border-[#f3b7af] bg-[#fff5f3] text-bad",
};

export default function ProvenanceChips({ chips }: { chips: ProvenanceChip[] }) {
  if (!chips.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Where this answer came from">
      {chips.map((chip) => (
        <li key={chip.key}>
          <span
            title={chip.title}
            className={`inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] ${TONE_CLASS[chip.tone]}`}
          >
            {chip.label}
          </span>
        </li>
      ))}
    </ul>
  );
}
