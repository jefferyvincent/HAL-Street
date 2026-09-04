import { describe, expect, it } from "vitest";
import { hueOf } from "./hue";

describe("a ticker chip's colour", () => {
  it("is the same for the same symbol every time", () => {
    // Not random and not sequential: a chip that changes colour between sessions
    // stops being a recognisable shape and becomes decoration.
    expect(hueOf("QQQ")).toBe(hueOf("QQQ"));
  });

  it("separates the symbols this agent actually trades", () => {
    const hues = ["QQQ", "SPY", "IWM"].map(hueOf);
    expect(new Set(hues).size).toBe(3);
  });

  it("stays a hue", () => {
    for (const symbol of ["QQQ", "SPY", "IWM", "A", "ZZZZ", "?"]) {
      expect(hueOf(symbol)).toBeGreaterThanOrEqual(0);
      expect(hueOf(symbol)).toBeLessThan(360);
    }
  });
});
