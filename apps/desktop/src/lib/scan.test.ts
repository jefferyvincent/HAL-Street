import { describe, expect, it } from "vitest";

import { samePass } from "@/lib/scan";

// --- one scan, not five hours of them ------------------------------------------------
//
// The rail listed the newest five whatever their age, so a quiet afternoon showed three
// sessions from this scan beside two from eighteen hours ago, at the same weight and in
// the same list. Ages were on every row and nobody reads five timestamps to work out
// where the boundary is.

describe("samePass", () => {
  const t = (minutesAgo: number) =>
    new Date(Date.UTC(2026, 7, 28, 19, 0, 0) - minutesAgo * 60_000).toISOString();

  it("keeps the deliberations from the same pass as the newest", () => {
    // A pass over six names takes a minute or two; passes are half an hour apart. The
    // gap between those two numbers is what makes this a clean cut rather than a guess.
    const rows = [{ ts: t(1) }, { ts: t(2) }, { ts: t(3) }];
    expect(samePass(rows).shown).toHaveLength(3);
    expect(samePass(rows).hidden).toBe(0);
  });

  it("drops the pass before it out of the list and counts it", () => {
    const rows = [{ ts: t(1) }, { ts: t(2) }, { ts: t(31) }, { ts: t(1080) }];
    const { shown, hidden } = samePass(rows);
    expect(shown).toHaveLength(2);
    expect(hidden).toBe(2);
  });

  it("shows the last pass even when the last pass was hours ago", () => {
    // Blanking the rail after hours would be a rail that only speaks when something is
    // happening, which is indistinguishable from a broken one when nothing is.
    const rows = [{ ts: t(1080) }, { ts: t(1081) }, { ts: t(2000) }];
    expect(samePass(rows).shown).toHaveLength(2);
  });

  it("has nothing to show and nothing to hide when nothing has sat", () => {
    expect(samePass([])).toEqual({ shown: [], hidden: 0 });
  });

  it("keeps a row whose timestamp cannot be read rather than silently dropping it", () => {
    // A record we cannot place in time is not a record from another pass. Dropping it
    // would make the rail quietly disagree with the tab about how many there are.
    const rows = [{ ts: t(1) }, { ts: "not a date" }];
    expect(samePass(rows).shown).toHaveLength(2);
  });
});
