import { describe, expect, it } from "vitest";
import { MAX_CHIPS, newsChips } from "./newsChips";

/**
 * Which symbols a ticker item shows.
 *
 * The strip used to draw one thing: the underlyings whose own reads picked an article
 * up. That was right while every article came from a per-symbol read. Now half of them
 * come from the market-wide census, which was fetched for no symbol in particular —
 * so those items had nothing to draw and went past unlabelled, which is precisely the
 * variety the reader was looking for.
 */
describe("what a ticker item is labelled with", () => {
  it("shows the underlyings that actually read it, when there are any", () => {
    // Which of our own names picked a story up is a fact about the desk, and it beats
    // the publisher's tag list — "SPY and QQQ both read this" is the more useful
    // thing to know about a macro story than "the publisher tagged twelve tickers".
    expect(newsChips(["SPY", "QQQ"], ["SPY", "QQQ", "IWM", "DIA"]))
      .toEqual(["SPY", "QQQ"]);
  });

  it("falls back to the publisher's tags when no read picked it up", () => {
    expect(newsChips([], ["NVDA", "AMD"])).toEqual(["NVDA", "AMD"]);
  });

  it("caps the tags so one macro story cannot fill the strip", () => {
    // A roundup carries a dozen tickers. Twelve chips on one item is a wall the
    // reader scrolls past, and it crowds out the next three stories.
    const many = Array.from({ length: 12 }, (_, i) => `S${i}`);
    expect(newsChips([], many)).toHaveLength(MAX_CHIPS);
  });

  it("does not cap the reads, because there are only ever a few", () => {
    // These are our own scanned names, not a publisher's tag list. Truncating them
    // would hide that a third underlying also read the story.
    const roots = Array.from({ length: MAX_CHIPS + 2 }, (_, i) => `R${i}`);
    expect(newsChips(roots, [])).toHaveLength(roots.length);
  });

  it("keeps the publisher's order rather than sorting it", () => {
    // The tag list is ordered by the publisher, and the first is usually the subject.
    expect(newsChips([], ["NVDA", "AMD", "INTC"])).toEqual(["NVDA", "AMD", "INTC"]);
  });

  it("draws nothing when there is nothing to draw", () => {
    expect(newsChips([], [])).toEqual([]);
  });

  it("drops blanks rather than rendering an empty chip", () => {
    expect(newsChips([], ["NVDA", "", "  "])).toEqual(["NVDA"]);
  });

  it("does not repeat a symbol the publisher listed twice", () => {
    expect(newsChips([], ["NVDA", "NVDA", "AMD"])).toEqual(["NVDA", "AMD"]);
  });

  it("survives a record written before either field existed", () => {
    // The journal outlives this file, and an older event has neither key.
    expect(newsChips(undefined, undefined)).toEqual([]);
  });
});
