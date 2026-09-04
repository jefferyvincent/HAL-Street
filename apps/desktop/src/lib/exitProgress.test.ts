import { describe, expect, it } from "vitest";
import { exitProgress } from "./exitProgress";

// A put credit spread opened for 1.60: target takes half the credit, stop is at
// twice it. Prices are on the system's own convention — negative is a credit — so
// this position wins as the mark rises toward zero.
const LEVELS = { entry: -1.6, target: -0.8, stop: -3.2 };

describe("how far a position has travelled toward its exit", () => {
  it("reads halfway to the target as halfway", () => {
    expect(exitProgress({ ...LEVELS, now: -1.2 })).toEqual({
      pct: 50, toward: "target", beyond: false,
    });
  });

  it("measures against the stop once the mark has gone the other way", () => {
    // -2.4 is halfway from -1.60 to -3.20. Measuring that against the target would
    // report a negative percentage of the wrong band entirely.
    expect(exitProgress({ ...LEVELS, now: -2.4 })).toEqual({
      pct: 50, toward: "stop", beyond: false,
    });
  });

  it("sits at neither end at the entry price", () => {
    expect(exitProgress({ ...LEVELS, now: -1.6 })).toEqual({
      pct: 0, toward: "neither", beyond: false,
    });
  });

  it("says a level has been passed rather than reporting more than all of it", () => {
    // The exit acts on the price, not on this bar. A bar drawn past its own end
    // would say the policy had failed to fire when it simply has not run yet.
    expect(exitProgress({ ...LEVELS, now: -0.4 })).toEqual({
      pct: 100, toward: "target", beyond: true,
    });
    expect(exitProgress({ ...LEVELS, now: -4.0 })).toEqual({
      pct: 100, toward: "stop", beyond: true,
    });
  });

  it("works the same for a debit structure, which wins as the mark rises", () => {
    const debit = { entry: 3.2, target: 4.8, stop: 1.6 };
    expect(exitProgress({ ...debit, now: 4.0 })).toEqual({
      pct: 50, toward: "target", beyond: false,
    });
    expect(exitProgress({ ...debit, now: 2.4 })).toEqual({
      pct: 50, toward: "stop", beyond: false,
    });
  });

  it("answers nothing rather than zero when a figure is missing", () => {
    // "I could not tell" never renders as "at its entry" — a bar at 0% is a claim.
    expect(exitProgress({ ...LEVELS, now: null })).toBeNull();
    expect(exitProgress({ entry: null, target: -0.8, stop: -3.2, now: -1.2 })).toBeNull();
    expect(exitProgress({ entry: -1.6, target: null, stop: -3.2, now: -1.2 })).toBeNull();
  });

  it("refuses a band with no width instead of dividing by it", () => {
    expect(exitProgress({ entry: -1.6, target: -1.6, stop: -3.2, now: -1.2 })).toBeNull();
  });
});
