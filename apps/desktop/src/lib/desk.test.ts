import { describe, expect, it } from "vitest";

import { DESK, deskProgress, deskSeats } from "@/lib/desk";

const state = (seats: ReturnType<typeof deskSeats>) =>
  Object.fromEntries(seats.map((s) => [s.key, s.state]));

const finished = {
  catalystAbsent: false, bullAbsent: false, bearAbsent: false,
  judgeFailed: false, passed: false, gated: true,
};

/**
 * The desk: five seats, always all five, each saying where it is.
 *
 * The tab used to lead with a stack of finished cards, so the screen was mostly
 * sessions from five and eighteen hours ago and the one happening now was a word.
 * These are the rules for the roster that replaced it.
 */
describe("deskSeats", () => {
  it("seats everyone, every time", () => {
    // The shape of the deliberation is the point. A roster that grew a row at a time
    // would say the session was over every time it paused.
    expect(deskSeats({ live: null, session: finished }).map((s) => s.key))
      .toEqual([...DESK]);
  });

  it("has no desk at all before anything has sat", () => {
    expect(deskSeats({ live: null, session: null })).toEqual([]);
  });

  it("works the debate once the catalyst is in", () => {
    expect(state(deskSeats({ live: ["catalyst"], session: null }))).toEqual({
      catalyst: "in", bull: "working", bear: "working",
      judge: "pending", gates: "pending",
    });
  });

  it("works the judge once both researchers are back", () => {
    expect(state(deskSeats({ live: ["catalyst", "debate"], session: null }))).toEqual({
      catalyst: "in", bull: "in", bear: "in",
      judge: "working", gates: "pending",
    });
  });

  it("falls back to the finished session when nothing is in flight", () => {
    expect(state(deskSeats({ live: null, session: finished }))).toEqual({
      catalyst: "in", bull: "in", bear: "in", judge: "in", gates: "in",
    });
  });

  it("does not seat a live desk with the last session's answers", () => {
    // The whole complaint. A live catalyst row showing the previous symbol's read is
    // a real verdict attributed to a deliberation that has not reached it yet.
    const seats = deskSeats({ live: ["catalyst"], session: finished });
    expect(state(seats).bull).toBe("working");
    expect(state(seats).judge).toBe("pending");
  });

  it("treats an empty live list as no evidence a committee is sitting", () => {
    // The same point in a --no-committee cycle looks identical from the journal: one
    // call runs and no stage ever lands. Seating five people on that would be an
    // invention.
    expect(state(deskSeats({ live: [], session: finished })).judge).toBe("in");
  });

  it("says an arm was absent rather than drawing it empty", () => {
    // A missing researcher means the judge decided having heard one side. That is a
    // fact about the decision, not a gap in the display.
    const seats = deskSeats({
      live: null, session: { ...finished, bearAbsent: true, catalystAbsent: true },
    });
    expect(state(seats)).toMatchObject({ catalyst: "absent", bear: "absent", bull: "in" });
  });

  it("marks the gates skipped on a considered pass, not pending", () => {
    // They did not run and never will — nothing was proposed to gate. "Pending" would
    // leave a reader waiting for a verdict that is not coming.
    expect(state(deskSeats({
      live: null, session: { ...finished, passed: true, gated: false },
    })).gates).toBe("skipped");
  });

  it("keeps the gates pending on a proposal that has not reached them", () => {
    expect(state(deskSeats({
      live: null, session: { ...finished, passed: false, gated: false },
    })).gates).toBe("pending");
  });

  it("seats a failed judge as absent", () => {
    expect(state(deskSeats({
      live: null, session: { ...finished, judgeFailed: true, gated: false },
    })).judge).toBe("absent");
  });
});

// --- how far along ------------------------------------------------------------------
//
// A roster of dots says which seat is working and not how much of the deliberation is
// left. HAL's fills a bar toward the final call, and that is most of what makes a
// minute of waiting read as progress rather than as a stopped screen.

describe("deskProgress", () => {
  it("is empty before anyone has reported", () => {
    expect(deskProgress(deskSeats({ live: ["catalyst"], session: null }))).toBeCloseTo(0.2);
  });

  it("counts only the seats that are in", () => {
    // Working is not done. A bar that filled on 'started' would reach the end while
    // the head trader was still thinking, which is the one moment it matters.
    expect(deskProgress(deskSeats({ live: ["catalyst", "debate"], session: null })))
      .toBeCloseTo(0.6);
  });

  it("is full when every seat has reported", () => {
    expect(deskProgress(deskSeats({ live: null, session: finished }))).toBe(1);
  });

  it("is zero with no desk at all rather than dividing by nothing", () => {
    expect(deskProgress([])).toBe(0);
  });

  it("counts a skipped seat as settled", () => {
    // The gates after a considered pass are not outstanding work. Leaving the bar
    // short would say the deliberation never finished, which it did.
    const seats = deskSeats({
      live: null, session: { ...finished, passed: true, gated: false },
    });
    expect(deskProgress(seats)).toBe(1);
  });

  it("counts an absent seat as settled", () => {
    const seats = deskSeats({ live: null, session: { ...finished, bullAbsent: true } });
    expect(deskProgress(seats)).toBe(1);
  });
});
