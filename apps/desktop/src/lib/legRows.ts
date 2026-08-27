import type { LegMark, StructureChart } from "@/types";

/** One leg, ready to render, whichever source could answer for it. */
export interface LegRow {
  symbol: string;
  /** Signed contracts the account holds for this structure. */
  contracts: number;
  /** What it filled at, per contract. Null when the fill was never recorded. */
  basis: string | null;
  /** Its mid now, or its closing fill once the position is closed. */
  now: string | null;
  /** Unrealized while open, realized once closed. */
  pnl: string | null;
}

/**
 * The leg table's rows, from whichever of the two sources can answer.
 *
 * Two sources because they arrive at different times and carry different halves. The
 * chart route holds the fills — they come off the order and never change — and takes
 * about seven hundred milliseconds because it spawns an MCP subprocess and waits on
 * Alpaca. The marks route holds the live prices, and the panel already has its answer
 * before anyone opens a position.
 *
 * So `chart` may be null, and that is the ordinary case rather than an error: it is
 * every moment between clicking a position and the history arriving. During it the
 * marks alone can fill the whole table, because `/api/marks` carries the recorded
 * fill beside the live mid. Showing that beats showing a spinner over information
 * already in hand.
 *
 * A closed position has no live half and needs none — there is nothing left to mark,
 * and the round trip is the whole story.
 */
export function legRows(chart: StructureChart | null,
                        live?: { legs?: LegMark[] } | null): LegRow[] {
  const marks = new Map((live?.legs ?? []).map((l) => [l.symbol, l]));

  if (chart) {
    const closed = !chart.open;
    return chart.legs.map((leg) => {
      const mark = marks.get(leg.symbol);
      return {
        symbol: leg.symbol,
        contracts: leg.contracts,
        basis: leg.basis,
        now: closed ? leg.exit : mark?.mid ?? null,
        pnl: closed ? leg.realized_usd : mark?.unrealized_usd ?? null,
      };
    });
  }

  // No chart yet. Only an open position has marks, which is the only case that
  // reaches here — a closed one is opened from the book and its history is the only
  // thing there is to show.
  return (live?.legs ?? []).map((leg) => ({
    symbol: leg.symbol,
    contracts: leg.contracts,
    basis: leg.basis,
    now: leg.mid,
    pnl: leg.unrealized_usd,
  }));
}
