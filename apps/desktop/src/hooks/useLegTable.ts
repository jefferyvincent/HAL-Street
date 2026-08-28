import { useMemo } from "react";

import { legRows } from "@/lib/legRows";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import type { LegMark, StructureChart } from "@/types";

export interface LegLine {
  symbol: string;
  /** Signed contracts, so a two-lot reads as the two lots actually held. */
  qty: string;
  short: boolean;
  /** The word for the side, on the size's title. */
  side: string;
  basis: string;
  /** Whether that is the real figure or the words standing in for a missing one. */
  hasBasis: boolean;
  now: string;
  hasNow: boolean;
  pnl: string;
  /** Null where nothing could price the leg — which is not the same as flat. */
  pnlSign: number | null;
}

/**
 * Every leg of a structure, with what it filled at and what it has done since.
 *
 * Two sources, merged by `legRows` and neither recomputed: the fills come off the
 * order and never change, the marks come from the same `mark_legs` the net is summed
 * from. So a leg shown as unpriced is a leg the net is refusing to include, and the
 * P&L column adds to the tile above it exactly rather than approximately.
 *
 * `chart` may be null — that is the second between opening a position and its history
 * arriving, and the marks alone can fill the table.
 */
export function useLegTable(chart: StructureChart | null,
                            live: { legs?: LegMark[] } | null | undefined) {
  const t = useStrings();
  const f = useFormat();

  return useMemo(() => {
    const rows = legRows(chart, live);
    const closed = chart ? !chart.open : false;

    const lines = rows.map<LegLine>((leg) => {
      const pnl = leg.pnl === null ? null : Number(leg.pnl);
      const priced = pnl !== null && Number.isFinite(pnl);
      return {
        symbol: leg.symbol,
        qty: f.signed(leg.contracts, 0),
        short: leg.contracts < 0,
        side: leg.contracts < 0 ? t.chart.legShort : t.chart.legLong,
        basis: leg.basis === null ? t.chart.legNoBasis : f.plain(leg.basis),
        hasBasis: leg.basis !== null,
        now: leg.now === null ? t.chart.legNoQuote : f.plain(leg.now),
        hasNow: leg.now !== null,
        pnl: priced ? f.money(pnl) : t.common.dash,
        pnlSign: priced ? pnl : null,
      };
    });

    return {
      lines,
      // The middle column is a live mid while the position is on and the closing fill
      // once it is not. Different claims, so they are named differently.
      nowHeading: closed ? t.chart.exitAt : t.chart.legNow,
      // Only for a position still on. A structure opened before per-leg fills were
      // kept has no basis to show and no way to get one — the order is long since
      // filled, and the backfill only runs while it is held.
      pending: !closed && lines.length > 0 && lines.every((l) => !l.hasBasis),
    };
  }, [chart, live, t, f]);
}
