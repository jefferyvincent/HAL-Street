import { describe, expect, it } from "vitest";
import { soundLabel } from "./soundLabel";

const WORDS = { off: "MUTED", on: "SOUND" };

describe("what the sound control says it is doing", () => {
  it("says muted when muted", () => {
    expect(soundLabel({ muted: true }, WORDS)).toBe("MUTED");
  });

  it("says sound otherwise, whatever the audio context is doing", () => {
    // There was a third state, ARMING, for "sound is wanted and the browser has not
    // granted it yet". It was honest and it was wrong twice: the readiness flag it
    // read could drift from the context, and each time it drifted the control sat
    // there describing a state the app had left. Two states cannot drift.
    expect(soundLabel({ muted: false }, WORDS)).toBe("SOUND");
  });
});
