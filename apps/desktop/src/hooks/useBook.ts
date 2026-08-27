import { useMemo } from "react";
import { useConnection } from "@/stores/connection";
import type { Position } from "@/types";

export interface BookRow {
  structureId: string;
  /**
   * The open position itself, for the chart read beside it. Null for a closed row:
   * what the chart is doing now says nothing about a position that is no longer on.
   */
  position: Position | null;
  name: string;
  underlying: string;
  qty: number;
  open: boolean;
  openedAt: string;
  closedAt: string | null;
  entry: string | null;
  exit: string | null;
  realized: string | null;
  /**
   * The agent's own last unrealized read on an open row, as a fallback for when the
   * broker cannot be reached. Null on a closed row: there is nothing left to mark.
   */
  unrealized: string | null;
}

/**
 * The whole book, open positions first, then closed newest-first.
 *
 * Both, deliberately. A chart of a position that already ran its course — opened
 * here, target there, closed at that point — is the one worth looking at, and a view
 * that only lists what is open can never show one.
 */
export function useBook(): { rows: BookRow[]; open: number; closed: number } {
  const snap = useConnection((s) => s.snapshot);

  return useMemo(() => {
    if (!snap) return { rows: [], open: 0, closed: 0 };

    const open: BookRow[] = snap.positions.map((p) => ({
      structureId: p.structure_id,
      position: p,
      name: p.name,
      underlying: p.underlying,
      qty: p.qty,
      open: true,
      openedAt: p.opened_at,
      closedAt: null,
      entry: p.entry_price,
      exit: null,
      realized: null,
      unrealized: p.read?.unrealized_usd ?? null,
    }));

    const closed: BookRow[] = snap.closed.map((c) => ({
      structureId: c.structure_id,
      position: null,
      name: c.name,
      underlying: c.underlying,
      qty: c.qty,
      open: false,
      openedAt: c.opened_at,
      closedAt: c.closed_at,
      entry: c.entry_price,
      exit: c.exit_price,
      realized: c.realized_usd,
      unrealized: null,
    }));

    return { rows: [...open, ...closed], open: open.length, closed: closed.length };
  }, [snap]);
}
