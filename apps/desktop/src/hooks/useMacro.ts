import { useMemo } from "react";

import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface OddsLine {
  key: string;
  question: string;
  pct: string;
  /** Wide of a coin flip in either direction, so a settled question reads as one. */
  settled: boolean;
  depth: string;
}

export interface Macro {
  title: string;
  meta: string;
  note: string;
  rows: OddsLine[];
  /** The words for a pass that could not read a venue, or null. */
  empty: string | null;
}

/**
 * What a venue is charging for the macro questions the headlines argue about.
 *
 * Prices rather than forecasts, and read-only: this agent trades US equity options on
 * Alpaca and nothing else. The note under the panel says so, because a screen showing
 * live odds beside a trading book invites exactly one wrong conclusion.
 *
 * A pass that could not read the venue says so rather than rendering empty. "Could
 * not ask" and "nothing is happening" are different, and only one of them is a reason
 * to stop reading the panel.
 */
export function useMacro(): Macro {
  const t = useStrings();
  const f = useFormat();
  const macro = useConnection((s) => s.snapshot?.macro ?? null);

  return useMemo(() => {
    const odds = macro?.odds ?? [];
    return {
      title: t.agent.macro,
      meta: macro ? t.agent.macroMeta(macro.venue, odds.length, f.ago(macro.at)) : "",
      note: t.agent.macroNote,
      empty: macro ? null : t.agent.macroNone,
      rows: odds.map((o, i) => ({
        key: `${o.question}-${i}`,
        question: o.question,
        pct: f.plain(o.yes_pct, 1),
        // A market at 0.4% is not an open question; drawing it in the same tone as a
        // coin flip would give it the same weight on the page that it has nowhere else.
        settled: o.yes_pct <= 5 || o.yes_pct >= 95,
        depth: t.agent.depth(f.money(o.volume_usd, 0)),
      })),
    };
  }, [macro, t, f]);
}
