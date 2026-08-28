/**
 * How long the journal may go quiet before it is worth saying so, when the server has
 * not said.
 *
 * A fallback, not the rule. Between passes the agent writes nothing at all — it logs
 * to stdout and sleeps — so healthy silence is about one cadence, and a cadence is
 * configurable. At the thirty-minute default this fixed fifteen minutes announced a
 * stopped process for roughly half of every cycle, on the one banner whose whole job
 * is to be believed. The server now derives it from `SCAN_INTERVAL_MINUTES` and sends
 * it; this stands in only for a snapshot that predates that field.
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
  /** The server's own threshold, derived from the cadence. Null before it sends one. */
  silentAfterS?: number | null;
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
  const silentAfter = input.silentAfterS ?? SILENT_AFTER_S;
  if (input.quietForS !== null && input.quietForS > silentAfter) {
    return { kind: "silent" };
  }
  return { kind: "idle" };
}
