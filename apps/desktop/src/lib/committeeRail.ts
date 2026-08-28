/** A deliberation happening right now, and whether it is the one on show. */
export interface RailLive {
  stage: string;
  underlying: string;
  /** True only when the card being shown is the argument currently being had. */
  onShown: boolean;
}

export interface RailFocus {
  /** The deliberation to show, or null before any has finished. */
  key: string | null;
  live: RailLive | null;
}

/**
 * Which deliberation the rail shows, and whether it is happening now.
 *
 * The second half is the part worth having a test for. The rail shows the newest
 * finished session; the agent, meanwhile, has usually moved on to the next underlying
 * — it works through the universe one name at a time. So a pulsing "live" mark over
 * the shown card would be wrong most of the time, claiming an argument is still being
 * had when it concluded a minute ago and the desk is now reading something else.
 *
 * `onShown` is the distinction, and both halves are still reported: the rail can say
 * "QQQ decided, now working on IWM", which is true and is what a reader wants.
 *
 * A cycle in flight before anything has finished still counts. The first deliberation
 * of a run takes about a minute, and a rail blank until it lands would read as broken
 * for exactly as long as the most interesting thing was happening.
 */
export function railFocus(
  sessions: { key: string; underlying: string }[],
  inFlight: { underlying: string; stage: string } | null,
): RailFocus {
  const shown = sessions[0] ?? null;
  const key = shown?.key ?? null;
  if (!inFlight) return { key, live: null };

  const underlying = inFlight.underlying ?? "";
  return {
    key,
    live: {
      stage: inFlight.stage,
      underlying,
      // An unnamed cycle claims nothing. It is between names, not on this one.
      onShown: Boolean(underlying) && underlying === shown?.underlying,
    },
  };
}
