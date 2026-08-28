/**
 * The shape of a deliberation while it is still being had.
 *
 * The committee tab is an archive: one card per session, written when the judge
 * returns. That is right for reading afterwards and useless for watching, because the
 * session takes four model calls and about a minute, and for all of it the tab showed
 * yesterday's argument under a single amber word.
 *
 * The agent now writes a record as each stage finishes, so the panel can name the one
 * running. What it must not do is guess: before any stage has reported there is no
 * evidence a committee is sitting at all — the same point in the cycle looks identical
 * with `--no-committee`, where one call runs and no stage ever lands. So this draws
 * nothing until the agent has said something, and the coarse label speaks until then.
 *
 * No words here, by rule. Keys only; the labels come through `useStrings`.
 */

/** In the order they run. The judge is last and never reports — see `liveStages`. */
export const STAGES = ["catalyst", "debate", "judge"] as const;

export type Stage = (typeof STAGES)[number];
export type StageState = "done" | "running" | "pending";

export interface LiveStage {
  key: Stage;
  state: StageState;
}

/**
 * Which stages are in, which one is working, and which have not started.
 *
 * The stage running is the first that has not reported — not "the one after the last
 * that did". They differ when a record arrives out of order, and the difference
 * matters: filling in a catalyst read the agent never wrote would put a fabricated
 * lean on the one surface whose whole job is to say what is happening now.
 *
 * The judge is done when every stage has reported, which it cannot be from stage
 * records alone — it never writes one, because the full session lands the moment it
 * returns. In practice the card is replaced by that session; the all-done case is here
 * so that a card which outlives it says the work finished rather than inventing a
 * fourth stage to be busy with.
 */
export function liveStages(done: string[]): LiveStage[] {
  if (done.length === 0) return [];
  const finished = new Set(done);
  const running = STAGES.find((stage) => !finished.has(stage));
  return STAGES.map((key) => ({
    key,
    state: finished.has(key) ? "done" : key === running ? "running" : "pending",
  }));
}
