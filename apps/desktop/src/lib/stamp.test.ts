import { describe, expect, it } from "vitest";

import { needsDate, running } from "@/lib/stamp";

const at = (iso: string) => new Date(iso).getTime();

/**
 * The tape stamped every row with a wall clock and nothing else, so an approval from
 * two days ago read "17:26:19" — indistinguishable from one this afternoon, on the
 * list whose whole job is to say what this agent has been doing.
 */
describe("needsDate", () => {
  it("leaves a stamp from today as a time", () => {
    expect(needsDate("2026-08-28T17:26:19Z", at("2026-08-28T19:00:00Z"))).toBe(false);
  });

  it("dates a stamp from a day the reader is no longer in", () => {
    expect(needsDate("2026-08-26T17:26:19Z", at("2026-08-28T19:00:00Z"))).toBe(true);
  });

  it("dates yesterday even when it was ninety minutes ago", () => {
    // Elapsed time is the wrong question. 23:50 read at 01:20 is yesterday, and a
    // bare "23:50" on that row is the same lie as one from a week back.
    //
    // Built from local components on purpose. The day that matters is the reader's,
    // so a pair of UTC stamps either side of midnight proves nothing east or west of
    // it — written that way this test passed in UTC and failed in New York.
    const lateLastNight = new Date(2026, 7, 27, 23, 50);
    const earlyToday = new Date(2026, 7, 28, 1, 20);
    expect(needsDate(lateLastNight.toISOString(), earlyToday.getTime())).toBe(true);
  });

  it("does not date a stamp eleven hours old inside the same day", () => {
    expect(needsDate("2026-08-28T07:00:00Z", at("2026-08-28T18:00:00Z"))).toBe(false);
  });

  it("dates a stamp it cannot read rather than passing it off as today", () => {
    // Failing closed: an unreadable timestamp is not evidence of anything, and the
    // safe direction is the one that makes a reader look rather than assume.
    expect(needsDate("not a date", at("2026-08-28T19:00:00Z"))).toBe(true);
  });

  it("dates an empty stamp", () => {
    expect(needsDate("", at("2026-08-28T19:00:00Z"))).toBe(true);
  });
});

// --- a clock that moves --------------------------------------------------------------
//
// The snapshot only arrives when the journal changes, and a stage writes nothing for
// twenty seconds at a time. Without a second hand of its own the desk sat perfectly
// still through the part it exists to show.

describe("running", () => {
  const start = "2026-08-28T19:00:00Z";
  const after = (s: number) => new Date(start).getTime() + s * 1000;

  it("counts from the moment the stage began", () => {
    expect(running(start, after(42))).toBe("0:42");
  });

  it("pads the seconds so the width never jumps", () => {
    // A figure that changes width every ten seconds drags the row beside it around.
    expect(running(start, after(5))).toBe("0:05");
  });

  it("carries into minutes", () => {
    expect(running(start, after(65))).toBe("1:05");
  });

  it("keeps counting past an hour rather than wrapping to zero", () => {
    // It should never get here — a stage is seconds — but a clock that silently
    // restarts is worse than a long number.
    expect(running(start, after(3675))).toBe("61:15");
  });

  it("does not run backwards when the clocks disagree", () => {
    // The stamp is the agent's clock and `now` is the browser's. A stage that started
    // half a second in the future must read zero, not minus one.
    expect(running(start, after(-2))).toBe("0:00");
  });

  it("says nothing for a stamp it cannot read", () => {
    expect(running("not a date", after(10))).toBeNull();
    expect(running(null, after(10))).toBeNull();
  });
});
