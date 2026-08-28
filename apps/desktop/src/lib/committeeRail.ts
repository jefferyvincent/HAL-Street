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

/**
 * How far apart two deliberations can be and still belong to the same pass.
 *
 * A pass over six discovered names is a minute or two of model calls; passes are
 * `SCAN_INTERVAL_MINUTES` apart, thirty by default. Ten minutes sits in the gap
 * between those two numbers with room on both sides, which is what makes this a cut
 * rather than a guess — it would take a pass five times slower, or a cadence three
 * times faster, before the two could be confused.
 */
export const SCAN_WINDOW_MS = 10 * 60_000;

/**
 * The deliberations from the most recent pass, and how many are older.
 *
 * The rail listed the newest five whatever their age, so a quiet afternoon showed
 * three sessions from this scan beside two from eighteen hours ago, at the same
 * weight and in the same list. Every row carried its age and nobody reads five
 * timestamps to find the boundary.
 *
 * Anchored on the newest session rather than on the clock, so a rail after hours
 * still shows the last pass in full instead of going blank. A rail that only speaks
 * while something is happening is indistinguishable from a broken one when nothing
 * is, which is the failure the state line above it already exists to prevent.
 *
 * A timestamp that cannot be read keeps its row. It is not evidence of another pass,
 * and dropping it would make the rail quietly disagree with the tab about how many
 * deliberations there have been.
 */
export function railScan<T extends { ts: string }>(
  sessions: T[],
): { shown: T[]; hidden: number } {
  if (sessions.length === 0) return { shown: [], hidden: 0 };
  const stamp = (s: T) => Date.parse(s.ts);
  const newest = sessions.reduce(
    (max, s) => (Number.isNaN(stamp(s)) ? max : Math.max(max, stamp(s))),
    Number.NEGATIVE_INFINITY,
  );
  if (!Number.isFinite(newest)) return { shown: sessions, hidden: 0 };
  const shown = sessions.filter((s) => {
    const at = stamp(s);
    return Number.isNaN(at) || newest - at <= SCAN_WINDOW_MS;
  });
  return { shown, hidden: sessions.length - shown.length };
}
