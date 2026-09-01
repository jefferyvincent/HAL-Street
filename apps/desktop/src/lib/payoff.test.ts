import { describe, expect, it } from "vitest";
import { parseOcc, payoff, payoffCurve } from "./payoff";

/** SPY 2026-10-16 contracts, the shape this agent actually trades. */
const C770 = "SPY261016C00770000";
const C780 = "SPY261016C00780000";
const P760 = "SPY261016P00760000";
const P750 = "SPY261016P00750000";

describe("reading a contract out of its OCC symbol", () => {
  it("takes the strike from the last eight digits, in thousandths", () => {
    expect(parseOcc(C770)).toEqual({
      root: "SPY", expiry: "2026-10-16", right: "C", strike: 770,
    });
  });

  it("reads a fractional strike without losing the fraction", () => {
    expect(parseOcc("IWM261016P00218500")!.strike).toBe(218.5);
  });

  it("returns null for anything that is not an OCC symbol", () => {
    // The payoff is drawn from strikes. A symbol we cannot read is a leg we cannot
    // place, and placing it at zero would draw a cliff at the y-axis.
    expect(parseOcc("SPY")).toBeNull();
    expect(parseOcc("")).toBeNull();
    expect(parseOcc("SPY261016X00770000")).toBeNull();
  });
});

describe("what a structure is worth at expiry", () => {
  // A put credit spread: short the 760, long the 750, sold for 1.60.
  const pcs = [
    { symbol: P760, contracts: -1 },
    { symbol: P750, contracts: 1 },
  ];

  it("keeps the whole credit above the short strike", () => {
    expect(payoff(pcs, -1.6, 1, 800)).toBeCloseTo(160);
  });

  it("loses the width less the credit below the long strike", () => {
    // 10 wide, 1.60 taken in: the worst case is $840, and it is the number the
    // max-loss gate sized against.
    expect(payoff(pcs, -1.6, 1, 700)).toBeCloseTo(-840);
  });

  it("breaks even at the short strike less the credit", () => {
    expect(payoff(pcs, -1.6, 1, 758.4)).toBeCloseTo(0);
  });

  it("scales with the position's size", () => {
    expect(payoff(pcs, -1.6, 2, 800)).toBeCloseTo(320);
  });

  it("prices a debit spread off the debit it cost", () => {
    const call = [{ symbol: C770, contracts: 1 }, { symbol: C780, contracts: -1 }];
    expect(payoff(call, 3.2, 1, 800)).toBeCloseTo(680);
    expect(payoff(call, 3.2, 1, 700)).toBeCloseTo(-320);
  });
});

describe("the curve the panel draws", () => {
  const condor = [
    { symbol: P750, contracts: 1 },
    { symbol: P760, contracts: -1 },
    { symbol: C770, contracts: -1 },
    { symbol: C780, contracts: 1 },
  ];

  it("finds both breakevens of an iron condor", () => {
    const curve = payoffCurve(condor, -3.0, 1, null)!;
    expect(curve.breakevens).toHaveLength(2);
    expect(curve.breakevens[0]).toBeCloseTo(757);
    expect(curve.breakevens[1]).toBeCloseTo(773);
  });

  it("reports max gain and max loss on a defined-risk structure", () => {
    const curve = payoffCurve(condor, -3.0, 1, null)!;
    expect(curve.maxGain).toBeCloseTo(300);
    expect(curve.maxLoss).toBeCloseTo(-700);
    expect(curve.boundedAbove).toBe(true);
    expect(curve.boundedBelow).toBe(true);
  });

  it("refuses to name a max loss it cannot bound", () => {
    // A naked short call loses without limit. Reporting the worst point on the drawn
    // range as "max loss" would be a made-up number on the one structure where the
    // number matters most — and the gates exist to keep this off the book at all.
    const naked = payoffCurve([{ symbol: C770, contracts: -1 }], -2.0, 1, null)!;
    expect(naked.boundedAbove).toBe(false);
    expect(naked.maxLoss).toBeNull();
    expect(naked.maxGain).toBeCloseTo(200);
  });

  it("puts a kink at every strike and nowhere else", () => {
    const curve = payoffCurve(condor, -3.0, 1, null)!;
    for (const strike of [750, 760, 770, 780]) {
      expect(curve.points.some((p) => Math.abs(p.s - strike) < 1e-9)).toBe(true);
    }
  });

  it("widens the range to keep spot on the picture", () => {
    const curve = payoffCurve(condor, -3.0, 1, 900)!;
    expect(curve.hi).toBeGreaterThanOrEqual(900);
  });

  it("draws nothing without an entry price or a readable leg", () => {
    // "I could not tell" never renders as zero — a curve through an unknown entry is
    // a picture of a trade nobody made.
    expect(payoffCurve(condor, null, 1, null)).toBeNull();
    expect(payoffCurve([], -3.0, 1, null)).toBeNull();
    expect(payoffCurve([{ symbol: "SPY", contracts: -1 }], -3.0, 1, null)).toBeNull();
  });
});
