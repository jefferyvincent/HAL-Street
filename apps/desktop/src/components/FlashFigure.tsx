import { cn } from "@/lib/cn";
import { Trend } from "@/components/Trend";
import { useFlash } from "@/hooks/useFlash";

/**
 * A money figure that lights for a moment when it moves, in the direction it moved.
 *
 * The tape idiom, and it answers the one question a static number cannot: *which* of
 * these just changed, on a screen where most things sit still for minutes at a time.
 *
 * The colour of the figure and the colour of the flash are different claims and are
 * kept apart. The figure is green or red by whether the position is winning; the
 * flash is green or red by which way it just moved. A losing position that recovered
 * a dollar is a red figure under a green flash, and both are true.
 */
export function FlashFigure({ value, text, className, size = 10 }: {
  /** The number, for the direction. Null when it cannot be priced. */
  value: number | null;
  /** The already-formatted words, which this never computes. */
  text: string;
  className?: string;
  size?: number;
}) {
  const flash = useFlash(value);

  return (
    <span className={cn("flex items-center gap-[5px] px-[3px] font-mono tabular-nums",
      flash === "up" && "flash-up",
      flash === "down" && "flash-down",
      className)}>
      {value !== null && <Trend value={value} size={size} />}
      {text}
    </span>
  );
}
