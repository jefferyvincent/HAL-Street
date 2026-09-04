import { describe, expect, it } from "vitest";
import { flashOf } from "./flash";

/**
 * The tape idiom: a figure lights for a moment when it moves, in the direction it
 * moved. It answers a question a static number cannot — *which* of these just
 * changed — on a screen where most things sit still for minutes at a time.
 */
describe("which way a figure moved", () => {
  it("lights up when it rose", () => {
    expect(flashOf(-19, -12)).toBe("up");
  });

  it("lights down when it fell", () => {
    expect(flashOf(-12, -19)).toBe("down");
  });

  it("crosses zero without confusion", () => {
    // The direction is the move, not the sign of where it landed. A position going
    // from -5 to +3 rose, and the flash says so even though the colours either side
    // of zero are about something else.
    expect(flashOf(-5, 3)).toBe("up");
    expect(flashOf(3, -5)).toBe("down");
  });
});

describe("when it must not light", () => {
  it("stays dark on the first reading", () => {
    // Opening the panel is not a move. Without this every figure on screen flashes
    // the moment it loads, and again on every reconnect.
    expect(flashOf(null, -19)).toBe("");
  });

  it("stays dark when nothing changed", () => {
    // The snapshot is pushed whenever any file changes, so most arrivals carry the
    // same figures. Flashing on every push would make the flash mean "a poll
    // happened" rather than "this moved".
    expect(flashOf(-19, -19)).toBe("");
  });

  it("stays dark when the figure became unknown", () => {
    // A quote went missing. That is not a move and painting it as one would report
    // a loss the position did not take.
    expect(flashOf(-19, null)).toBe("");
  });

  it("stays dark for a figure that was never a number", () => {
    expect(flashOf(null, null)).toBe("");
    expect(flashOf(Number.NaN, 5)).toBe("");
    expect(flashOf(5, Number.NaN)).toBe("");
  });
});
