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

/**
 * How many deliberations the rail carries.
 *
 * It is a 200px column beside the thing you are actually reading, and the tab is
 * where the whole argument lives. Enough to see the shape of the last half hour, few
 * enough that it never becomes the thing you are reading.
 */
export const RAIL_ROWS = 5;

/**
 * The newest few deliberations, and how many are only on the tab.
 *
 * The count is the part with a bug in it. `length - limit` goes negative on a short
 * archive and reads as "-3 more"; clamping it at zero is what stops a rail with three
 * sessions offering a link to somewhere with nothing extra in it. The exact-fit case
 * is the one that catches an off-by-one — four sessions and a limit of four must
 * offer nothing, not "1 more".
 */
export function railList<T>(sessions: T[], limit: number): { shown: T[]; hidden: number } {
  return {
    shown: sessions.slice(0, limit),
    hidden: Math.max(0, sessions.length - limit),
  };
}

