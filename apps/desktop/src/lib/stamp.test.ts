import { describe, expect, it } from "vitest";

import { needsDate } from "@/lib/stamp";

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
