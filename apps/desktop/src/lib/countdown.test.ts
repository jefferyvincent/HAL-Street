import { describe, expect, it } from "vitest";

import { clockOf, countdown } from "@/lib/countdown";

const NOW = new Date("2026-08-28T18:00:00Z").getTime();
const at = (mins: number) => new Date(NOW + mins * 60_000).toISOString();

const input = (over = {}) => ({
  marketState: "open", nextOpen: null, nextClose: at(120),
  lastScanAt: at(-5), intervalS: 1800, now: NOW, ...over,
});

/**
 * A panel that says nothing about when the agent acts next cannot be told apart from a
 * stopped one, which is the thread running through most of this screen's history.
 */
describe("countdown", () => {
  it("counts to the next scan while the market is open", () => {
    expect(countdown(input())).toEqual({ target: "scan", seconds: 25 * 60 });
  });

  it("counts to the open while the market is shut", () => {
    // Nothing will happen until then, so nothing else is worth a timer.
    expect(countdown(input({ marketState: "closed", nextOpen: at(900) })))
      .toEqual({ target: "open", seconds: 900 * 60 });
  });

  it("falls back to the close when nothing has scanned yet", () => {
    expect(countdown(input({ lastScanAt: null })))
      .toEqual({ target: "close", seconds: 120 * 60 });
  });

  it("falls back to the close when the cadence is not known", () => {
    expect(countdown(input({ intervalS: null })))
      .toEqual({ target: "close", seconds: 120 * 60 });
  });

  it("does not count down to a scan that was due in the past", () => {
    // The agent has stopped, and a timer reading DUE for the rest of an afternoon says
    // something is imminent while the console says two panels away that it is not.
    expect(countdown(input({ lastScanAt: at(-90) })))
      .toEqual({ target: "close", seconds: 120 * 60 });
  });

  it("says nothing at all when no session has been recorded", () => {
    // A `--once` run never writes a boundary. Counting down to anything here would
    // invent the one fact the panel does not have.
    expect(countdown(input({ marketState: null }))).toBeNull();
  });

  it("says nothing when the close it would count to has already gone", () => {
    expect(countdown(input({ lastScanAt: null, nextClose: at(-10) }))).toBeNull();
  });

  it("survives a stamp it cannot read", () => {
    // This runs once a second. A throw here takes the console down.
    expect(countdown(input({ lastScanAt: "soon", nextClose: "later" }))).toBeNull();
  });
});

describe("clockOf", () => {
  it("reads as minutes and seconds", () => {
    expect(clockOf(763)).toBe("12:43");
  });

  it("grows an hours field rather than counting past sixty minutes", () => {
    expect(clockOf(3862)).toBe("1:04:22");
  });

  it("keeps a fixed width so the figure never jitters", () => {
    // It ticks once a second beside a number people read at a glance.
    expect(clockOf(5)).toBe("0:05");
    expect(clockOf(65)).toBe("1:05");
  });

  it("floors at zero rather than showing a negative clock", () => {
    expect(clockOf(-30)).toBe("0:00");
  });
});
