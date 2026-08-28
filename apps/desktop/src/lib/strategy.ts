/**
 * A structure's name split into what it is and when it is.
 *
 * Names read `2026-10-16 765/775 call credit spread` — an expiry, the strikes, then
 * the strategy. The strategy is the part a trader scans for, and it was the part with
 * the least contrast: eleven characters of prose at the end of a line of digits,
 * rendered exactly like the digits.
 *
 * Split on the last number, because that is what the two halves genuinely are: the
 * head is dates and strikes, the tail is words. Anything that does not have that shape
 * comes back whole in `head` with no `strategy`, so a name from a structure this
 * builder never made is printed rather than mangled.
 */
import { stripRoot } from "@/lib/names";

export interface NameParts {
  head: string;
  /** The strategy phrase, or "" when the name does not end in one. */
  strategy: string;
}

//: A head ending in a digit, then a tail of nothing but letters and spaces. Anchored
//: at both ends so a stray number inside the tail refuses the match rather than
//: splitting the name somewhere arbitrary.
const SHAPE = /^(.*\d)\s+([A-Za-z][A-Za-z ]*)$/;

export function nameParts(name: string): NameParts {
  const match = SHAPE.exec(String(name ?? "").trim());
  if (!match) return { head: String(name ?? ""), strategy: "" };
  return { head: match[1]!, strategy: match[2]! };
}

/**
 * Which family a strategy belongs to, for colour.
 *
 * Coarse on purpose: a reader scanning a book wants to know at a glance whether a row
 * is a credit spread or a condor, not to distinguish nine variants by hue. More
 * colours than that stops being a signal and becomes decoration.
 */
export type StrategyKind = "credit" | "debit" | "condor" | "other";

export function strategyKind(strategy: string): StrategyKind {
  const s = strategy.toLowerCase();
  if (s.includes("condor") || s.includes("butterfly") || s.includes("fly")) {
    return "condor";
  }
  if (s.includes("credit")) return "credit";
  if (s.includes("debit")) return "debit";
  return "other";
}

//: One class per kind. Amber is the panel's accent and is already spoken for by
//: "attention", so the strategies take the cooler end and leave it alone.
export const STRATEGY_CLASS: Record<StrategyKind, string> = {
  credit: "text-agent",
  debit: "text-amber",
  condor: "text-pass",
  other: "text-ink/55",
};

/** A name split and classified, ready for markup to paint. */
export interface StructureNameParts {
  head: string;
  strategy: string;
  /** The class for the strategy, or "" when there is no strategy to paint. */
  strategyClass: string;
}

/**
 * Everything the name needs decided, in one call.
 *
 * The component was making three of them and a lookup — split the name, read its
 * kind, then find the class for that kind. Each step is small and together they are a
 * rule, and a rule that lives in a component is a rule no test can reach without
 * mounting React. Here it is five assertions.
 *
 * `root` is optional because the views genuinely disagree: the console shows the
 * ticker in its own chip and strips it from the name, the tape does not.
 */
export function structureName(name: string, root?: string): StructureNameParts {
  const shown = root ? stripRoot(String(name ?? ""), root) : String(name ?? "");
  const { head, strategy } = nameParts(shown);
  return {
    head,
    strategy,
    strategyClass: strategy ? STRATEGY_CLASS[strategyKind(strategy)] : "",
  };
}
