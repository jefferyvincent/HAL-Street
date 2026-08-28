import { describe, expect, it } from "vitest";
import { nameParts, strategyKind, structureName } from "./strategy";

describe("splitting a structure name", () => {
  it("separates the strategy from the expiry and strikes", () => {
    expect(nameParts("2026-10-16 765/775 call credit spread")).toEqual({
      head: "2026-10-16 765/775",
      strategy: "call credit spread",
    });
  });

  it("handles a four-legged name", () => {
    expect(nameParts("2026-10-16 299/304/310/315 iron condor")).toEqual({
      head: "2026-10-16 299/304/310/315",
      strategy: "iron condor",
    });
  });

  it("keeps a leading ticker in the head where the caller put it", () => {
    // `Holding` strips the root before this sees it; `Tape` does not. Either way the
    // strategy is the tail, and the head is whatever came before it.
    expect(nameParts("QQQ 2026-10-16 765/775 put credit spread").strategy)
      .toBe("put credit spread");
  });
});

describe("names this builder never made", () => {
  it("returns an unrecognised name whole rather than mangling it", () => {
    expect(nameParts("hand written position")).toEqual({
      head: "hand written position", strategy: "",
    });
  });

  it("refuses a tail containing a number rather than splitting mid-name", () => {
    // "spread 2" is not a strategy. Anchoring both ends is what makes this a refusal
    // instead of a split at some arbitrary digit.
    expect(nameParts("2026-10-16 765/775 spread 2").strategy).toBe("");
  });

  it("survives an empty or missing name", () => {
    expect(nameParts("")).toEqual({ head: "", strategy: "" });
    expect(nameParts(undefined as unknown as string).strategy).toBe("");
  });

  it("does not split a name that is only digits", () => {
    expect(nameParts("2026-10-16 765/775").strategy).toBe("");
  });
});

describe("which family a strategy belongs to", () => {
  it.each([
    ["call credit spread", "credit"],
    ["put credit spread", "credit"],
    ["call debit spread", "debit"],
    ["iron condor", "condor"],
    ["broken wing butterfly", "condor"],
    ["something else entirely", "other"],
    ["", "other"],
  ])("reads %s as %s", (strategy, kind) => {
    expect(strategyKind(strategy)).toBe(kind);
  });

  it("is case insensitive", () => {
    expect(strategyKind("CALL CREDIT SPREAD")).toBe("credit");
  });

  it("puts a condor ahead of the credit it also is", () => {
    // "iron condor" is a credit structure and reads as a condor, because the shape is
    // the more useful thing to see at a glance — four legs, not two.
    expect(strategyKind("credit iron condor")).toBe("condor");
  });
});

describe("the whole decision, for the component to render", () => {
  // The component was making three calls and a lookup to arrive at these — the split,
  // the kind, then the class for that kind. That is a rule, and a rule reachable only
  // by mounting React is a rule with no test. One function, four assertions.

  it("hands back the head, the strategy and the class to paint it", () => {
    expect(structureName("QQQ 2026-10-16 765/775 call credit spread", "QQQ")).toEqual({
      head: "2026-10-16 765/775",
      strategy: "call credit spread",
      strategyClass: "text-agent",
    });
  });

  it("leaves the name alone when no root was given", () => {
    // The tape shows the ticker in its own chip and the console strips it; the views
    // disagree, which is why the root is optional rather than assumed.
    expect(structureName("2026-10-16 765/775 iron condor").head).toBe("2026-10-16 765/775");
  });

  it("does not strip a root the name does not start with", () => {
    expect(structureName("2026-10-16 765/775 call credit spread", "SPY").head)
      .toBe("2026-10-16 765/775");
  });

  it("gives an unrecognised name no strategy and no class", () => {
    // Better a plain row than a name broken in an arbitrary place to satisfy a regex.
    expect(structureName("hand written position")).toEqual({
      head: "hand written position", strategy: "", strategyClass: "",
    });
  });

  it("survives an empty name", () => {
    expect(structureName("")).toEqual({ head: "", strategy: "", strategyClass: "" });
  });
});
