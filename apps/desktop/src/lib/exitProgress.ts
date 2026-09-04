/**
 * How far a position has travelled from where it was opened toward where it will be
 * closed.
 *
 * The three tiles above this say what the entry, the target and the stop are. None of
 * them says the thing a person actually wants at a glance — whether this trade is
 * nearly done, and which way. That is one number, and it is the same number for a
 * credit structure and a debit one because it is measured from the entry rather than
 * from zero: the direction is whichever level the mark has moved toward.
 *
 * Pure, and measured against the levels the exit policy itself acts on, which arrive
 * from `manager.exit_levels` on the chart payload. Nothing is re-derived here — a
 * second opinion about where the stop is would be a bar that disagrees with the agent.
 */

export interface ExitProgress {
  /** 0–100, clamped. `beyond` says when the true figure was larger. */
  pct: number;
  toward: "target" | "stop" | "neither";
  /** True once the mark has passed the level it was heading for. */
  beyond: boolean;
}

export interface ProgressInput {
  entry: number | null;
  target: number | null;
  stop: number | null;
  now: number | null;
}

export function exitProgress({ entry, target, stop, now }: ProgressInput): ExitProgress | null {
  if (entry === null || target === null || stop === null || now === null) return null;
  if (![entry, target, stop, now].every(Number.isFinite)) return null;

  // A level sitting on the entry price is not a band to measure against, and it has
  // to be caught before the side is chosen: a zero-width target sends the mark down
  // the stop's branch, where it reports a real-looking percentage of the wrong thing.
  if (target === entry || stop === entry) return null;

  if (now === entry) return { pct: 0, toward: "neither", beyond: false };

  // Which way it has gone, in the only terms that hold for both kinds of structure:
  // toward the level that lies on the same side of the entry as the mark now does.
  const towardTarget = (now > entry) === (target > entry);
  const level = towardTarget ? target : stop;
  const travelled = (now - entry) / (level - entry);
  return {
    // Whole percent. It is a "how far along" figure read at a glance, and the third
    // decimal of a division is float noise rather than information.
    pct: Math.round(Math.min(100, Math.abs(travelled) * 100)),
    toward: towardTarget ? "target" : "stop",
    beyond: travelled >= 1,
  };
}
