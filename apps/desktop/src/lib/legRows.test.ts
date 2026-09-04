import { describe, expect, it } from "vitest";
import { legRows } from "./legRows";
import type { LegMark, StructureChart } from "@/types";

const SHORT = "QQQ261016C00765000";
const LONG = "QQQ261016C00775000";

const mark = (symbol: string, over: Partial<LegMark> = {}): LegMark => ({
  symbol, signed: -1, contracts: -1, bid: "4.55", ask: "4.65", mid: "4.60",
  basis: "4.51", value_usd: "-460.00", unrealized_usd: "-9.00", ...over,
});

const chart = (over: Partial<StructureChart> = {}): StructureChart => ({
  open: true,
  legs: [
    { symbol: SHORT, signed: -1, contracts: -1, basis: "4.51", exit: null, realized_usd: null },
    { symbol: LONG, signed: 1, contracts: 1, basis: "3", exit: null, realized_usd: null },
  ],
  ...over,
} as StructureChart);

describe("while the history is still being fetched", () => {
  it("fills the whole table from the marks alone", () => {
    // The chart route spawns an MCP subprocess and waits on Alpaca — about seven
    // hundred milliseconds. The marks already carry the recorded fill beside the live
    // mid, so there is nothing to wait for and nothing to spin over.
    const rows = legRows(null, { legs: [mark(SHORT), mark(LONG, { contracts: 1, basis: "3", mid: "3.22", unrealized_usd: "22.00" })] });

    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ symbol: SHORT, basis: "4.51", now: "4.60", pnl: "-9.00" });
    expect(rows[1]).toMatchObject({ contracts: 1, basis: "3", now: "3.22", pnl: "22.00" });
  });

  it("is empty rather than broken when there are no marks either", () => {
    expect(legRows(null, null)).toEqual([]);
    expect(legRows(null, {})).toEqual([]);
    expect(legRows(null, { legs: [] })).toEqual([]);
  });
});

describe("once the history has arrived", () => {
  it("takes the fills from the chart and the prices from the marks", () => {
    // The fills come off the order and never change; the prices do. Each from the
    // source that owns it, so neither can be stale in the other's name.
    const rows = legRows(chart(), { legs: [mark(SHORT, { mid: "4.99", unrealized_usd: "-48.00" })] });

    expect(rows[0]).toMatchObject({ basis: "4.51", now: "4.99", pnl: "-48.00" });
  });

  it("shows a leg the broker could not price without losing its fill", () => {
    const rows = legRows(chart(), { legs: [] });
    expect(rows[0]).toMatchObject({ basis: "4.51", now: null, pnl: null });
  });

  it("keeps the chart's leg order, not the marks'", () => {
    const rows = legRows(chart(), { legs: [mark(LONG), mark(SHORT)] });
    expect(rows.map((r) => r.symbol)).toEqual([SHORT, LONG]);
  });
});

describe("a closed position", () => {
  const done = chart({
    open: false,
    legs: [
      { symbol: SHORT, signed: -1, contracts: -1, basis: "4.51", exit: "2.05", realized_usd: "246.00" },
      { symbol: LONG, signed: 1, contracts: 1, basis: "3", exit: "0.85", realized_usd: "-215.00" },
    ],
  });

  it("shows what it closed at and what it made", () => {
    const rows = legRows(done, null);
    expect(rows[0]).toMatchObject({ basis: "4.51", now: "2.05", pnl: "246.00" });
    expect(rows[1]).toMatchObject({ now: "0.85", pnl: "-215.00" });
  });

  it("ignores a live mark if one somehow exists", () => {
    // There is nothing left to mark. A live price beside a closed round trip is
    // either stale or somebody else's position.
    const rows = legRows(done, { legs: [mark(SHORT, { mid: "9.99", unrealized_usd: "1.00" })] });
    expect(rows[0]).toMatchObject({ now: "2.05", pnl: "246.00" });
  });
});
