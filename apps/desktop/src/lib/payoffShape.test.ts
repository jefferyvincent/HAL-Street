import { describe, expect, it } from "vitest";
import { payoffCurve } from "./payoff";
import { payoffShape } from "./payoffShape";

const CONDOR = [
  { symbol: "SPY261016P00750000", contracts: 1 },
  { symbol: "SPY261016P00760000", contracts: -1 },
  { symbol: "SPY261016C00770000", contracts: -1 },
  { symbol: "SPY261016C00780000", contracts: 1 },
];

const W = 400;
const H = 120;
const curve = () => payoffCurve(CONDOR, -3.0, 1, null)!;

describe("placing a payoff curve in its box", () => {
  it("puts profit above the zero line and loss below it", () => {
    const shape = payoffShape(curve(), W, H, null)!;
    const gain = shape.points.find((p) => p.pnl > 0)!;
    const loss = shape.points.find((p) => p.pnl < 0)!;
    expect(gain.y).toBeLessThan(shape.zeroY);
    expect(loss.y).toBeGreaterThan(shape.zeroY);
  });

  it("keeps the whole curve inside the box", () => {
    const shape = payoffShape(curve(), W, H, null)!;
    for (const p of shape.points) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(W);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(H);
    }
  });

  it("splits the fill at zero so profit and loss can be coloured apart", () => {
    // One path in two colours is not possible; two paths clipped at the zero line is.
    const shape = payoffShape(curve(), W, H, null)!;
    expect(shape.gainArea).toBeTruthy();
    expect(shape.lossArea).toBeTruthy();
  });

  it("marks every strike where the curve bends", () => {
    const shape = payoffShape(curve(), W, H, null)!;
    expect(shape.strikes).toHaveLength(4);
    expect(shape.strikes[0]!.x).toBeLessThan(shape.strikes[3]!.x);
  });

  it("places spot only when there is a spot to place", () => {
    // A marker at a made-up price is worse than no marker: it reads as a measurement.
    expect(payoffShape(curve(), W, H, null)!.spotX).toBeNull();
    const withSpot = payoffShape(curve(), W, H, 765)!;
    expect(withSpot.spotX).toBeGreaterThan(0);
    expect(withSpot.spotX).toBeLessThan(W);
  });

  it("ignores a spot the curve does not cover rather than drawing it off the edge", () => {
    expect(payoffShape(curve(), W, H, 10_000)!.spotX).toBeNull();
  });

  it("draws nothing from nothing", () => {
    expect(payoffShape(null, W, H, null)).toBeNull();
  });
});
