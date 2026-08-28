import { describe, expect, it } from "vitest";
import { RAIL_ROWS, railFocus, railList, railScan } from "./committeeRail";

const SESSIONS = [
  { key: "QQQ@2", underlying: "QQQ" },   // newest first, as the server sends them
  { key: "SPY@1", underlying: "SPY" },
];

/**
 * Which deliberation the rail shows, and whether it is happening now.
 *
 * The trap is the second half. A finished card under a pulsing "live" dot is a lie
 * whenever the agent has moved on to a different underlying — and it moves on every
 * cycle, so the wrong answer here would be wrong most of the time.
 */
describe("what the rail is looking at", () => {
  it("shows the newest deliberation", () => {
    expect(railFocus(SESSIONS, null).key).toBe("QQQ@2");
  });

  it("says nothing is running when nothing is", () => {
    expect(railFocus(SESSIONS, null).live).toBeNull();
  });

  it("marks the shown card live when the agent is on that underlying", () => {
    const focus = railFocus(SESSIONS, { underlying: "QQQ", stage: "deliberating" });
    expect(focus.key).toBe("QQQ@2");
    expect(focus.live).toEqual({ stage: "deliberating", underlying: "QQQ", onShown: true });
  });

  it("does not mark it live when the agent has moved to another name", () => {
    // The card is QQQ's finished deliberation; the desk is now reading IWM. Pulsing
    // over the QQQ card would say that argument is still being had.
    const focus = railFocus(SESSIONS, { underlying: "IWM", stage: "deliberating" });
    expect(focus.key).toBe("QQQ@2");
    expect(focus.live?.onShown).toBe(false);
    expect(focus.live?.underlying).toBe("IWM");
  });

  it("does not claim the card when the running cycle names no underlying", () => {
    expect(railFocus(SESSIONS, { underlying: "", stage: "reading the tape" })?.live?.onShown)
      .toBe(false);
  });
});

describe("before anything has deliberated", () => {
  it("has no card and says so", () => {
    expect(railFocus([], null)).toEqual({ key: null, live: null });
  });

  it("still reports a cycle in flight, so the rail is not blank on the first scan", () => {
    // The first deliberation of a run takes a minute or so. A rail that showed
    // nothing until it finished would read as broken for exactly as long as the most
    // interesting thing was happening.
    const focus = railFocus([], { underlying: "SPY", stage: "reading the tape" });
    expect(focus.key).toBeNull();
    expect(focus.live).toEqual({ stage: "reading the tape", underlying: "SPY", onShown: false });
  });
});

describe("how much of the archive the rail carries", () => {
  const many = Array.from({ length: 12 }, (_, i) => ({ key: `k${i}`, underlying: "SPY" }));

  it("shows the newest few and counts the rest", () => {
    const { shown, hidden } = railList(many, 4);
    expect(shown.map((s) => s.key)).toEqual(["k0", "k1", "k2", "k3"]);
    expect(hidden).toBe(8);
  });

  it("hides nothing when everything fits", () => {
    const { shown, hidden } = railList(many.slice(0, 3), 4);
    expect(shown).toHaveLength(3);
    expect(hidden).toBe(0);
  });

  it("hides nothing when the count is exactly the limit", () => {
    // The off-by-one this exists for: a "1 more" link to a tab holding nothing new.
    expect(railList(many.slice(0, 4), 4).hidden).toBe(0);
  });

  it("copes with an empty archive", () => {
    expect(railList([], 4)).toEqual({ shown: [], hidden: 0 });
  });

  it("keeps the rail short enough to sit beside a view", () => {
    // It is a 200px column next to the thing you are actually reading. The tab is
    // where the whole argument lives; this is the corner of the eye.
    expect(RAIL_ROWS).toBeLessThanOrEqual(6);
  });
});

// --- one scan, not five hours of them ------------------------------------------------
//
// The rail listed the newest five whatever their age, so a quiet afternoon showed three
// sessions from this scan beside two from eighteen hours ago, at the same weight and in
// the same list. Ages were on every row and nobody reads five timestamps to work out
// where the boundary is.

describe("railScan", () => {
  const t = (minutesAgo: number) =>
    new Date(Date.UTC(2026, 7, 28, 19, 0, 0) - minutesAgo * 60_000).toISOString();

  it("keeps the deliberations from the same pass as the newest", () => {
    // A pass over six names takes a minute or two; passes are half an hour apart. The
    // gap between those two numbers is what makes this a clean cut rather than a guess.
    const rows = [{ ts: t(1) }, { ts: t(2) }, { ts: t(3) }];
    expect(railScan(rows).shown).toHaveLength(3);
    expect(railScan(rows).hidden).toBe(0);
  });

  it("drops the pass before it out of the list and counts it", () => {
    const rows = [{ ts: t(1) }, { ts: t(2) }, { ts: t(31) }, { ts: t(1080) }];
    const { shown, hidden } = railScan(rows);
    expect(shown).toHaveLength(2);
    expect(hidden).toBe(2);
  });

  it("shows the last pass even when the last pass was hours ago", () => {
    // Blanking the rail after hours would be a rail that only speaks when something is
    // happening, which is indistinguishable from a broken one when nothing is.
    const rows = [{ ts: t(1080) }, { ts: t(1081) }, { ts: t(2000) }];
    expect(railScan(rows).shown).toHaveLength(2);
  });

  it("has nothing to show and nothing to hide when nothing has sat", () => {
    expect(railScan([])).toEqual({ shown: [], hidden: 0 });
  });

  it("keeps a row whose timestamp cannot be read rather than silently dropping it", () => {
    // A record we cannot place in time is not a record from another pass. Dropping it
    // would make the rail quietly disagree with the tab about how many there are.
    const rows = [{ ts: t(1) }, { ts: "not a date" }];
    expect(railScan(rows).shown).toHaveLength(2);
  });
});
