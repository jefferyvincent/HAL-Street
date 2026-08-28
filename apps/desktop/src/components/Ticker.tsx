import { cn } from "@/lib/cn";
import { chipColors, hueOf } from "@/lib/hue";
import { useStrings } from "@/hooks/useStrings";

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
 * as well as hue would make some symbols shout. Both are `lib/hue.ts`.
 */
export function Ticker({ symbol, size = "sm" }: { symbol: string; size?: "sm" | "md" }) {
  const t = useStrings();
  const root = (symbol || t.common.unknown).toUpperCase();

  return (
    <span
      title={root}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[3px] border font-mono font-bold leading-none tracking-[.04em]",
        size === "md" ? "min-w-[42px] px-[6px] py-[4px] text-[11px]"
                      : "min-w-[34px] px-[5px] py-[3px] text-[9.5px]",
      )}
      style={chipColors(hueOf(root))}
    >
      {root}
    </span>
  );
}
