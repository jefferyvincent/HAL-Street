import { useMemo } from "react";

import { stripRoot } from "@/lib/names";
import { useFormat } from "@/hooks/useFormat";
import { useMarks } from "@/hooks/useMarks";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";
import type { Position } from "@/types";

export interface HoldingRow {
  id: string;
  position: Position;
  symbol: string;
  /** The name with the root taken off, since the chip beside it already says it. */
  name: string;
  qty: number;
  /** The figure itself, for the sign the colour and the arrow read off. */
  pnl: number | null;
  /** That figure as money, or the words for a row nothing could price. */
  value: string;
  /** The agent's own marks, one per cycle, with the live figure on the end. */
  spark: number[];
  dte: string | null;
  /** "priced live" or "priced 4m ago" — never absent, never unlabelled. */
  asOf: string | null;
  fresh: boolean;
}

/**
 * The open book, shaped for the card on the console.
 *
 * The P&L is the broker's where it answered and the agent's own last mark otherwise,
 * never both and always labelled with which — a number whose age is unknown is worth
 * less than a stale one that says so. That choice is made here rather than in the
 * markup, so the label and the figure cannot come apart.
 */
export function useHolding() {
  const t = useStrings();
  const f = useFormat();
  const positions = useConnection((s) => s.snapshot?.positions) ?? [];
  const live = useMarks();
  const open = useUI((s) => s.chart);

  const rows = useMemo<HoldingRow[]>(() => positions.map((p) => {
    const now = live?.marks[p.structure_id];
    const read = p.read;
    const unpriceable = now?.missing?.length ?? 0;
    const raw = now?.unrealized_usd ?? read?.unrealized_usd ?? null;
    const fresh = now?.unrealized_usd != null;
    const pnl = raw == null ? null : Number(raw);

    // The live figure is appended to the history so the line ends where the number
    // beside it says it is — otherwise the last point is a cycle old and visibly
    // disagrees with the P&L.
    const history = (p.marks ?? [])
      .map((m) => Number(m.pnl))
      .filter((n) => Number.isFinite(n));

    return {
      id: p.structure_id,
      position: p,
      symbol: p.underlying,
      name: stripRoot(p.name, p.underlying),
      qty: p.qty,
      pnl,
      value: pnl === null
        ? (unpriceable ? t.console.partial(unpriceable) : t.console.unpriced)
        : f.money(raw),
      spark: fresh && pnl !== null ? [...history, pnl] : history,
      dte: read?.dte != null ? t.console.dte(read.dte) : null,
      asOf: fresh
        ? t.console.asOf(t.console.live)
        : read
          ? t.console.asOf(f.ago(read.as_of))
          : null,
      fresh,
    };
  }), [positions, live, t, f]);

  return { rows, count: rows.length, open };
}
