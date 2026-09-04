import { describe, expect, it } from "vitest";
import { sparkGeometry } from "./spark";

describe("the P&L sparkline on a holding", () => {
  it("draws nothing from one reading", () => {
    // One point is a dot, and a dot drawn as a line asserts a trend nobody measured.
    expect(sparkGeometry([12], 100, 20)).toBeNull();
    expect(sparkGeometry([], 100, 20)).toBeNull();
  });

  it("reads its direction off the last point, not the first", () => {
    expect(sparkGeometry([-30, -10, 5], 100, 20)!.up).toBe(true);
    expect(sparkGeometry([30, 10, -5], 100, 20)!.up).toBe(false);
  });

  it("rules break-even only where the line has been on both sides of it", () => {
    // On a position that has only ever lost, a rule along the top edge says nothing
    // and crowds the shape it is meant to frame.
    expect(sparkGeometry([-30, -10, -5], 100, 20)!.zeroY).toBeNull();
    expect(sparkGeometry([-30, 10], 100, 20)!.zeroY).not.toBeNull();
  });

  it("places a flat line rather than dividing by its zero range", () => {
    const flat = sparkGeometry([4, 4, 4], 100, 20)!;
    for (const point of flat.line.split(" ")) {
      expect(Number(point.split(",")[1])).toBeGreaterThan(0);
      expect(Number(point.split(",")[1])).toBeLessThan(20);
    }
  });

  it("ends the line where the dot sits, so the two cannot disagree", () => {
    const spark = sparkGeometry([-19, -4, 11], 104, 26)!;
    expect(spark.line.split(" ").at(-1)).toBe(`${spark.dot.x.toFixed(1)},${spark.dot.y.toFixed(1)}`);
  });
});
