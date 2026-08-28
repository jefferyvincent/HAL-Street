"""A full position lifecycle, driven through the real loop across many cycles.

Six journal events had never once been written in production: `fill_correction`,
`exit_decision`, `exit`, `divergence`, `halt`, and the marks that feed them. Not
because they were broken — because reaching them takes a *sequence*. An order has to
be accepted, then fill at a different price than its limit, then be re-marked on a
later cycle, then cross a threshold, then be closed, then be absent from the broker's
next position list. Nothing in a unit test spans that, and the single live round trip
this project has done ended before most of it.

So this drives the actual `Agent` — the real `run_cycle`, the real ledger, the real
exit policy, the real gate chain — across a scripted session where each cycle returns
a different broker state. The broker is a stub; everything above it is production
code. That is the point: the bugs this is hunting live in the seams between cycles,
and a stub broker is what makes those seams reachable in 0.1 seconds instead of a
trading week.

What it does not cover, and no offline test can: whether Alpaca actually fills a
closing `mleg` order, and whether its `filled_avg_price` means what we read it to
mean. Those need a live window and are noted as such in the write-up.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import ExitPolicy
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
from halstreet.gates.base import Limits
from halstreet.marketdata.occ import Right, occ
from halstreet.telemetry.journal import Journal

TODAY = date(2026, 8, 26)
FAR = TODAY + timedelta(days=45)
SHORT = occ("SPY", FAR, Right.PUT, Decimal(760))
LONG = occ("SPY", FAR, Right.PUT, Decimal(755))


def spread(qty: int = 1) -> Structure:
    """A 760/755 put credit spread — sold at 760, bought at 755."""
    return Structure(
        name="2026-10-10 760/755 put credit spread",
        legs=(
            Leg(SHORT, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
            Leg(LONG, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),
        ),
        qty=qty,
        limit_price=Decimal("-1.00"),
    )


def position(symbol: str, qty: int) -> dict:
    return {"symbol": symbol, "qty": str(qty), "asset_class": "us_option"}


class ScriptedBroker:
    """A broker that returns a different world on each cycle.

    Only the handful of calls the exit path makes. Everything it returns is shaped
    like Alpaca's real responses, because the code under test parses them.
    """

    def __init__(self) -> None:
        self.equity = Decimal(100000)
        self.positions: list[dict] = []
        self.orders: dict[str, dict] = {}
        self.marks: dict[str, dict] = {}
        self.submitted: list[Structure] = []
        self.option_feed = "indicative"

    # --- what the loop calls ---------------------------------------------------

    async def get_account(self) -> dict:
        return {"equity": str(self.equity), "account_number": "PA-SOAK", "id": "soak",
                "options_buying_power": str(self.equity), "buying_power": str(self.equity * 4)}

    async def get_positions(self) -> list[dict]:
        return list(self.positions)

    async def get_option_snapshot(self, symbols: list[str], **_: object) -> dict:
        return {"snapshots": {s: self.marks[s] for s in symbols if s in self.marks}}

    async def get_order(self, order_id: str) -> dict:
        return self.orders.get(order_id, {})

    async def place_structure(self, structure: Structure, **_: object) -> dict:
        self.submitted.append(structure)
        return {"id": f"order-{len(self.submitted)}", "status": "accepted"}

    # --- scripting helpers -----------------------------------------------------

    def quote(self, symbol: str, bid: str, ask: str) -> None:
        self.marks[symbol] = {"latestQuote": {"bp": bid, "ap": ask},
                              "greeks": {"delta": "-0.20"}, "impliedVolatility": "0.18"}

    def mark_spread_at(self, cost_to_close: str) -> None:
        """Price both legs so buying the spread back costs `cost_to_close` per share.

        Both legs get real two-sided quotes. `mark_structure` refuses to mark a
        structure it can only price part of — a mark from three of four legs is not a
        mark — so a stub that zeroed one leg would exercise the *missing data* path
        and never the exit thresholds it was written for.
        """
        cost = Decimal(cost_to_close)
        short_mid, long_mid = cost + Decimal("0.20"), Decimal("0.20")
        self.quote(SHORT, str(short_mid - Decimal("0.02")), str(short_mid + Decimal("0.02")))
        self.quote(LONG, str(long_mid - Decimal("0.02")), str(long_mid + Decimal("0.02")))


@pytest.fixture
def soak(tmp_path):
    broker = ScriptedBroker()
    journal = Journal.open(tmp_path / "run.jsonl")
    ledger = Ledger.load(tmp_path / "ledger.json")
    agent = Agent(
        broker, writer=None, limits=Limits(), journal=journal, ledger=ledger,
        policy=ExitPolicy(take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200),
                          force_close_dte=5),
        dry_run=False, breaker=CircuitState(baseline_equity=Decimal(100000),
                                            baseline_day=TODAY.isoformat()),
    )
    return agent, broker, journal, ledger


def events(journal: Journal, name: str) -> list[dict]:
    return [e for e in journal.read() if e.get("event") == name]


# --- the lifecycle ----------------------------------------------------------------

def test_a_limit_becomes_a_fill_on_the_next_cycle(soak):
    """Cycle 1 records the limit; cycle 2 learns what it actually filled at.

    The gap this closes is real and was found by a live order: submitted at -1.59,
    filled at -1.60. A penny, and a dollar of error in a single contract's reported
    P&L — always in the flattering direction, because a limit is the worst price you
    were willing to take.
    """
    agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1",
                       entry_price=Decimal("-1.00"), order_id="order-1")
    broker.orders["order-1"] = {"id": "order-1", "status": "filled",
                                "filled_avg_price": "-1.12"}

    assert asyncio.run(agent.refresh_fills()) == 1
    assert ledger.structures[0].entry_price == Decimal("-1.12")

    correction = events(journal, "fill_correction")
    assert len(correction) == 1
    assert correction[0]["side"] == "entry"
    assert correction[0]["limit_price"] == "-1.00"
    assert correction[0]["fill_price"] == "-1.12"

    # Idempotent: a second cycle must not re-report a correction it already made.
    assert asyncio.run(agent.refresh_fills()) == 0
    assert len(events(journal, "fill_correction")) == 1


def test_a_winner_is_taken_at_the_profit_target(soak):
    """Open, mark, wait, mark again, close — across four cycles."""
    agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1",
                       entry_price=Decimal("-1.00"), order_id="order-1")
    broker.positions = [position(SHORT, -1), position(LONG, 1)]
    broker.orders["order-1"] = {"filled_avg_price": "-1.00", "status": "filled"}

    # Cycle 1: worth 0.80 to close — 20% of the credit captured, target is 50%.
    broker.mark_spread_at("0.80")
    decisions = asyncio.run(agent.manage_exits(broker.positions))
    assert decisions and not decisions[0].should_close
    assert ledger.open_structures, "a 20% winner is not a closed trade"

    # Cycle 2: worth 0.40 — 60% captured, past the target.
    broker.mark_spread_at("0.40")
    decisions = asyncio.run(agent.manage_exits(broker.positions))
    assert decisions[0].should_close
    assert decisions[0].action.value == "take_profit"
    assert "60%, target 50%" in decisions[0].reason, decisions[0].reason

    assert not ledger.open_structures, "the ledger must retire what it closed"
    closed = ledger.structures[0]
    assert closed.closed_at
    # Accepted, not filled — a real submission comes back `pending_new`. The realized
    # figure stays None until a later cycle learns the price, rather than being made
    # up from the limit. `test_the_exit_fill_is_corrected_on_a_later_cycle` finishes
    # this trade.
    assert closed.exit_price is None and closed.realized() is None
    assert closed.exit_order_id, "no handle to ask the broker about later"

    assert len(broker.submitted) == 1, "one closing order, not one per leg"
    closing = broker.submitted[0]
    assert len(closing.legs) == 2
    assert all(leg.position_intent.value.endswith("_to_close") for leg in closing.legs)
    # Every leg inverted: what was sold is bought back.
    assert {leg.symbol: leg.side.value for leg in closing.legs} == {SHORT: "buy", LONG: "sell"}

    assert events(journal, "exit_decision")
    closes = [e for e in events(journal, "order") if e["intent"] == "close"]
    assert len(closes) == 1 and closes[0]["submitted"]


def test_a_loser_is_cut_at_the_stop(soak):
    agent, broker, _journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1", entry_price=Decimal("-1.00"))
    broker.positions = [position(SHORT, -1), position(LONG, 1)]

    # Costs 3.10 to close against a 1.00 credit — past the 200% stop.
    broker.mark_spread_at("3.10")
    decisions = asyncio.run(agent.manage_exits(broker.positions))
    assert decisions[0].should_close
    assert decisions[0].action.value == "stop_loss"
    # The close was accepted, not filled — which is what a real submission returns —
    # so realized P&L is not knowable yet and must not be invented.
    assert ledger.structures[0].exit_price is None
    assert ledger.structures[0].realized() is None


def test_the_ledger_and_the_broker_disagreeing_is_reported_not_repaired(soak):
    """The broker wins, always — and the disagreement survives as evidence.

    An agent that quietly rewrites its own books to match is an agent that cannot
    tell you it was wrong.
    """
    _agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1", entry_price=Decimal("-1.00"))
    # Someone closed one leg in the Alpaca dashboard overnight.
    broker.positions = [position(SHORT, -1)]

    divergences = ledger.reconcile(broker.positions)
    assert len(divergences) == 1
    assert divergences[0].symbol == LONG
    assert (divergences[0].expected, divergences[0].actual) == (1, 0)

    journal.divergence(divergences)
    assert events(journal, "divergence")
    # Not repaired: the structure is still open and still claims both legs.
    assert ledger.open_structures[0].legs[LONG] == 1


def test_a_structure_whose_legs_all_vanished_is_marked_closed(soak):
    """Expiry, or a manual close of the whole thing. Only when *every* leg is gone."""
    _agent, _broker, _journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1", entry_price=Decimal("-1.00"))

    # One leg left: a partial disappearance is a divergence for a human, not tidy-up.
    assert ledger.mark_closed_where_flat([position(SHORT, -1)]) == []
    assert ledger.open_structures

    assert len(ledger.mark_closed_where_flat([])) == 1
    assert not ledger.open_structures


def test_the_halt_latches_on_the_daily_loss_and_survives_a_restart(soak, tmp_path):
    """The breaker is only a breaker if it is still tripped after the process dies."""
    agent, broker, journal, _ledger = soak
    broker.equity = Decimal(94000)  # -6%, past the 5% daily limit

    tripped = agent.breaker.observe(asyncio.run(broker.get_account()), asof=TODAY,
                                    daily_loss_limit_pct=Limits().daily_loss_limit_pct)
    assert tripped and agent.breaker.halted
    journal.halt(reason=agent.breaker.halt_reason, equity=str(broker.equity))
    assert events(journal, "halt")

    path = tmp_path / "circuit.json"
    agent.breaker.path = path
    agent.breaker.save()
    assert CircuitState.load(path).halted, "a latch that dies with the process is not a latch"


def test_exits_still_run_while_the_breaker_is_halted(soak):
    """The asymmetry that makes a halt safe rather than dangerous.

    A breaker that blocked exits would trap the book in exactly the drawdown that
    tripped it. Entries stop; getting out never does.
    """
    agent, broker, _journal, ledger = soak
    agent.breaker.halt("daily loss limit breached")
    ledger.record_open(spread(), "SPY", structure_id="s1", entry_price=Decimal("-1.00"))
    broker.positions = [position(SHORT, -1), position(LONG, 1)]
    broker.mark_spread_at("0.30")

    decisions = asyncio.run(agent.manage_exits(broker.positions))
    assert decisions[0].should_close, "a halt must never block the way out"
    assert not ledger.open_structures


def test_a_full_session_end_to_end(soak):
    """Ten cycles: open, correct the fill, drift, hit the target, close, go flat.

    The assertion that matters is the last one — after the whole sequence the ledger
    and the broker agree, with no divergence left over. Every individual step is
    covered above; this is the one that catches a step that only breaks when it
    follows another.
    """
    agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1",
                       entry_price=Decimal("-1.00"), order_id="order-1")
    broker.positions = [position(SHORT, -1), position(LONG, 1)]
    broker.orders["order-1"] = {"filled_avg_price": "-1.05", "status": "filled"}

    prices = ["0.95", "0.90", "0.88", "0.75", "0.70", "0.66", "0.61", "0.58", "0.52", "0.40"]
    closed_on = None
    for i, price in enumerate(prices, start=1):
        broker.mark_spread_at(price)
        decisions = asyncio.run(agent.manage_exits(broker.positions))
        if decisions and decisions[0].should_close:
            closed_on = i
            broker.positions = []          # the close fills; the broker goes flat
            break

    assert closed_on is not None, "a spread marked down to 0.40 must hit a 50% target"
    assert ledger.structures[0].entry_price == Decimal("-1.05"), "the fill, not the limit"
    assert events(journal, "fill_correction")
    assert ledger.reconcile(broker.positions) == [], "flat book, flat ledger, no divergence"

    # And the run is reconstructable from the journal alone.
    kinds = {e["event"] for e in journal.read()}
    assert {"fill_correction", "exit_decision", "order"} <= kinds
    assert [e["intent"] for e in events(journal, "order")] == ["close"]


def test_the_exit_fill_is_corrected_on_a_later_cycle(soak):
    """The defect this harness was written to find, and could only find in sequence.

    `refresh_fills` used to walk `open_structures` only. Two consequences, both silent:
    a position opened and closed inside one session was never corrected at all, and a
    closing order's fill was never fetched under any circumstances. Realized P&L is
    the difference between entry and exit, so a round trip could report a figure
    computed from two limits and no fills.

    That is not hypothetical. This project's one live round trip submitted at -1.59 and
    closed at 1.69, both `pending_new` with no fill attached, and the -$10.00 in the
    report is the difference between two prices nobody traded at.
    """
    agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1",
                       entry_price=Decimal("-1.00"), order_id="order-1")
    broker.positions = [position(SHORT, -1), position(LONG, 1)]

    # Cycle 1: the open fills a penny better than the limit.
    broker.orders["order-1"] = {"filled_avg_price": "-1.05", "status": "filled"}
    broker.mark_spread_at("0.40")
    asyncio.run(agent.manage_exits(broker.positions))

    closed = ledger.structures[0]
    assert not closed.is_open
    assert closed.entry_price == Decimal("-1.05")
    # The close was accepted, not filled: nothing to record yet, and nothing invented.
    assert closed.exit_price is None and not closed.exit_filled
    assert closed.exit_order_id == "order-1" or closed.exit_order_id

    # Cycle 2: the broker now reports what the close actually filled at.
    broker.orders[closed.exit_order_id] = {"filled_avg_price": "0.42", "status": "filled"}
    broker.positions = []
    assert asyncio.run(agent.refresh_fills()) == 1

    assert closed.exit_price == Decimal("0.42") and closed.exit_filled
    # (-0.42 - -1.05) * 100 = 63.00 — from two fills, neither of them a limit.
    assert closed.realized() == Decimal("63.00")

    corrections = {e["side"] for e in events(journal, "fill_correction")}
    assert corrections == {"entry", "exit"}


def test_a_confirmed_fill_is_never_looked_up_again(soak):
    """The flags exist so a fill that equals its limit still counts as answered.

    Without them, a structure whose fill matched its limit exactly would be queried on
    every cycle for the life of the run — the price never changes, so "did it change?"
    can never mean "have we asked?".
    """
    agent, broker, _journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s1",
                       entry_price=Decimal("-1.00"), order_id="order-1")
    broker.orders["order-1"] = {"filled_avg_price": "-1.00", "status": "filled"}

    assert asyncio.run(agent.refresh_fills()) == 0, "no change: the fill matched the limit"
    assert ledger.structures[0].entry_filled, "but it was answered, and must not be re-asked"
    assert ledger.awaiting_fill_price() == []


# --- what a bad response from the broker costs the rest of the book -------------------

def test_a_malformed_fill_price_does_not_abort_the_exit_sweep(soak):
    """One structure's unexpected response must not cost every other structure its exit.

    The failure was three deep and only the first part was obvious. `_close` parsed
    `filled_avg_price` with a bare `Decimal(str(fill))` — undefended, while the
    identical parse in `refresh_fills` was guarded — and it sat *between* the order
    being accepted by the broker and the ledger being told about it. So a single
    malformed figure produced:

      1. an order the broker had taken and a ledger that still called the structure
         open, which is the duplicate close the comment in `_close` exists to prevent;
      2. every structure later in the sweep left unexamined, because the raise escaped
         the `for` loop entirely; and
      3. the loss of `ledger.save()`, which sat after the loop.

    None of it surfaced as an error at the time: `run_once` catches around
    `manage_exits`, so the whole thing read as a quiet cycle.
    """
    agent, broker, _journal, ledger = soak
    for n, sid in enumerate(("s0", "s1", "s2")):
        st = spread()
        ledger.record_open(st, "SPY", structure_id=sid,
                           entry_price=Decimal("-1.00"), order_id=f"e{n}", rationale="r")
        ledger.structures[-1].entry_filled = True

    # The broker answers the second close with something that is not a number.
    calls = {"n": 0}
    original = broker.place_structure

    async def flaky(structure, **kw):
        calls["n"] += 1
        response = await original(structure, **kw)
        response["filled_avg_price"] = "N/A" if calls["n"] == 2 else "1.10"
        return response

    broker.place_structure = flaky
    # All three hold the same legs, so one mark takes every one of them to its
    # profit target: entry was a 1.00 credit and 50% of it is a 0.50 buy-back.
    broker.mark_spread_at("0.40")
    asyncio.run(agent.manage_exits())

    assert calls["n"] == 3, "every structure in the book must get its closing order"
    assert ledger.open_structures == [], "a structure the broker accepted a close for is not open"
    assert Ledger.load(ledger.path).open_structures == [], "and that must survive a restart"


def test_an_unparseable_fill_is_recorded_as_unknown_not_invented(soak):
    # Unknown is the same outcome as absent, which the ledger already handles and
    # `refresh_fills` corrects on a later cycle. Anything else would put a number
    # nobody traded at into a realized P&L.
    agent, broker, journal, ledger = soak
    ledger.record_open(spread(), "SPY", structure_id="s0", entry_price=Decimal("-1.00"),
                       order_id="e0", rationale="r")
    ledger.structures[-1].entry_filled = True

    original = broker.place_structure

    async def bad(structure, **kw):
        response = await original(structure, **kw)
        response["filled_avg_price"] = "not-a-price"
        return response

    broker.place_structure = bad
    broker.mark_spread_at("0.40")
    asyncio.run(agent.manage_exits())

    closed = ledger.structures[0]
    assert not closed.is_open and closed.exit_price is None
    assert closed.realized() is None, "no realized figure from a price that was never read"
    assert any(e.get("event") == "error" and "unparseable" in str(e)
               for e in journal.read()), "the broker sent something odd; say so"


def test_one_structure_failing_to_close_does_not_cost_the_others_their_exit(soak):
    """The isolation, tested on its own terms rather than through the parse bug.

    `_close` already handles the two broker errors it expects. This is the third
    case — anything else — and it is the one that used to abort the whole sweep,
    silently, because `run_once` catches around `manage_exits` and a dead sweep looks
    exactly like a quiet cycle.

    Written separately because the fill-parse fix removes the only trigger currently
    reachable, so a test that goes through it proves nothing about the isolation. This
    raises a type nothing in the exit path claims to handle.
    """
    agent, broker, journal, ledger = soak
    for n, sid in enumerate(("s0", "s1", "s2")):
        ledger.record_open(spread(), "SPY", structure_id=sid,
                           entry_price=Decimal("-1.00"), order_id=f"e{n}", rationale="r")
        ledger.structures[-1].entry_filled = True

    calls = {"n": 0}
    original = broker.place_structure

    async def flaky(structure, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("something nothing here claims to handle")
        return await original(structure, **kw)

    broker.place_structure = flaky
    broker.mark_spread_at("0.40")
    asyncio.run(agent.manage_exits())

    assert calls["n"] == 3, "the third structure must still be offered its exit"
    still_open = {s.structure_id for s in ledger.open_structures}
    assert still_open == {"s1"}, "only the one that actually failed stays open"
    assert any(e.get("event") == "error" and "close_failed" in str(e)
               for e in journal.read()), "a failed exit is the loudest thing in the journal"
