import { describe, expect, it } from "vitest";
import { COLD_FLOOR, heatCells, heatLevel, heatStyle } from "./heat";

const cell = (symbol: string, mentions: number, status = "scanned", reason?: string) =>
  ({ symbol, mentions, status, headline: `About ${symbol}`, ...(reason ? { reason } : {}) });

/**
 * The heat map's arithmetic.
 *
 * Two channels, deliberately independent: how loud the tape was about a name, and
 * what the agent did about it. Collapsing them would make the map assert things it
 * does not know — a name nobody screened is not a cold name, and a name the screen
 * threw out was often one of the loudest on the page.
 */
describe("the level a cell is drawn at", () => {
  it("fills the ramp for the loudest name in the census", () => {
    expect(heatLevel(9, 9)).toBe(1);
  });

  it("scales everything else against that one, not against a fixed count", () => {
    // A four-mention morning and a forty-mention afternoon must both use the whole
    // ramp. An absolute scale draws every quiet day as one flat cold grid — true,
    // and useless as a map.
    expect(heatLevel(2, 4)).toBeCloseTo(heatLevel(20, 40));
  });

  it("never draws a mentioned name at nothing", () => {
    // The tail is the point of the map. A cell at zero opacity is a cell that is not
    // there, and the map would then show only the shortlist it was built to give
    // context to.
    expect(heatLevel(1, 200)).toBeGreaterThanOrEqual(COLD_FLOOR);
  });

  it("does not divide by an empty census", () => {
    expect(Number.isFinite(heatLevel(0, 0))).toBe(true);
  });

  it("clamps a count above the scale rather than overflowing the ramp", () => {
    // Belt and braces: the server floors `hottest` at 1, so a stale or hand-edited
    // journal is the only way here — and an alpha over 1 renders as a hard block.
    expect(heatLevel(50, 1)).toBe(1);
  });

  it("treats a negative count as no heat rather than as reversed heat", () => {
    expect(heatLevel(-5, 10)).toBe(COLD_FLOOR);
  });
});

describe("what the map is built from", () => {
  it("keeps the loudest names first", () => {
    const cells = heatCells([cell("B", 1), cell("A", 9)], 9);
    expect(cells.map((c) => c.symbol)).toEqual(["A", "B"]);
  });

  it("breaks a tie by symbol so the grid does not reshuffle between polls", () => {
    // The map is repainted every five seconds. Cells that swap places on equal counts
    // make it flicker, and a moving tile is one nobody can point at.
    const cells = heatCells([cell("Z", 3), cell("A", 3)], 3);
    expect(cells.map((c) => c.symbol)).toEqual(["A", "Z"]);
  });

  it("carries the reason a name was refused", () => {
    const cells = heatCells([cell("CYCUW", 4, "refused", "no options listed on it")], 4);
    expect(cells[0]?.reason).toBe("no options listed on it");
  });

  it("gives a scanned cell no reason rather than an empty one", () => {
    expect(heatCells([cell("NVDA", 4)], 4)[0]?.reason).toBeNull();
  });

  it("draws a refused name at its real heat, not at a punished one", () => {
    // It was one of the loudest names on the page — that is a fact about the tape and
    // the map's job is to show the tape. What the agent did about it is the *other*
    // channel, and dimming the heat would smear the two together.
    const cells = heatCells([cell("CYCUW", 9, "refused", "no options")], 9);
    expect(cells[0]?.level).toBe(heatLevel(9, 9));
  });

  it("survives a status it has never heard of", () => {
    // The server sends whatever the journal held, and a journal outlives this file.
    expect(() => heatCells([cell("X", 1, "invented")], 1)).not.toThrow();
  });

  it("draws nothing from an empty census", () => {
    expect(heatCells([], 1)).toEqual([]);
  });
});

describe("the two channels stay separate", () => {
  it("gives the three outcomes three different treatments at one heat", () => {
    const styles = ["scanned", "refused", "not-reached"].map((s) =>
      JSON.stringify(heatStyle(1, s)));
    expect(new Set(styles).size).toBe(3);
  });

  it("gives one outcome two different treatments at two heats", () => {
    expect(heatStyle(1, "scanned")).not.toEqual(heatStyle(COLD_FLOOR, "scanned"));
  });

  it("returns colours a browser will accept", () => {
    const style = heatStyle(0.5, "scanned");
    expect(style.backgroundColor).toMatch(/^hsl\(/);
    expect(style.color).toMatch(/^hsl\(/);
  });
});
