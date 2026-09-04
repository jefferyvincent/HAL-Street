/**
 * Grouping records by the scan that produced them.
 *
 * Two surfaces need this and for the same reason. The committee rail listed the newest
 * five deliberations whatever their age, and the tape listed every decision ever
 * gated — so a quiet afternoon put this scan beside two days ago in one list, at the
 * same weight, with the boundary encoded only in timestamps nobody reads across five
 * rows. Both are lists whose job is to say what the agent is doing.
 *
 * No words here, by rule.
 */

/**
 * How far apart two records can be and still belong to the same pass.
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
export function samePass<T extends { ts: string }>(
  sessions: T[], windowMs: number = SCAN_WINDOW_MS,
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
    return Number.isNaN(at) || newest - at <= windowMs;
  });
  return { shown, hidden: sessions.length - shown.length };
}
