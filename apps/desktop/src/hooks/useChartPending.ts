import { useMemo } from "react";

import { stripRoot } from "@/lib/names";
import { useFormat } from "@/hooks/useFormat";
import { useMarks } from "@/hooks/useMarks";
import { useStrings } from "@/hooks/useStrings";
import type { BookRow } from "@/hooks/useBook";
import type { LegMark } from "@/types";

export interface PendingTile {
  label: string;
  /** Null is the hole: the tile shimmers rather than showing a guess. */
  value: string | null;
  tone: string;
  /** Whether the figure has a direction worth drawing an arrow for. */
  trend: number | null;
}

/**
 * What is already known about a position while its price history is on the way.
 *
 * Almost everything, as it turns out: the name, the ticker, the size, the legs, their
 * fills, their live prices and the P&L are all on the panel before anyone clicks.
 * Only the target and the stop are genuinely unknown, because both are derived from
 * the exit policy by the same function the agent acts on — and asking the panel to
 * compute them would be the one way this picture could come to disagree with what
 * the agent will do.
 */
export function useChartPending(row: BookRow) {
  const t = useStrings();
  const f = useFormat();
  const live = useMarks()?.marks[row.structureId];

  const tiles = useMemo<PendingTile[]>(() => {
    const mark = live?.mark ?? null;
    const pnl = live?.unrealized_usd ?? row.unrealized ?? null;
    const tone = pnl === null ? "text-ink" : Number(pnl) >= 0 ? "text-pass" : "text-fail";

    return [
      // Known from the ledger the moment the panel loaded.
      { label: t.chart.entry, value: row.entry ? f.toClose(row.entry) : null,
        tone: "text-ink", trend: null },
      { label: t.chart.target, value: null, tone: "text-pass", trend: null },
      { label: t.chart.stop, value: null, tone: "text-fail", trend: null },
      // Known from the marks route, which answered before the click.
      { label: t.chart.last, value: mark === null ? null : f.toClose(mark),
        tone, trend: null },
      { label: t.chart.pnl, value: pnl === null ? null : f.money(pnl),
        tone: pnl === null ? "text-ink/40" : tone,
        trend: pnl === null ? null : Number(pnl) },
    ];
  }, [row, live, t, f]);

  return {
    name: stripRoot(row.name, row.underlying),
    underlying: row.underlying,
    tiles,
    live: live as { legs?: LegMark[] } | undefined,
  };
}
