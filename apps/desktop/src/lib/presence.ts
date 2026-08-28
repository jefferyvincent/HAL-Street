/**
 * How long the journal may go quiet during the session before it is worth saying so.
 *
 * Longer than any cycle takes. A committee is four model calls and a judge that has
 * spent fourteen thousand output tokens on a hard decision, so a scan is minutes; a
 * quarter of an hour of nothing while the market is open is a stopped process rather
 * than a slow one.
 */
export const SILENT_AFTER_S = 900;

export type PresenceKind = "disconnected" | "closed" | "working" | "silent" | "idle";

export interface PresenceInput {
  /** Whether the panel can reach its own server. */
  connected: boolean;
  /** "open", "closed", or null when nothing has recorded a boundary yet. */
  marketState: string | null;
  /** The stage running now, or null. */
  inFlight: string | null;
  /** Seconds since anything was written, or null if nothing ever has. */
  quietForS: number | null;
}

/**
 * What the console should say about itself when it is not busy trading.
 *
 * Five states, in the order that matters, because a single "nothing is happening"
 * flattens things that call for opposite reactions: a dropped socket is worth fixing
 * now, a shut market is worth ignoring until morning, and a silent agent during the
 * session is the one that should worry somebody.
 *
 * The order is the whole design.
 *
 *   A dropped connection outranks everything, because nothing else on screen can be
 *   trusted — the snapshot is whatever arrived last and the world has moved since.
 *
 *   A shut market outranks a stale agent. Of course nothing has written for hours;
 *   that is what closed means, and reporting it as a stopped process would be a fault
 *   where there is none.
 *
 * Two things it will not guess. An unknown market state is not a closed one — a
 * `--once` run never records a boundary, and announcing a shut market on that silence
 * would invent the single fact the panel does not have. And a journal that has never
 * spoken is a fresh start, not a stopped agent.
 */
export function presence(input: PresenceInput): { kind: PresenceKind } {
  if (!input.connected) return { kind: "disconnected" };
  if (input.marketState === "closed") return { kind: "closed" };
  if (input.inFlight) return { kind: "working" };
  if (input.quietForS !== null && input.quietForS > SILENT_AFTER_S) {
    return { kind: "silent" };
  }
  return { kind: "idle" };
}
