/**
 * Whether a timestamp can be shown as a time, or has to carry its date.
 *
 * The tape stamped every row with a wall clock alone, so an approval from two days ago
 * read `17:26:19` and sat above one from this afternoon looking exactly like it. That
 * is the panel's own rule broken at the smallest scale: a reading from another day
 * rendered identically to a current one, on the list whose whole job is to say what
 * this agent has been doing.
 *
 * The question is the calendar day, not the elapsed time. 23:50 read at 01:20 is
 * yesterday — ninety minutes old and still needing its date — while 07:00 read at
 * 18:00 is eleven hours old and needs none.
 *
 * No words here, by rule. This decides; `useFormat` spells it.
 */

/** True when the stamp is from a day the reader is no longer in, or cannot be read. */
export function needsDate(ts: string | null | undefined, now: number): boolean {
  if (!ts) return true;
  const at = new Date(ts);
  // Unreadable fails closed, toward the date. It is not evidence of today, and the
  // safe direction is the one that makes a reader look rather than assume.
  if (Number.isNaN(at.getTime())) return true;
  const here = new Date(now);
  return at.getFullYear() !== here.getFullYear()
    || at.getMonth() !== here.getMonth()
    || at.getDate() !== here.getDate();
}


/**
 * A stage's own clock, as `M:SS`, or null for a stamp that cannot be read.
 *
 * The snapshot arrives only when the journal changes and a stage writes nothing for
 * twenty seconds at a time, so without a second hand of its own the desk sat perfectly
 * still through the part it exists to show.
 *
 * Never negative. The stamp is the agent's clock and `now` is the browser's; two
 * machines disagree by a second or so routinely, and a stage that started half a
 * second in the future must read zero rather than counting backwards.
 *
 * Minutes are not wrapped at sixty. A stage running for an hour should never happen,
 * and a clock that silently restarts is worse than a long number.
 */
export function running(ts: string | null | undefined, now: number): string | null {
  if (!ts) return null;
  const at = new Date(ts).getTime();
  if (Number.isNaN(at)) return null;
  const seconds = Math.max(0, Math.floor((now - at) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
