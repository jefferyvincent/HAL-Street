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

describe("a crossing the agent did not write down", () => {
  const inferred = (): Market => ({
    ...market("closed", "T-0930"), source: "boundary",
    recorded: "open", crossed_at: "2026-08-27 16:00:00-04:00", stale: true,
  });

  it("rings for a crossing the panel worked out from the published boundary", () => {
    // This used to be silent, and the reason given was that the crossing "happened
    // after everything had stopped running". That conflated two things: the agent
    // was not there to write it down, and nobody was there at all. The person
    // watching the panel is there — that is who a bell is for — and the market did
    // genuinely close, on the broker's own published time.
    //
    // The panel already treats that figure as good enough to draw CLOSED in the
    // badge. Good enough for the eye and not for the ear is the screen holding two
    // confidences about one fact.
    const w = watch();
    expect(decide(w, [], { ...market("open", "T-0930"), source: "observed" }))
      .toEqual([]);                                        // primes
    expect(decide(w, [], inferred())).toEqual(["closingBell"]);
  });

  it("does not ring for a close that had already happened when the page opened", () => {
    // The case the old gate was really protecting, and `primed` protects it properly:
    // opening a dashboard at six in the evening is not the market closing.
    const w = watch();
    expect(decide(w, [], inferred())).toEqual([]);
  });

  it("does not ring twice for the same worked-out crossing", () => {
    const w = watch();
    decide(w, [], { ...market("open", "T-0930"), source: "observed" });
    expect(decide(w, [], inferred())).toEqual(["closingBell"]);
    expect(decide(w, [], inferred())).toEqual([]);
  });

  it("stays silent for a state nothing has confirmed either way", () => {
    // `last-seen` is the one case with no boundary to reason from in any direction.
    // It cannot flip the state, so it should never reach the bell — and if it ever
    // does, silence is the honest sound for "we do not know".
    const w = watch();
    decide(w, [], { ...market("open", "T1"), source: "observed" });
    expect(decide(w, [], { ...market("closed", "T2"), source: "last-seen" })).toEqual([]);
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
