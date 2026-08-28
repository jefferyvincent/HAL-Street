import { useMemo } from "react";

import { RAIL_ROWS, railFocus, railList, railScan, type RailLive } from "@/lib/committeeRail";
import { clock, day } from "@/lib/format";
import { useCommittee, type CommitteeCard } from "@/hooks/useCommittee";
import { usePresence } from "@/hooks/usePresence";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";

export interface RailRow {
  key: string;
  underlying: string;
  lean: { label: string; tone: string } | null;
  verdict: { label: string; tone: string };
  gated: { label: string; ok: boolean } | null;
  ago: string;
  /** The one currently being argued, if any. */
  live: boolean;
}

export interface CommitteeRail {
  /** What the desk is doing, in two or three words. Always something. */
  state: string;
  stateTone: string;
  /** When the market is shut, when it opens again. */
  detail: string | null;
  live: RailLive | null;
  rows: RailRow[];
  /** How many deliberations are only on the tab. */
  hidden: number;
  empty: string;
  /** Take the reader to the full argument. */
  openArchive: () => void;
}

/**
 * The committee rail: what the desk is doing, and the deliberations behind it.
 *
 * It showed one card and no state, so after hours it read as a panel with nothing in
 * it rather than a desk waiting for the bell. Two things follow from that.
 *
 * The state line is always present — offline, market closed with the next open, the
 * stage running now, or between cycles. A rail that only speaks when something is
 * happening is indistinguishable from a broken one when nothing is.
 *
 * And it lists the recent deliberations rather than the newest alone. The full
 * argument — catalyst, both cases, the judge's reasoning — stays on the tab, which is
 * the archive; this is the stream. `hidden` is how many are only there.
 */
export function useCommitteeRail(): CommitteeRail {
  const t = useStrings();
  const cards = useCommittee();
  const { kind } = usePresence();
  const market = useConnection((s) => s.snapshot?.market ?? null);
  const inFlight = useConnection((s) => s.snapshot?.in_flight ?? null);
  const setView = useUI((s) => s.setView);

  return useMemo(() => {
    const focus = railFocus(
      cards.map((c) => ({ key: c.key, underlying: c.underlying })),
      inFlight ? { underlying: inFlight.underlying, stage: inFlight.stage } : null,
    );
    // This pass only. The rail listed the newest five whatever their age, so a
    // quiet afternoon put three deliberations from this scan beside two from
    // eighteen hours ago, same weight, same list. The older ones are counted,
    // not dropped — the tab still has every one of them.
    const scan = railScan(cards);
    const { shown, hidden } = railList(scan.shown, RAIL_ROWS);

    const state = kind === "disconnected" ? t.presence.shortDisconnected
      : kind === "closed" ? t.presence.shortClosed
      : kind === "working" ? (inFlight?.stage ?? t.presence.shortIdle)
      : kind === "silent" ? t.presence.shortSilent
      : t.presence.shortIdle;

    const tone = kind === "disconnected" ? "text-fail"
      : kind === "working" ? "text-amber"
      : kind === "silent" ? "text-amber"
      : "text-ink/40";

    const opens = market?.next_open;
    return {
      state,
      stateTone: tone,
      detail: kind === "closed" && opens
        ? t.presence.opensAt(day(opens), clock(opens))
        : null,
      live: focus.live,
      rows: shown.map<RailRow>((c: CommitteeCard) => ({
        key: c.key,
        underlying: c.underlying,
        lean: c.catalyst.lean,
        verdict: c.verdict,
        gated: c.gated,
        ago: c.ago,
        // Only the one actually being argued, which is usually none of them: the
        // agent has moved on by the time a card reaches the screen.
        live: Boolean(focus.live?.onShown) && c.key === focus.key,
      })),
      hidden: hidden + scan.hidden,
      empty: t.committeeRail.none,
      openArchive: () => setView("committee"),
    };
  }, [cards, kind, inFlight, market, t, setView]);
}
