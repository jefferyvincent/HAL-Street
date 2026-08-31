import { describe, it, expect } from "vitest";
import { exposureKind, exposureTone } from "@/lib/exposure";
import { STROKE } from "@/constants/theme";

describe("exposureKind", () => {
  it("passes through the four the agent sends", () => {
    for (const k of ["bullish", "bearish", "neutral", "unknown"] as const) {
      expect(exposureKind(k)).toBe(k);
    }
  });

  it("reads anything else as unknown rather than printing it raw", () => {
    // The chip is a fixed-width badge next to a chart. A field the agent grew a new
    // value for should degrade to "direction unknown", not blow the layout out with
    // whatever string arrived.
    expect(exposureKind("sideways")).toBe("unknown");
    expect(exposureKind(null)).toBe("unknown");
    expect(exposureKind(undefined)).toBe("unknown");
    expect(exposureKind("")).toBe("unknown");
  });
});

describe("exposureTone", () => {
  it("colours by what the position wants, not by what it is", () => {
    expect(exposureTone("bullish")).toBe(STROKE.pass);
    expect(exposureTone("bearish")).toBe(STROKE.fail);
  });

  it("leaves no-opinion muted", () => {
    // Neutral is an answer, not a warning. A condor painted red reads as a position
    // in trouble when it is a position doing exactly what it was opened to do.
    expect(exposureTone("neutral")).toBe(STROKE.muted);
    expect(exposureTone("unknown")).toBe(STROKE.muted);
  });
});
