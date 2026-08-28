import { describe, expect, it } from "vitest";
import { stripRoot } from "./names";

describe("a structure's name beside its ticker chip", () => {
  it("drops a leading root, so the ticker is never printed twice", () => {
    expect(stripRoot("QQQ 2026-10-16 765/775 call credit spread", "QQQ"))
      .toBe("2026-10-16 765/775 call credit spread");
  });

  it("leaves a name opened before the root was recorded exactly as it is", () => {
    // Rewriting the ledger to match code written after the trade would be editing a
    // record. The panel shows the underlying from its own field either way.
    expect(stripRoot("2026-10-16 765/775 call credit spread", "QQQ"))
      .toBe("2026-10-16 765/775 call credit spread");
  });

  it("only strips a whole word, never a prefix that happens to match", () => {
    expect(stripRoot("QQQQ 765/775", "QQQ")).toBe("QQQQ 765/775");
  });
});
