import { describe, expect, it } from "vitest";
import { decide, watch } from "./cues";
import type { ClosedStructure, Market } from "@/types";

const trade = (id: string, realized: string | null): ClosedStructure =>
  ({ structure_id: id, realized_usd: realized } as ClosedStructure);

const market = (state: "open" | "closed", at: string, observed = false): Market =>
  ({ state, at, observed, session_date: "2026-08-27", next_open: null, next_close: null,
     // A live run: the agent is there to write the crossing, which is the only
     // situation a bell should ring in. A boundary the panel merely inferred was
     // never heard by anyone, and there is nothing to sound for it.
     source: "observed", recorded: state, crossed_at: null, until: null,
     stale: false, quiet_for_s: 0 });

describe("the first snapshot", () => {
  it("records what is already there and sounds nothing", () => {
    // Opening a dashboard is not an event. Without this, every winner the account
    // has ever closed rings the till the moment you load the page.
    const w = watch();
    expect(decide(w, [trade("a", "50"), trade("b", "-20")], market("open", "T1"))).toEqual([]);
    expect(w.seen.size).toBe(2);
  });

  it("leaves nothing to replay on the snapshot after it", () => {
    const w = watch();
    decide(w, [trade("a", "50")], market("open", "T1"));
    expect(decide(w, [trade("a", "50")], market("open", "T1"))).toEqual([]);
  });
});

describe("closed trades", () => {
  it("rings the till for a winner and the buzzer for a loser", () => {
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [trade("a", "50")], null)).toEqual(["cashRegister"]);
    expect(decide(w, [trade("a", "50"), trade("b", "-20")], null)).toEqual(["buzzer"]);
  });

  it("sounds each trade once, however often the snapshot repeats it", () => {
    // The snapshot is a complete picture pushed on every change, so a position
    // closed at 10am is in every push for the rest of the day.
    const w = watch();
    decide(w, [], null);
    const book = [trade("a", "50")];
    expect(decide(w, book, null)).toEqual(["cashRegister"]);
    expect(decide(w, book, null)).toEqual([]);
    expect(decide(w, book, null)).toEqual([]);
  });

  it("says nothing about a trade whose fill was never confirmed", () => {
    // Unknown is not a win and not a loss. A sound either way would tell the room
    // something the ledger does not know.
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [trade("a", null)], null)).toEqual([]);
    expect(decide(w, [trade("a", null), trade("b", "nonsense")], null)).toEqual([]);
  });

  it("says nothing about a scratch", () => {
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [trade("a", "0")], null)).toEqual([]);
  });

  it("sounds every trade when a cycle closes several at once", () => {
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [trade("a", "50"), trade("b", "-20"), trade("c", "10")], null))
      .toEqual(["cashRegister", "buzzer", "cashRegister"]);
  });
});

describe("the bell", () => {
  it("rings on the transition and not on the pushes after it", () => {
    const w = watch();
    decide(w, [], market("closed", "T0"));
    expect(decide(w, [], market("open", "T1"))).toEqual(["openingBell"]);
    expect(decide(w, [], market("open", "T1"))).toEqual([]);
    expect(decide(w, [], market("closed", "T2"))).toEqual(["closingBell"]);
  });

  it("stays silent for a session the scheduler merely found on startup", () => {
    // `observed` marks the state it arrived to rather than heard change. Ringing it
    // would claim a bell rang at a moment nobody was listening.
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [], market("open", "T1", true))).toEqual([]);
  });

  it("rings before the trades in the same push", () => {
    // The bell frames what else happened. A till before the closing bell reads as
    // though the trade closed after the session ended.
    const w = watch();
    decide(w, [], market("open", "T0"));
    expect(decide(w, [trade("a", "50")], market("closed", "T1")))
      .toEqual(["closingBell", "cashRegister"]);
  });

  it("says nothing when no scheduled run has recorded a boundary", () => {
    // A `--once` run never observes the market close. Silence beats inferring a
    // session from a clock that knows no holidays.
    const w = watch();
    decide(w, [], null);
    expect(decide(w, [], null)).toEqual([]);
  });

  it("does not re-ring the same record after a reconnect", () => {
    // A reconnect re-reads the journal and pushes the same session event again.
    const w = watch();
    decide(w, [], market("open", "T1"));
    expect(decide(w, [], market("open", "T1"))).toEqual([]);
  });
});

describe("a crossing nobody watched", () => {
  it("does not ring a bell the panel worked out for itself", () => {
    // The failure this prevents: the agent writes `open` at 09:30 and exits at
    // 15:40. At 16:00 the server derives `closed` from the broker's published
    // boundary, the bell key changes, and the panel rings a closing bell for a
    // crossing that happened after everything had stopped running.
    const w = watch();
    const morning: Market = { ...market("open", "T-0930"), source: "observed" };
    expect(decide(w, [], morning)).toEqual([]);            // primes

    const inferred: Market = {
      ...market("closed", "T-0930"), source: "boundary",
      recorded: "open", crossed_at: "2026-08-27 16:00:00-04:00", stale: true,
    };
    expect(decide(w, [], inferred)).toEqual([]);
  });

  it("still rings for one the agent actually recorded", () => {
    const w = watch();
    expect(decide(w, [], market("open", "T1"))).toEqual([]);
    expect(decide(w, [], market("closed", "T2"))).toEqual(["closingBell"]);
  });

  it("does not ring when nothing is writing and nothing has been worked out", () => {
    const w = watch();
    expect(decide(w, [], market("open", "T1"))).toEqual([]);
    const lastSeen: Market = { ...market("closed", "T2"), source: "last-seen", stale: true };
    expect(decide(w, [], lastSeen)).toEqual([]);
  });
});
