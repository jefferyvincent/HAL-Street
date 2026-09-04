import type { Candle, Line, Series } from "@/hooks/useStructureLevels";

/**
 * A fingerprint of what a chart is *of*, as opposed to what it currently reads.
 *
 * The canvas re-fits the time scale when this changes and leaves it alone when it
 * does not. That distinction is the whole point: switching bar size, opening a
 * different structure, or a new bar arriving are all reasons to reset the view, and
 * the live mark ticking a cent is not.
 *
 * It used to re-fit on every render. Two things came of that — a scroll or a zoom was
 * undone within seconds, and the view was reset continuously rather than at the
 * moments a reset means something. A chart that re-fits constantly reads as one that
 * never settles where you left it, which is the opposite of how it sounds.
 *
 * Cheap on purpose. Counts and endpoints, not every value: a 1-minute series and a
 * 1-hour series over the same position differ in both, and the forming candle growing
 * inside its own bucket changes neither.
 */
export function chartShape(series: Series[], candles: Candle[], lines: Line[]): string {
  return [
    series.length,
    candles.length,
    series[0]?.time ?? 0,
    series[series.length - 1]?.time ?? 0,
    // The levels move only when the structure does, but they are what the scale has
    // to contain — a chart fitted without them is fitted to the wrong thing.
    lines.map((l) => `${l.key}=${l.value}`).join(","),
  ].join(":");
}
