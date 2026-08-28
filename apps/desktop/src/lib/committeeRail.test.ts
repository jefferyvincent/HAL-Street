import { describe, expect, it } from "vitest";
import { railFocus } from "./committeeRail";

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
