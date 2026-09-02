import { describe, expect, it } from "vitest";
import { soundLabel } from "./soundLabel";

const WORDS = { off: "MUTED", on: "SOUND", arming: "ARMING" };

describe("what the sound control says it is doing", () => {
  it("says muted whether or not the context is armed", () => {
    // Muted wins: what the audio context is capable of is irrelevant to someone who
    // asked for silence.
    expect(soundLabel({ muted: true, armed: false }, WORDS)).toBe("MUTED");
    expect(soundLabel({ muted: true, armed: true }, WORDS)).toBe("MUTED");
  });

  it("says arming only while the browser has not granted audio yet", () => {
    expect(soundLabel({ muted: false, armed: false }, WORDS)).toBe("ARMING");
  });

  it("says sound once the context is running", () => {
    // The bug this exists to stop: the label read ARMING forever, because readiness
    // was module state that React had no reason to re-render on. A control that
    // describes a state the app left ten minutes ago is worse than no label.
    expect(soundLabel({ muted: false, armed: true }, WORDS)).toBe("SOUND");
  });
});
