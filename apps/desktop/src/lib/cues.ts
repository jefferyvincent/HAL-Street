import type { ClosedStructure, Market } from "@/types";

/** What the desk should be hearing, given what just changed. */
export type Cue = "openingBell" | "closingBell" | "cashRegister" | "buzzer";

/** Everything the decision depends on, so it depends on nothing else. */
export interface Watched {
  /** structure_ids already accounted for. Mutated by `decide`, deliberately. */
  seen: Set<string>;
  /** The bell already sounded, as `state@timestamp`, or null before the first. */
  bell: string | null;
  /** False until a first snapshot has been recorded. */
  primed: boolean;
}

export function watch(): Watched {
  return { seen: new Set(), bell: null, primed: false };
}

export function bellKey(market: Market | null): string | null {
  return market ? `${market.state}@${market.at}` : null;
}

/**
 * Which cues a new snapshot earns, and what to remember afterwards.
 *
 * Pure but for `state`, which it advances — the alternative is returning a new
 * `Watched` and having every caller remember to store it, which is one more thing
 * to get wrong in an effect that runs on every push.
 *
 * Two rules do all the work, and both exist because the snapshot is a *complete*
 * picture rather than a diff:
 *
 *   1. The first snapshot records and sounds nothing. Otherwise opening the panel
 *      rings the till once for every winner the account has ever closed, and does
 *      it again on every reconnect.
 *   2. After that, only what is genuinely new — keyed by `structure_id` for trades,
 *      and by state-and-timestamp for the bell, so re-reading the same record does
 *      not ring it twice.
 *
 * A realized figure of `null` earns no cue at all. Unknown is not a win and not a
 * loss: the exit fill was never confirmed, and a sound either way would tell the
 * room something the ledger does not know.
 */
export function decide(
  state: Watched,
  closed: ClosedStructure[],
  market: Market | null,
): Cue[] {
  const key = bellKey(market);

  if (!state.primed) {
    state.primed = true;
    for (const trade of closed) state.seen.add(trade.structure_id);
    state.bell = key;
    return [];
  }

  const fresh = closed.filter((t) => !state.seen.has(t.structure_id));
  for (const trade of fresh) state.seen.add(trade.structure_id);

  const rang = key !== null && key !== state.bell;
  if (rang) state.bell = key;

  const cues: Cue[] = [];
  // The bell first: it frames whatever else arrived in the same push. Two ways to
  // earn one, and they are different claims about the same moment:
  //
  //   `observed` — the agent was running and wrote the crossing down. `market.observed`
  //   still excludes a state the scheduler merely *found* on startup: it began
  //   mid-session, and there was no crossing to hear.
  //
  //   `boundary` — nobody wrote it down, but the broker had published when it would
  //   happen and that time has now passed. This used to be silent, on the grounds
  //   that the crossing "happened after everything had stopped running" — which
  //   conflated the agent not being there with nobody being there. The person
  //   watching the panel is there, which is who a bell is for, and the market did
  //   genuinely close. The panel already treats that same published figure as good
  //   enough to draw CLOSED in the badge; good enough for the eye and not for the ear
  //   is one fact held at two confidences.
  //
  // What is not a reason to ring is `last-seen`: no boundary in either direction and
  // nothing writing. It cannot flip the state, and if it ever did, silence is the
  // honest sound for not knowing.
  //
  // Opening the panel after a close still sounds nothing. That is `primed`, above,
  // and it was always the rule doing that work.
  const heard = market?.source === "observed" ? !market.observed
    : market?.source === "boundary";
  if (rang && market && heard) {
    cues.push(market.state === "open" ? "openingBell" : "closingBell");
  }
  for (const trade of fresh) {
    const realized = trade.realized_usd === null ? NaN : Number(trade.realized_usd);
    if (!Number.isFinite(realized) || realized === 0) continue;
    cues.push(realized > 0 ? "cashRegister" : "buzzer");
  }
  return cues;
}
