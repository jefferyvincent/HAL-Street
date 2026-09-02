import { describe, it, expect } from "vitest";
import { armingStep } from "@/lib/arming";

describe("armingStep", () => {
  it("stops listening once the context is actually running", () => {
    expect(armingStep({ muted: false, ready: true })).toBe("stop");
    expect(armingStep({ muted: true, ready: true })).toBe("stop");
  });

  it("tries on a gesture while sound is wanted and not yet running", () => {
    expect(armingStep({ muted: false, ready: false })).toBe("try");
  });

  it("keeps listening rather than arming for someone who asked for silence", () => {
    // Not "stop". Arming audio for a muted panel is the wrong side of the same
    // mistake, but giving up on listening means the gesture that consumed the
    // attempt was spent on nothing — which is how the label stuck at ARMING.
    expect(armingStep({ muted: true, ready: false })).toBe("skip");
  });
});
