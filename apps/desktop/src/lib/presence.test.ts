import { describe, expect, it } from "vitest";
import { SILENT_AFTER_S, presence } from "./presence";

const LIVE = {
  connected: true,
  marketState: "open" as string | null,
  inFlight: null as string | null,
  quietForS: 5 as number | null,
};

/**
 * What the console says about itself when it is not busy trading.
 *
 * Five states that a single "nothing is happening" would flatten into one, and they
 * call for opposite reactions: a dropped socket is worth fixing now, a shut market is
 * worth ignoring until morning, and a silent agent during the session is the one that
 * should worry somebody.
 */
describe("priority between the states", () => {
  it("reports a dropped connection above everything else", () => {
    // Nothing else on screen can be trusted: the snapshot is whatever arrived last,
    // and the market may have opened, closed and moved since.
    expect(presence({ ...LIVE, connected: false, marketState: "closed" }).kind)
      .toBe("disconnected");
    expect(presence({ ...LIVE, connected: false, inFlight: "deliberating" }).kind)
      .toBe("disconnected");
  });

  it("reports a shut market above a stale agent", () => {
    // Of course nothing has written for hours. That is what closed means, and
    // "no agent running" would read as a fault where there is none.
    expect(presence({ ...LIVE, marketState: "closed", quietForS: 40_000 }).kind)
      .toBe("closed");
  });

  it("says it is working when a cycle is in flight", () => {
    expect(presence({ ...LIVE, inFlight: "deliberating" }).kind).toBe("working");
  });
});

describe("during the session", () => {
  it("is idle between cycles", () => {
    expect(presence({ ...LIVE, quietForS: 30 }).kind).toBe("idle");
  });

  it("calls out an agent that has stopped writing", () => {
    // The one worth noticing. The market is open, the panel is connected, and
    // nothing has scanned — which is a stopped process, not a quiet one.
    expect(presence({ ...LIVE, quietForS: SILENT_AFTER_S + 1 }).kind).toBe("silent");
  });

  it("does not call a long cycle silent", () => {
    expect(presence({ ...LIVE, quietForS: SILENT_AFTER_S }).kind).toBe("idle");
  });

  it("gives a cycle longer than any cycle takes", () => {
    // A committee is four model calls and a judge that has spent fourteen thousand
    // output tokens on a hard one. Minutes, not seconds.
    expect(SILENT_AFTER_S).toBeGreaterThanOrEqual(600);
  });
});

describe("what it refuses to guess", () => {
  it("does not claim the market is shut when nothing said so", () => {
    // A `--once` run never records a session boundary. Announcing a closed market on
    // that silence would be inventing the one fact the panel does not have.
    expect(presence({ ...LIVE, marketState: null, quietForS: 30 }).kind).toBe("idle");
  });

  it("does not call a journal that has never spoken silent", () => {
    // Nothing has written because nothing has run yet, which is a fresh start rather
    // than a stopped agent.
    expect(presence({ ...LIVE, quietForS: null }).kind).toBe("idle");
  });
});
