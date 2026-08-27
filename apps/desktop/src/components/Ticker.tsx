import { cn } from "@/lib/cn";

/**
 * A ticker as a chip, so a symbol is found by shape before it is read.
 *
 * Drawn rather than fetched. A real logo would be an external request the panel's
 * policy blocks outright, or a binary asset committed to a repository that is
 * otherwise entirely readable — and either way it would cover the three symbols
 * this agent trades and nothing else. A monogram works for any ticker that ever
 * appears, including one added tomorrow.
 *
 * The hue comes from the symbol itself, so it is stable across sessions and across
 * machines without a lookup table anyone has to maintain. Fixed saturation and
 * lightness keep every chip at the same weight — a colour that varies in contrast
 * as well as hue would make some symbols shout.
 */
export function Ticker({ symbol, size = "sm" }: { symbol: string; size?: "sm" | "md" }) {
  const root = (symbol || "?").toUpperCase();
  const hue = hueOf(root);

  return (
    <span
      title={root}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[3px] border font-mono font-bold leading-none tracking-[.04em]",
        size === "md" ? "min-w-[42px] px-[6px] py-[4px] text-[11px]"
                      : "min-w-[34px] px-[5px] py-[3px] text-[9.5px]",
      )}
      style={{
        color: `hsl(${hue} 70% 68%)`,
        borderColor: `hsl(${hue} 55% 40% / 0.55)`,
        backgroundColor: `hsl(${hue} 60% 30% / 0.22)`,
      }}
    >
      {root}
    </span>
  );
}

/**
 * A stable hue per symbol.
 *
 * Deliberately not random and not sequential: the same ticker must get the same
 * colour on every machine and in every session, or the chip stops being a
 * recognisable shape and becomes decoration.
 */
function hueOf(symbol: string): number {
  let hash = 0;
  for (const char of symbol) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  // Nudged off the amber the chrome already uses, so a chip never reads as chrome.
  return (hash + 25) % 360;
}
