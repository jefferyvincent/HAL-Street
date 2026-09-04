/** Which way a figure just moved, for the moment after it moved. */
export type Flash = "up" | "down" | "";

/**
 * The tape idiom: a figure lights for a moment when it moves, in the direction it
 * moved.
 *
 * It answers the one question a static number cannot — *which* of these just changed —
 * on a screen where most things sit still for minutes at a time.
 *
 * Three cases must stay dark, and each is a way the flash would come to mean nothing.
 * The first reading is not a move, or every figure lights on load and again on every
 * reconnect. An unchanged figure is not a move, and the snapshot is pushed whenever
 * any file changes, so most arrivals carry the same numbers — flashing on those would
 * make it mean "a poll happened". And a figure that has become unknown is not a move
 * either: a missing quote painted as a fall reports a loss the position did not take.
 *
 * The direction is the move, not the sign of where it landed. A position going from
 * -5 to +3 rose; the colours either side of zero are about something else.
 */
export function flashOf(previous: number | null, next: number | null): Flash {
  if (previous === null || next === null) return "";
  if (!Number.isFinite(previous) || !Number.isFinite(next)) return "";
  if (next === previous) return "";
  return next > previous ? "up" : "down";
}
