import { useMemo } from "react";

import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { chosenPeriod } from "@/lib/periods";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";

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
  /** The one the switcher is on. Exactly one row carries this, or none. */
  active: boolean;
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
 * The mark-to-market figure is a dash where the journal does not reach back to the
 * start of the window, which is most of them on a young account. That is the honest
 * answer: computing it anyway would give a number labelled MTD that means "since this
 * file was created" — plausible, precise, and false.
 *
 * One window is shown at a time and the rest are a row of switches — five rows of two
 * figures each is a table to read, and a trader wants a number to glance at. Which one
 * is showing is decided by `lib/periods.chosenPeriod`, where the disagreement between
 * a remembered choice and the server's offer is five assertions from a test.
 */
export function usePeriods() {
  const t = useStrings();
  const f = useFormat();
  const periods = useConnection((s) => s.snapshot?.periods) ?? [];

  const wanted = useUI((s) => s.pnlPeriod);
  const choose = useUI((s) => s.setPnlPeriod);

  return useMemo(() => {
    const active = chosenPeriod(periods.map((p) => p.period), wanted);
    const shown = periods.find((p) => p.period === active) ?? null;
    const since = periods.find((p) => p.since)?.since;
    const figure = (raw: string | null, zeroIsFlat = false): PeriodFigure => {
      const n = raw === null ? null : Number(raw);
      if (n === null || !Number.isFinite(n)) {
        return { value: t.common.dash, missing: true, sign: null };
      }
      return { value: f.money(n), missing: false, sign: n === 0 && zeroIsFlat ? null : n };
    };

    const rows = periods.map<PeriodRow>((p) => ({
      key: p.period,
      label: t.periods.label[p.period],
      closed: p.closed > 0 ? t.periods.closed(p.closed) : t.periods.noneClosed,
      realized: figure(p.realized_usd, true),
      marked: figure(p.equity_change_usd),
      active: p.period === active,
    }));

    return {
      rows,
      choose,
      // The window on show, decided here rather than found again in the markup.
      // Null only when the server sent no windows at all.
      showing: rows.find((r) => r.active) ?? null,
      // Said once, under the figures, and only when the window on show is actually
      // the one that fell short. Naming the first session the journal has beats a
      // bare dash with no explanation — and saying it beside a window that *is*
      // covered would explain a gap that is not there.
      shortNote: shown && !shown.covered && since ? t.periods.shortNote(since) : null,
    };
  }, [periods, t, f, wanted, choose]);
}
