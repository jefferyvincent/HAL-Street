import { useMemo } from "react";

import { presence, type PresenceKind } from "@/lib/presence";
import { clock, day } from "@/lib/format";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface Presence {
  kind: PresenceKind;
  /** What to say, or null when the console is simply working and needs no banner. */
  message: string | null;
  tone: string;
}

/**
 * What the console says about itself when it is not busy trading.
 *
 * The order between these is the design and lives in `lib/presence`; this turns the
 * answer into words. `idle` and `working` say nothing at all — the panel is fine and
 * a banner announcing that is noise. Only the three that a reader would otherwise
 * mistake for a broken screen get one.
 */
export function usePresence(): Presence {
  const t = useStrings();
  const connected = useConnection((s) => s.connected);
  const market = useConnection((s) => s.snapshot?.market ?? null);
  const inFlight = useConnection((s) => s.snapshot?.in_flight ?? null);
  const cadence = useConnection((s) => s.snapshot?.cadence ?? null);

  return useMemo(() => {
    const { kind } = presence({
      connected,
      marketState: market?.state ?? null,
      inFlight: inFlight?.stage ?? null,
      quietForS: market?.quiet_for_s ?? null,
      // The agent's own cadence decides what counts as too quiet. A fixed threshold
      // is one that is right at exactly one setting of a configurable interval.
      silentAfterS: cadence?.silent_after_s ?? null,
    });

    if (kind === "disconnected") {
      return { kind, message: t.presence.disconnected, tone: "text-fail" };
    }
    if (kind === "closed") {
      // Named in the reader's own clock, from the broker's published next open.
      const opens = market?.next_open;
      return {
        kind,
        message: opens
          ? t.presence.closedUntil(day(opens), clock(opens))
          : t.presence.closed,
        tone: "text-ink/45",
      };
    }
    if (kind === "silent") {
      return { kind, message: t.presence.silent, tone: "text-amber" };
    }
    return { kind, message: null, tone: "" };
  }, [connected, market, inFlight, cadence, t]);
}
