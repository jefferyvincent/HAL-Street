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
