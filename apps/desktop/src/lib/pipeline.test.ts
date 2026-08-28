import { describe, expect, it } from "vitest";

import { STEPS, pipeline } from "@/lib/pipeline";

const row = (over: Record<string, unknown> = {}) => ({
  underlying: "SPY", at: "T", spot: "100", menu: null, committee: null,
  proposal: null, gates: null, rejected_by: [], order: null, error: null,
  outcome: "running", running: true, ...over,
} as never);

const track = (r: ReturnType<typeof row>) =>
  Object.fromEntries(pipeline(r).map((s) => [s.key, s.state]));

/**
 * One name's journey through a cycle, drawn as a track. The panel could say what the
 * agent was doing right now and what it decided eventually, with nothing in between —
 * so a pass in which four names were settled and one was mid-committee looked like a
 * single amber word and a wait.
 */
describe("pipeline", () => {
  it("always draws every step", () => {
    // The shape of the cycle is the point: seeing MENU done and DESK working tells you
    // gates and an order are still to come. A track that grew would say the name was
    // finished every time it paused.
    expect(pipeline(row()).map((s) => s.key)).toEqual([...STEPS]);
  });

  it("has read the tape the moment the name is on the list", () => {
    // A `cycle_start` record is what puts it there, and that record *is* the read.
    expect(track(row()).tape).toBe("done");
  });

  it("works the menu until one is built", () => {
    expect(track(row()).menu).toBe("working");
    expect(track(row({ menu: 6 })).menu).toBe("done");
  });

  it("stops the line where the menu came up empty", () => {
    // Not "pending", and this is the distinction that matters most on this table. The
    // loop returns before the committee when nothing was built — no deliberation is
    // missing and none is coming, so a reader waiting for one is waiting forever.
    const t = track(row({ menu: 0, outcome: "no menu", running: false }));
    expect(t.menu).toBe("empty");
    expect(t.desk).toBe("skipped");
    expect(t.gates).toBe("skipped");
    expect(t.order).toBe("skipped");
  });

  it("skips the gates on a considered pass", () => {
    // Nothing was proposed, so there was nothing to gate. It did not fail them.
    const t = track(row({ menu: 6, proposal: "passed", outcome: "passed", running: false }));
    expect(t.desk).toBe("done");
    expect(t.gates).toBe("skipped");
    expect(t.order).toBe("skipped");
  });

  it("fails the gates that refused it, and stops there", () => {
    const t = track(row({ menu: 6, proposal: "proposed", gates: "rejected",
                          rejected_by: ["max-loss"], outcome: "rejected", running: false }));
    expect(t.gates).toBe("failed");
    expect(t.order).toBe("skipped");
  });

  it("holds the order on an approved rehearsal rather than calling it done", () => {
    // A dry run clears all sixteen and stops. "Done" here would be the panel saying a
    // trade was placed, which is the exact failure the dry-run label exists to stop.
    const t = track(row({ menu: 6, proposal: "proposed", gates: "approved",
                          order: "held", outcome: "approved", running: false }));
    expect(t.gates).toBe("done");
    expect(t.order).toBe("held");
  });

  it("completes the line on a submitted order", () => {
    const t = track(row({ menu: 6, proposal: "proposed", gates: "approved",
                          order: "submitted", outcome: "submitted", running: false }));
    expect(t.order).toBe("done");
  });

  it("marks the step it died on when the name errored", () => {
    const t = track(row({ menu: null, error: "chain unavailable",
                          outcome: "error", running: false }));
    expect(t.menu).toBe("failed");
  });

  it("does not leave a step working on a name the agent has moved past", () => {
    // The unfinished case: it started, wrote nothing more, and the queue moved on.
    // A step still pulsing there would claim work that nobody is doing.
    const t = track(row({ outcome: "unfinished", running: false }));
    expect(Object.values(t)).not.toContain("working");
  });
});
