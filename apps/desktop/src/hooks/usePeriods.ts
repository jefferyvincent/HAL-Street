import { useMemo } from "react";

import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface PeriodFigure {
  /** The money, or the dash where the window cannot be measured. */
  value: string;
  /** No figure at all, which is not the same as a figure of zero. */
  missing: boolean;
  /** Null where the sign means nothing: a realized zero is a day nothing closed. */
  sign: number | null;
}

export interface PeriodRow {
  key: string;
  label: string;
  closed: string;
  realized: PeriodFigure;
  marked: PeriodFigure;
}

/**
 * P&L over the windows a trader asks for: today, this week, this month, this year.
 *
 * **Two figures per row, and they are not the same figure.** Realized is what closed
 * trades actually made — exact, off the ledger, and zero on a day the desk held
 * rather than a day it lost, which is why its zero is drawn flat rather than green.
 * Mark-to-market moves with open positions and is what most people mean by "today's
 * P&L".
 *
 * The mark-to-market column is a dash where the journal does not reach back to the
 * start of the window, which is most of them on a young account. That is the honest
 * answer: computing it anyway would give a number labelled MTD that means "since this
 * file was created" — plausible, precise, and false.
 */
export function usePeriods() {
  const t = useStrings();
  const f = useFormat();
  const periods = useConnection((s) => s.snapshot?.periods) ?? [];

  return useMemo(() => {
    const figure = (raw: string | null, zeroIsFlat = false): PeriodFigure => {
      const n = raw === null ? null : Number(raw);
      if (n === null || !Number.isFinite(n)) {
        return { value: t.common.dash, missing: true, sign: null };
      }
      return { value: f.money(n), missing: false, sign: n === 0 && zeroIsFlat ? null : n };
    };

    return {
      rows: periods.map<PeriodRow>((p) => ({
        key: p.period,
        label: t.periods.label[p.period],
        closed: p.closed > 0 ? t.periods.closed(p.closed) : t.periods.noneClosed,
        realized: figure(p.realized_usd, true),
        marked: figure(p.equity_change_usd),
      })),
      // Said once, under the table, and only where a window actually fell short of
      // the journal. Naming the first session it has beats a bare dash in a column.
      shortNote: (() => {
        const since = periods.find((p) => p.since)?.since;
        return periods.some((p) => !p.covered) && since
          ? t.periods.shortNote(since)
          : null;
      })(),
    };
  }, [periods, t, f]);
}
