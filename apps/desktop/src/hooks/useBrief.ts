import { useMemo } from "react";

import { briefRows, type BriefRow } from "@/lib/brief";
import { useCommittee } from "@/hooks/useCommittee";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface BriefLine {
  key: string;
  name: string;
  /** FITS / AGAINST / AMBIENT, or the word for one nobody has scored yet. */
  fit: string;
  fitTone: string;
  /** Why it sits that way, or null on an unscored row. */
  why: string | null;
  facts: string[];
  /** Expectation after friction at both volatilities, or null where none was run. */
  ev: string | null;
  evUp: boolean;
  /** Whether the two forecasts reach the same verdict, where there are two. */
  verdict: string | null;
  /** How often it loses everything, or the words for a structure nobody sampled. */
  tail: string;
}

export interface Brief {
  underlying: string;
  meta: string;
  /** The read the menu was scored against, or null before there is one. */
  signal: string | null;
  /**
   * What the daily chain makes of direction on this name, and whether that read
   * reaches as far as the structures below it. Null where nothing measured it.
   */
  persistence: { text: string; reach: string; inReach: boolean } | null;
  note: string | null;
  rows: BriefLine[];
  empty: string | null;
}

/**
 * The menu the committee was handed, for whichever name the desk is on.
 *
 * Keyed off the desk rather than off the newest anything, so the brief and the seats
 * are always about the same deliberation. A menu for one symbol beside an argument
 * about another is the same failure as a stale verdict on a live row, and harder to
 * spot because both halves are real.
 */
export function useBrief(underlying: string, live: boolean): Brief | null {
  const t = useStrings();
  const f = useFormat();
  const cards = useCommittee();
  const menus = useConnection((s) => s.snapshot?.menus) ?? [];
  const views = useConnection((s) => s.snapshot?.views) ?? [];
  const sessions = useConnection((s) => s.snapshot?.committees) ?? [];

  return useMemo(() => {
    if (!underlying) return null;
    // The scored table only where it belongs to the deliberation on screen. While one
    // is sitting the last session's table is about a decision already taken.
    const session = live ? null : sessions.find((s) => s.underlying === underlying);
    const menu = menus.find((m) => m.underlying === underlying) ?? null;
    const rows = briefRows({ burn: session?.burn ?? null, menu });
    const burn = session?.burn ?? null;
    const read = views.find((v) => v.underlying === underlying)?.persistence ?? null;
    // The longest hold on this menu. A chain informative for two days says nothing
    // about a 49-day structure, and quoting it beside one would be the panel lending
    // a measurement to a question it does not reach.
    const hold = Math.max(0, ...rows.map((r) => r.dte ?? 0));

    return {
      underlying,
      meta: t.committee.brief.meta(rows.length),
      signal: burn
        ? t.committee.brief.signal(
            burn.news_lean ?? t.committee.brief.noNews, burn.price_trend, burn.agreement)
        : null,
      note: burn?.note ?? null,
      persistence: read && {
        text: t.committee.brief.persistence(read.label, read.current_state,
                                            f.plain(read.repeats_pct, 0),
                                            f.plain(read.base_rate_pct, 0)),
        reach: read.informative_for_days >= hold
          ? t.committee.brief.reach(read.informative_for_days)
          : t.committee.brief.outOfReach,
        inReach: read.informative_for_days >= hold,
      },
      rows: rows.map((r) => line(r)),
      empty: rows.length === 0 ? t.committee.brief.empty : null,
    };

    /** The two expectancies, and what their agreement means. */
    function expectancy(out: BriefRow["scenario"]) {
      const implied = out?.at_implied ?? null;
      const realized = out?.at_realized ?? null;
      if (!implied && !realized) {
        return { ev: null, evUp: false, verdict: null,
                 tail: t.committee.brief.unsimulated };
      }
      const both = implied && realized;
      const one = implied ?? realized!;
      return {
        ev: both
          ? t.committee.brief.evPair(f.money(implied.ev_usd), f.money(realized.ev_usd))
          : t.committee.brief.evOne(f.money(one.ev_usd),
              implied ? t.committee.brief.basisImplied : t.committee.brief.basisRealized),
        // Coloured on the market's own volatility where there is one: that is the
        // number the structure was actually priced against.
        evUp: Number(one.ev_usd) >= 0,
        verdict: out?.agree === null || out?.agree === undefined ? null
          : out.agree ? t.committee.brief.agree : t.committee.brief.disagree,
        tail: t.committee.brief.tail(f.plain(one.p_max_loss * 100, 0)),
      };
    }

    function line(r: BriefRow): BriefLine {
      return {
        key: r.key,
        name: r.name,
        fit: (r.fit && t.committee.brief.fit[r.fit]) || t.committee.brief.unscored,
        fitTone: r.fit === "fits" ? "text-pass border-pass/40"
          : r.fit === "against" ? "text-fail border-fail/40"
          : r.fit === "ambient" ? "text-ink/45 border-line"
          : "text-ink/25 border-line",
        why: r.why,
        facts: [
          t.committee.brief.pop(f.plain(r.pop * 100, 0)),
          t.committee.brief.risk(f.money(r.maxLoss, 0), f.money(r.maxGain, 0)),
          t.committee.brief.score(f.plain(r.score, 1)),
        ],
        // Expectation after the round trip, which is the number the desk keeps
        // declining trades over and was reasoning about in prose. Null rather than
        // zero where nothing was simulated — an unmeasured expectation and a flat one
        // are not the same claim.
        // Both, never averaged. Short premium pays exactly when implied exceeds what
        // realizes, so a structure positive at one and negative at the other is not an
        // ambiguous read — it is the trade thesis stated as two numbers.
        ...expectancy(r.scenario),
      };
    }
  }, [underlying, live, cards, menus, sessions, views, t, f]);
}
