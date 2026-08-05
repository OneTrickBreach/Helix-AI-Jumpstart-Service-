/**
 * The `BETA` chip (Iteration 5 decision 12).
 *
 * This is a guardrail, not styling. A conversational surface is the highest-risk
 * thing in this repo for saying something wrong in front of a customer, and it has
 * not been reviewed by the project sponsor. The chip stays on the panel header and
 * on every what-if card until it has been — including in every screenshot.
 */
export default function BetaChip({ title }: { title?: string }) {
  return (
    <span
      title={
        title ??
        "Beta: this conversational surface has not yet been reviewed by the project sponsor. Numbers are real; the surface is new."
      }
      className="inline-flex items-center rounded-sm border border-warn/60 bg-[#fff8eb] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-warn"
    >
      Beta
    </span>
  );
}
