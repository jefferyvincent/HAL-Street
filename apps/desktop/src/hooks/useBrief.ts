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
  /** Expectation after friction, or null where nothing was simulated. */
  ev: string | null;
  evUp: boolean;
  /** How often it loses everything, or the words for a structure nobody sampled. */
  tail: string;
}

export interface Brief {
  underlying: string;
  meta: string;
  /** The read the menu was scored against, or null before there is one. */
  signal: string | null;
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
  const sessions = useConnection((s) => s.snapshot?.committees) ?? [];

  return useMemo(() => {
    if (!underlying) return null;
    // The scored table only where it belongs to the deliberation on screen. While one
    // is sitting the last session's table is about a decision already taken.
    const session = live ? null : sessions.find((s) => s.underlying === underlying);
    const menu = menus.find((m) => m.underlying === underlying) ?? null;
    const rows = briefRows({ burn: session?.burn ?? null, menu });
    const burn = session?.burn ?? null;

    return {
      underlying,
      meta: t.committee.brief.meta(rows.length),
      signal: burn
        ? t.committee.brief.signal(
            burn.news_lean ?? t.committee.brief.noNews, burn.price_trend, burn.agreement)
        : null,
      note: burn?.note ?? null,
      rows: rows.map((r) => line(r)),
      empty: rows.length === 0 ? t.committee.brief.empty : null,
    };

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
        ev: r.scenario ? t.committee.brief.ev(f.money(r.scenario.ev_usd)) : null,
        evUp: r.scenario ? Number(r.scenario.ev_usd) >= 0 : false,
        tail: r.scenario
          ? t.committee.brief.tail(f.plain(r.scenario.p_max_loss * 100, 0))
          : t.committee.brief.unsimulated,
      };
    }
  }, [underlying, live, cards, menus, sessions, t, f]);
}
