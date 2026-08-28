import { useMemo } from "react";

import { clockOf, countdown } from "@/lib/countdown";
import { move } from "@/lib/equity";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useTick } from "@/hooks/useTick";
import { useConnection } from "@/stores/connection";

/** One tick a second. The figure below it changes no faster than that. */
const SECOND = 1000;

export interface Hero {
  /** The account, at the size the room can read. Null when nothing has priced it. */
  equity: string | null;
  equityLabel: string;
  unknown: string;
  /** The move since the first equity sample, from the same helper the chart uses. */
  today: { value: string; up: boolean } | null;
  todayLabel: string;
  stats: string;
  /** What is next and how long until it, or null when nothing can be projected. */
  timer: { label: string; clock: string; units: string[] } | null;
  waiting: { label: string; note: string } | null;
}

/**
 * The console's headline: what the account is worth, and when the agent acts next.
 *
 * The second half is the one that was missing. Every reading on this screen answers
 * "what has happened"; none answered "when does something happen next", so a quiet
 * panel between scans was indistinguishable from a stopped one — which is most of what
 * has been reported about this screen.
 *
 * The move comes through `lib/equity`'s `move`, the same helper the equity chart's
 * header uses. Two definitions of "today" on one screen is one of them being wrong.
 */
export function useHero(): Hero {
  const t = useStrings();
  const f = useFormat();
  const pnl = useConnection((s) => s.snapshot?.pnl ?? null);
  const market = useConnection((s) => s.snapshot?.market ?? null);
  const pass = useConnection((s) => s.snapshot?.pass ?? null);
  const cadence = useConnection((s) => s.snapshot?.cadence ?? null);
  // Only while there is something to count. A console left open all day should not
  // re-render once a second for a timer that is not on screen.
  const now = useTick(market !== null, SECOND);

  return useMemo(() => {
    const shift = pnl ? move(pnl.equity_start, pnl.equity_last) : null;
    const left = countdown({
      marketState: market?.state ?? null,
      nextOpen: market?.next_open ?? null,
      nextClose: market?.next_close ?? null,
      lastScanAt: pass?.at ?? null,
      intervalS: cadence?.interval_s ?? null,
      now,
    });

    return {
      equity: pnl?.equity_last ? f.money(pnl.equity_last) : null,
      equityLabel: t.hero.equity,
      unknown: t.hero.unknown,
      // `move` returns a number or null — null is 'no reading', which is not a
      // flat day and must not render as one.
      today: shift === null ? null : { value: f.signed(shift), up: shift >= 0 },
      todayLabel: t.hero.today,
      stats: t.hero.stats(pnl?.equity_samples ?? 0, pnl?.approved ?? 0,
                          pnl?.open ?? 0, pnl?.orders_submitted ?? 0),
      timer: left && {
        label: t.hero.target[left.target] ?? left.target,
        clock: clockOf(left.seconds),
        // Named under the figure the way a countdown is read, and only for the fields
        // actually on screen — an HRS label over a two-field clock labels nothing.
        units: left.seconds >= 3600
          ? [t.hero.hours, t.hero.mins, t.hero.secs]
          : [t.hero.mins, t.hero.secs],
      },
      waiting: left ? null : { label: t.hero.waiting, note: t.hero.waitingNote },
    };
  }, [pnl, market, pass, cadence, now, t, f]);
}
