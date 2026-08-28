import { useMemo } from "react";

import { useBook, type BookRow } from "@/hooks/useBook";
import { useFormat } from "@/hooks/useFormat";
import { useMarks } from "@/hooks/useMarks";
import { useStrings } from "@/hooks/useStrings";

export interface BookPnl {
  value: string;
  /** The sign, for the colour and the arrow. */
  amount: number;
  /** Marked-to-market rather than realized, which is a different claim and tagged. */
  open: boolean;
}

export interface BookLine extends BookRow {
  status: string;
  openedOn: string;
  entryText: string;
  exitText: string;
  /** Null where neither the broker nor the agent could price it — not flat. */
  pnl: BookPnl | null;
}

/**
 * The book as the table renders it.
 *
 * The P&L column is realized on a closed row and marked-to-market on an open one.
 * Both are money made or lost on the same position and belong in one column; what
 * they are not is interchangeable, so the open one is tagged. Live where the broker
 * answered, the agent's own last read otherwise, and nothing at all when neither can
 * price it — a structure with a missing quote is unpriceable, not flat, and printing
 * $0.00 there would be the worst of the three.
 *
 * The marks come from the same source the console's holding card reads, so the two
 * cannot disagree about what a position is worth.
 */
export function useBookTable() {
  const t = useStrings();
  const f = useFormat();
  const { rows, open, closed } = useBook();
  const live = useMarks();

  const lines = useMemo<BookLine[]>(() => rows.map((row) => {
    const raw = row.open
      ? live?.marks[row.structureId]?.unrealized_usd ?? row.unrealized
      : row.realized;
    const amount = raw === null || raw === undefined ? NaN : Number(raw);

    return {
      ...row,
      status: row.open ? t.book.open : t.book.closed,
      openedOn: f.day(row.openedAt),
      entryText: row.entry ? f.premium(row.entry) : t.common.dash,
      exitText: row.exit ? f.premium(row.exit) : t.common.dash,
      pnl: Number.isFinite(amount)
        ? { value: f.money(raw), amount, open: row.open }
        : null,
    };
  }), [rows, live, t, f]);

  return { lines, open, closed };
}
