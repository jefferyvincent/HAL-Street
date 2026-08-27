import { describe, expect, it } from "vitest";
import { chartShape } from "./chartShape";
import type { Candle, Line, Series } from "@/hooks/useStructureLevels";

const at = (t: number, v: number): Series => ({ time: t, value: v });
const bar = (t: number): Candle =>
  ({ time: t, open: 1, high: 2, low: 0.5, close: 1.5, forming: false });
const level = (key: Line["key"], value: number): Line =>
  ({ key, value, color: "#fff", label: key });

const LEVELS = [level("entry", -1.51), level("target", -0.6), level("stop", -3.0)];

/**
 * The canvas re-fits the time scale when this string changes and leaves it alone when
 * it does not. Everything below is about which of those two a given change deserves.
 */
describe("a reset the reader asked for", () => {
  it("sees a different bar size as a different chart", () => {
    // The reported bug: 15Min → 1Hour → back to AUTO, and the view never returned to
    // what it was on load. Same position, same window, different series entirely.
    const fine = chartShape([at(100, 1), at(160, 1), at(220, 1)], [bar(100)], LEVELS);
    const coarse = chartShape([at(100, 1)], [bar(100)], LEVELS);
    expect(fine).not.toBe(coarse);
  });

  it("sees a different position as a different chart", () => {
    expect(chartShape([at(100, 1)], [bar(100)], LEVELS))
      .not.toBe(chartShape([at(900, 1)], [bar(900)], LEVELS));
  });

  it("sees a new bar arriving as a reason to re-fit", () => {
    expect(chartShape([at(100, 1)], [bar(100)], LEVELS))
      .not.toBe(chartShape([at(100, 1), at(160, 1)], [bar(100), bar(160)], LEVELS));
  });

  it("sees the levels moving", () => {
    // They move when a fill correction rewrites the entry price, and the scale has to
    // contain them — a chart fitted without them is fitted to the wrong thing.
    expect(chartShape([at(100, 1)], [bar(100)], LEVELS))
      .not.toBe(chartShape([at(100, 1)], [bar(100)], [level("entry", -1.6), ...LEVELS.slice(1)]));
  });

  it("distinguishes an empty chart from a one-point one", () => {
    expect(chartShape([], [], [])).not.toBe(chartShape([at(100, 1)], [bar(100)], []));
  });
});

describe("what must not move the view", () => {
  it("ignores the live mark moving the last price", () => {
    // This is what re-fitted the chart every few seconds and undid any scroll.
    expect(chartShape([at(100, 1), at(160, 1.4)], [bar(100)], LEVELS))
      .toBe(chartShape([at(100, 1), at(160, 1.9)], [bar(100)], LEVELS));
  });

  it("ignores the forming candle growing inside its own bucket", () => {
    const growing: Candle = { ...bar(160), high: 9, low: -9, close: 3, forming: true };
    expect(chartShape([at(100, 1)], [bar(100), bar(160)], LEVELS))
      .toBe(chartShape([at(100, 1)], [bar(100), growing], LEVELS));
  });

  it("is stable across identical inputs", () => {
    const s = [at(100, 1), at(160, 2)];
    const c = [bar(100)];
    expect(chartShape(s, c, LEVELS)).toBe(chartShape([...s], [...c], [...LEVELS]));
  });
});

describe("the level fingerprint", () => {
  it("names each level, so two swapping values is a change", () => {
    // `[-1, -2]` and `[-2, -1]` join to different strings only because the key is in
    // there. Values alone would call a target and a stop trading places identical.
    expect(chartShape([], [], [level("target", -1), level("stop", -2)]))
      .not.toBe(chartShape([], [], [level("target", -2), level("stop", -1)]));
  });

  it("survives a structure with no levels recorded", () => {
    expect(() => chartShape([at(100, 1)], [bar(100)], [])).not.toThrow();
  });
});
