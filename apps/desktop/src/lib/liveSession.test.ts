import { describe, expect, it } from "vitest";

import { STAGES, liveStages } from "@/lib/liveSession";

/**
 * The committee tab showed finished cards and nothing else, so the slowest and most
 * interesting minute of a cycle — four model calls deep — was a blank amber word.
 * These are the rules for the card drawn while it is still happening.
 */
describe("liveStages", () => {
  it("draws nothing before a stage has finished", () => {
    // A `candidates` record means a deliberation is *about* to start, and from that
    // record alone there is no telling whether a committee is sitting or one call is
    // running. Drawing three stages there would invent a shape nobody established.
    expect(liveStages([])).toEqual([]);
  });

  it("runs the stage after the last one that finished", () => {
    expect(liveStages(["catalyst"])).toEqual([
      { key: "catalyst", state: "done" },
      { key: "debate", state: "running" },
      { key: "judge", state: "pending" },
    ]);
  });

  it("puts the judge to work once both researchers are back", () => {
    expect(liveStages(["catalyst", "debate"])).toEqual([
      { key: "catalyst", state: "done" },
      { key: "debate", state: "done" },
      { key: "judge", state: "running" },
    ]);
  });

  it("leaves nothing running when every stage is in", () => {
    // The judge never writes a stage record — the full session lands instead — but a
    // card that invents a fourth stage to be busy with would be worse than one that
    // simply says the work is done.
    const stages = liveStages([...STAGES]);
    expect(stages.every((s) => s.state === "done")).toBe(true);
  });

  it("ignores a stage it has never heard of", () => {
    // Forward compatibility in the safe direction: a newer agent naming a stage this
    // build does not know must not shift the ones it does.
    expect(liveStages(["catalyst", "rebuttal"])).toEqual([
      { key: "catalyst", state: "done" },
      { key: "debate", state: "running" },
      { key: "judge", state: "pending" },
    ]);
  });

  it("does not treat a later stage as proof of an earlier one", () => {
    // Out of order should not silently fill in a catalyst read that never happened;
    // the stage that has not reported is the one running, whatever came after it.
    expect(liveStages(["debate"])).toEqual([
      { key: "catalyst", state: "running" },
      { key: "debate", state: "done" },
      { key: "judge", state: "pending" },
    ]);
  });
});
