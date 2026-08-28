import { useMemo } from "react";

import { railFocus, type RailLive } from "@/lib/committeeRail";
import { useCommittee, type CommitteeCard } from "@/hooks/useCommittee";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface CommitteeRail {
  /** The deliberation on show, or null before any has finished. */
  card: CommitteeCard | null;
  live: RailLive | null;
  /** What to say about a cycle running on a name other than the one on show. */
  elsewhere: string | null;
  empty: string;
}

/**
 * The newest deliberation, condensed for the rail, and whether one is happening now.
 *
 * The full argument is a tab; this is the corner-of-the-eye version — which name, what
 * the catalyst read, whether both researchers spoke, what the judge did and what the
 * gates then did with it.
 *
 * `elsewhere` is the honest case and the common one: the agent works through the
 * universe a name at a time, so by the time a deliberation is on the screen it has
 * usually moved on. Saying which name it moved to beats a live mark over a finished
 * argument. See `lib/committeeRail`.
 */
export function useCommitteeRail(): CommitteeRail {
  const t = useStrings();
  const cards = useCommittee();
  const inFlight = useConnection((s) => s.snapshot?.in_flight) ?? null;

  return useMemo(() => {
    const focus = railFocus(
      cards.map((c) => ({ key: c.key, underlying: c.underlying })),
      inFlight ? { underlying: inFlight.underlying, stage: inFlight.stage } : null,
    );
    const card = cards.find((c) => c.key === focus.key) ?? null;
    const live = focus.live;
    return {
      card,
      live,
      elsewhere: live && !live.onShown && live.underlying
        ? t.committeeRail.elsewhere(live.underlying, live.stage)
        : null,
      empty: t.committee.empty,
    };
  }, [cards, inFlight, t]);
}
