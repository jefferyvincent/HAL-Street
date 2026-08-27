import { useMemo } from "react";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface Stat {
  key: string;
  label: string;
  value: string;
  /** "up" | "down" | null — colour, only where a sign means something. */
  sign: "up" | "down" | null;
  note: string | null;
}

/**
 * The run's headline numbers, derived once.
 *
 * The win rate is the one worth care. It is reported over *closed* structures and
 * says so, because a rate computed over everything the agent holds would improve
 * simply by opening a position — and on a book this small a single trade moves it
 * by fifty points, which is why the raw record leads and the percentage follows in
 * smaller type rather than the other way round.
 *
 * Nothing here is computed from the broker. Every figure comes from the same
 * journal and ledger the report reads, so the panel and `./start.sh report` cannot
 * disagree about what happened.
 */
export function useScoreboard(): Stat[] {
  const t = useStrings();
  const pnl = useConnection((s) => s.snapshot?.pnl);

  return useMemo(() => {
    if (!pnl) return [];
    const num = (v: string | null) => (v === null ? null : Number(v));
    const sign = (v: number | null): "up" | "down" | null =>
      v === null || v === 0 ? null : v > 0 ? "up" : "down";

    const closed = pnl.closed;
    const rate = closed > 0 ? ((pnl.wins / closed) * 100).toFixed(0) : null;

    return [
      {
        key: "total", label: t.scoreboard.total,
        value: money(pnl.total), sign: sign(num(pnl.total)), note: null,
      },
      {
        key: "realized", label: t.scoreboard.realized,
        value: money(pnl.realized), sign: sign(num(pnl.realized)), note: null,
      },
      {
        key: "unrealized", label: t.scoreboard.unrealized,
        value: money(pnl.unrealized), sign: sign(num(pnl.unrealized)),
        note: pnl.open > 0 ? t.scoreboard.unrealizedNote : null,
      },
      {
        key: "record", label: t.scoreboard.record,
        value: closed === 0 ? t.scoreboard.recordNone
                            : t.scoreboard.recordValue(pnl.wins, pnl.losses),
        sign: null,
        note: rate === null ? null : t.scoreboard.rate(rate, closed),
      },
      {
        key: "drawdown", label: t.scoreboard.drawdown,
        value: `${money(pnl.max_drawdown_usd)} (${pnl.max_drawdown_pct}%)`,
        sign: null, note: t.scoreboard.drawdownNote(pnl.equity_samples),
      },
      {
        key: "turns", label: t.scoreboard.turns,
        value: t.scoreboard.turnsValue(pnl.proposals, pnl.passed),
        sign: null, note: t.scoreboard.turnsNote,
      },
      {
        key: "gated", label: t.scoreboard.gated,
        value: t.scoreboard.gatedValue(pnl.approved, pnl.rejected),
        sign: null, note: null,
      },
      {
        key: "orders", label: t.scoreboard.orders,
        value: String(pnl.orders_submitted), sign: null, note: null,
      },
    ];
  }, [pnl, t]);
}

/** Dollars, signed, never rounded away from what the ledger holds. */
function money(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const body = Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return `${n < 0 ? "-" : ""}$${body}`;
}
