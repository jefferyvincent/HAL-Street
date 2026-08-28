/**
 * The committee desk: five seats, and where each one is right now.
 *
 * Adapted from HAL's cognition roster, which is the shape this was asked to look
 * like — a fixed list of desk members in the order they speak, a dot each, and their
 * verdict written in as it lands. HAL scopes it to the run in progress and shows
 * nothing otherwise; a conversational agent can do that, because a run starts when
 * someone asks. This one scans on a cadence, so it falls back to the last session
 * that sat — stamped as such by the caller, never mixed into a live one.
 *
 * That last clause is the rule with a bug behind it. The tab led with a stack of
 * finished cards, so most of the screen was sessions from five and eighteen hours ago
 * while the one actually happening was a single word. Filling a live desk from the
 * previous session would be the same failure wearing the new design: a real verdict,
 * attributed to a deliberation that has not reached it yet.
 *
 * No words here, by rule. Keys and states; the labels come through `useStrings`.
 */

/** In the order they speak. The gates are not the committee — they are what it faces. */
export const DESK = ["catalyst", "bull", "bear", "judge", "gates"] as const;

export type Seat = (typeof DESK)[number];

/**
 * `in` reported and has something to say · `working` running now · `pending` has not
 * started and will · `absent` ran and produced nothing · `skipped` never ran and
 * never will.
 *
 * Five rather than three because the last two are different facts and the panel has
 * to say which. A researcher that failed is not one that is still thinking, and gates
 * that were never given a proposal are not gates a reader should wait for.
 */
export type SeatState = "in" | "working" | "pending" | "absent" | "skipped";

export interface DeskSeat {
  key: Seat;
  state: SeatState;
}

export interface FinishedSession {
  catalystAbsent: boolean;
  bullAbsent: boolean;
  bearAbsent: boolean;
  judgeFailed: boolean;
  /** The judge declined. Nothing was proposed, so the gates never ran. */
  passed: boolean;
  /** The gates returned a verdict on it. */
  gated: boolean;
}

export interface DeskInput {
  /**
   * Committee stages reported for the deliberation in flight. Empty or null means
   * none is — and empty is the honest answer for the first twenty seconds of every
   * cycle, and for the whole of one run with `--no-committee`.
   */
  live: string[] | null;
  session: FinishedSession | null;
}

/** Where each seat is, live if a committee is sitting and from the record if not. */
export function deskSeats({ live, session }: DeskInput): DeskSeat[] {
  if (live && live.length > 0) return sitting(live);
  if (!session) return [];
  return seated(session);
}

/** A deliberation in progress. Only what this one has produced. */
function sitting(live: string[]): DeskSeat[] {
  const done = new Set(live);
  const catalyst = done.has("catalyst");
  const debate = done.has("debate");
  return [
    { key: "catalyst", state: catalyst ? "in" : "working" },
    { key: "bull", state: debate ? "in" : catalyst ? "working" : "pending" },
    { key: "bear", state: debate ? "in" : catalyst ? "working" : "pending" },
    { key: "judge", state: debate ? "working" : "pending" },
    // Deterministic and instant once there is something to gate. There is no waiting
    // to report here, only a turn that has not come.
    { key: "gates", state: "pending" },
  ];
}

/** A deliberation that finished. What each seat actually did. */
function seated(s: FinishedSession): DeskSeat[] {
  return [
    { key: "catalyst", state: s.catalystAbsent ? "absent" : "in" },
    { key: "bull", state: s.bullAbsent ? "absent" : "in" },
    { key: "bear", state: s.bearAbsent ? "absent" : "in" },
    { key: "judge", state: s.judgeFailed ? "absent" : "in" },
    { key: "gates", state: s.gated ? "in" : s.passed ? "skipped" : "pending" },
  ];
}
