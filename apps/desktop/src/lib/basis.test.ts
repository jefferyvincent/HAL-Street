import { describe, expect, it } from "vitest";

import { basisState } from "@/lib/basis";

/**
 * "not recorded" against a leg of an order that has not filled yet.
 *
 * Reported live, on the first order this agent placed under the new configuration: the
 * SPY spread rested unfilled at its limit and both legs read `not recorded`, which says
 * the fill happened and we failed to write it down. Nothing had filled. Those are
 * different states and the panel was giving them the same words — the panel's own rule
 * six, on the row where money is.
 */
describe("basisState", () => {
  it("reports the price when there is one", () => {
    expect(basisState("12.65", true)).toBe("known");
  });

  it("says a leg is waiting when the order has not filled", () => {
    expect(basisState(null, false)).toBe("awaiting");
  });

  it("keeps 'not recorded' for a fill that happened and was not written down", () => {
    // The real gap, and the one worth alarming about: a filled order whose price the
    // ledger never captured is a P&L figure computed from a limit rather than a fill.
    expect(basisState(null, true)).toBe("missing");
  });

  it("does not claim a fill is missing before the panel knows whether it filled", () => {
    // `chart` is null for the ~700ms between opening a position and its history
    // arriving. Unknown is its own answer.
    expect(basisState(null, null)).toBe("unknown");
  });

  it("trusts a recorded price even on a structure marked unfilled", () => {
    // A partial fill records what filled. The number is real whatever the flag says,
    // and showing words over a price we hold would be the panel hiding evidence.
    expect(basisState("12.65", false)).toBe("known");
  });
});
