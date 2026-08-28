import type { PassRow } from "@/types";

/**
 * One name's journey through a cycle, as a track.
 *
 * The panel could say what the agent was doing *right now* and what it had decided
 * *eventually*, with nothing in between. A pass over six discovered names is a minute
 * or two in which four are already settled and one is mid-committee, and none of that
 * shape was anywhere — so watching the agent meant watching one amber word.
 *
 * Every step is always drawn, including the ones that will never run. That is the
 * distinction this table exists for: a name whose menu came up empty has no
 * deliberation missing and none coming, because the loop returns before the committee
 * when there is nothing to argue about. `skipped` says that; `pending` would leave a
 * reader waiting for a stage that is not on its way.
 *
 * No words here, by rule.
 */
export const STEPS = ["tape", "menu", "desk", "gates", "order"] as const;

export type Step = (typeof STEPS)[number];

/**
 * `done` reached and settled · `working` happening now · `pending` still to come ·
 * `skipped` will never run · `empty` ran and produced nothing · `held` cleared but
 * deliberately not acted on · `failed` refused or broke.
 */
export type StepState =
  | "done" | "working" | "pending" | "skipped" | "empty" | "held" | "failed";

export interface Track {
  key: Step;
  state: StepState;
}

/** Where each step of one name's cycle got to. */
export function pipeline(row: PassRow): Track[] {
  const live = Boolean(row.running);
  // `cycle_start` is what puts a name on this table, and that record *is* the read.
  const tape: StepState = "done";

  const menu: StepState = row.error !== null && row.menu === null ? "failed"
    : row.menu === null ? (live ? "working" : "pending")
    : row.menu === 0 ? "empty"
    : "done";

  // Nothing past the menu can happen without one, and nothing past a step that failed.
  const stopped = menu === "empty" || menu === "failed";

  const desk: StepState = stopped ? "skipped"
    : row.proposal !== null ? (row.proposal === "failed" ? "failed" : "done")
    : menu === "done" ? (live ? "working" : "pending")
    : "pending";

  // A considered pass proposes nothing, so the gates never ran and never will. They
  // were not failed and they are not waiting.
  const declined = row.proposal === "passed" || row.proposal === "failed";

  const gates: StepState = stopped || declined ? "skipped"
    : row.gates === "approved" ? "done"
    : row.gates === "rejected" ? "failed"
    : desk === "done" ? (live ? "working" : "pending")
    : "pending";

  // `held` rather than `done`: a rehearsal clears all sixteen gates and stops before
  // submission. Drawing that as a completed order is the panel saying a trade was
  // placed, which is the exact failure the dry-run label exists to prevent.
  const order: StepState = stopped || declined || gates === "failed" ? "skipped"
    : row.order === "submitted" ? "done"
    : row.order === "held" ? "held"
    : gates === "done" ? (live ? "working" : "pending")
    : "pending";

  const track: Record<Step, StepState> = { tape, menu, desk, gates, order };
  // A name the queue has moved past has nothing in progress on it, whatever the
  // records did or did not say. A step still pulsing there claims work nobody is doing.
  return STEPS.map((key) => ({
    key,
    state: !live && track[key] === "working" ? "pending" : track[key],
  }));
}
