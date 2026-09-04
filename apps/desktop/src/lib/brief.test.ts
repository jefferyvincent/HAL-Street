import { describe, expect, it } from "vitest";

import { briefRows, type BriefSource } from "@/lib/brief";

const burnRow = (name: string, fit: "fits" | "against" | "ambient") => ({
  kind: "iron_condor", news_fit: fit, why: "because", name,
  net_price: "-3.56", max_loss_usd: "44.00", max_gain_usd: "356.00",
  prob_of_profit: 0.178, score: "53.9922",
});

const menuRow = (name: string) => ({
  name, kind: "put_credit_spread", net_price: "-0.41",
  max_loss_usd: "359.00", max_gain_usd: "41.00", prob_of_profit: 0.789,
  score: "59.0394",
});

const source = (over: Partial<BriefSource> = {}): BriefSource =>
  ({ burn: null, menu: null, ...over });

/**
 * What the committee was handed. It was written to the journal from the very first
 * session and drawn nowhere, so the tab carried the argument and not the thing being
 * argued about — which is how a screen with four paragraphs on it still reads as dead.
 */
describe("briefRows", () => {
  it("has nothing to show before a menu has been built", () => {
    expect(briefRows(source())).toEqual([]);
  });

  it("reads the burn table when the session has finished", () => {
    const rows = briefRows(source({
      burn: { structures: [burnRow("a condor", "fits")] } as never,
    }));
    expect(rows).toHaveLength(1);
    expect(rows[0]!).toMatchObject({ name: "a condor", fit: "fits", why: "because" });
  });

  it("falls back to the menu while the desk is still sitting", () => {
    // The fit is worked out from the catalyst's read, and that arrives with the
    // finished session. The menu itself is on the journal a stage earlier — which is
    // most of a minute before anything else, and the whole of the dead screen.
    const rows = briefRows(source({ menu: { candidates: [menuRow("a spread")] } as never }));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.name).toBe("a spread");
  });

  it("claims no fit for a structure nobody has scored yet", () => {
    // Not "ambient". Ambient is a verdict — no direction was earned — and a menu the
    // catalyst has not been read against has no verdict of any kind.
    const rows = briefRows(source({ menu: { candidates: [menuRow("a spread")] } as never }));
    expect(rows[0]!.fit).toBeNull();
    expect(rows[0]!.why).toBeNull();
  });

  it("prefers the scored table over the bare menu when it has both", () => {
    const rows = briefRows(source({
      burn: { structures: [burnRow("scored", "against")] } as never,
      menu: { candidates: [menuRow("bare"), menuRow("also bare")] } as never,
    }));
    expect(rows.map((r) => r.name)).toEqual(["scored"]);
  });

  it("survives a menu record that carries no candidates", () => {
    // Older `candidates` events counted without listing, and a cycle that built
    // nothing writes a count of zero. Neither is a reason to throw.
    expect(briefRows(source({ menu: { count: 0 } as never }))).toEqual([]);
  });

  it("keeps the order the ranking put them in", () => {
    const rows = briefRows(source({
      burn: { structures: [burnRow("first", "fits"), burnRow("second", "ambient")] } as never,
    }));
    expect(rows.map((r) => r.name)).toEqual(["first", "second"]);
  });
});
