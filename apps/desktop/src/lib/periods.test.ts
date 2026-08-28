import { describe, expect, it } from "vitest";
import { DEFAULT_PERIOD, chosenPeriod } from "./periods";

/**
 * Which window the console is showing. The switcher stores a choice; the server
 * decides which windows exist. Those two can disagree, and this is what happens then.
 */
describe("choosing the window on show", () => {
  const AVAILABLE = ["day", "week", "month", "year", "all"];

  it("shows the one that was chosen", () => {
    expect(chosenPeriod(AVAILABLE, "month")).toBe("month");
  });

  it("opens on today", () => {
    // The window a trader looks at first, and the only one a fresh journal can
    // actually measure mark-to-market over.
    expect(chosenPeriod(AVAILABLE, null)).toBe(DEFAULT_PERIOD);
    expect(DEFAULT_PERIOD).toBe("day");
  });

  it("falls back when the stored choice is not on offer", () => {
    // The choice outlives a reload and the server's list may not. Showing nothing
    // because a remembered key vanished would read as a broken panel.
    expect(chosenPeriod(["day", "all"], "month")).toBe("day");
  });

  it("falls back to the first window when even the default is missing", () => {
    expect(chosenPeriod(["all"], null)).toBe("all");
  });

  it("has nothing to show when the server sent no windows", () => {
    expect(chosenPeriod([], "day")).toBeNull();
    expect(chosenPeriod([], null)).toBeNull();
  });
});
