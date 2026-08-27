"""Getting per-leg fills onto the ledger, including for positions already held.

The per-leg prices were always on the order; nothing was reading them. That makes the
backfill the interesting half of this feature — the position open when it was written
had a confirmed net fill, an `entry_filled` flag already True, and no legs, which is a
state `refresh_fills` is structurally unable to reach: it is bounded by exactly that
flag.

So there are two passes over one order, and these tests exist to keep them from being
merged back into one by someone who notices they both call `get_order`.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from halstreet.agent.breaker import CircuitState
from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.agent.loop import Agent
from halstreet.agent.manager import ExitPolicy
from halstreet.execution.mcp_client import MCPError
from halstreet.gates.base import Limits
from halstreet.telemetry.journal import Journal

SHORT, LONG = "QQQ261016C00765000", "QQQ261016C00775000"
FILLS = {"legs": [{"symbol": SHORT, "filled_avg_price": "4.51"},
                  {"symbol": LONG, "filled_avg_price": "3"}]}


class Broker:
    """Answers `get_order`, and counts how often it is asked."""

    option_feed = "indicative"

    def __init__(self, order=None, error=None):
        self.order = order if order is not None else {
            "id": "ord-1", "status": "filled", "filled_avg_price": "-1.51", **FILLS}
        self.error = error
        self.asked: list[str] = []

    async def get_order(self, order_id):
        self.asked.append(order_id)
        if self.error:
            raise self.error
        return self.order

    async def get_option_snapshot(self, symbols, **kw):
        return {"snapshots": {}}


def agent_for(tmp_path, broker, ledger):
    return Agent(
        broker, writer=None, limits=Limits(),
        journal=Journal.open(tmp_path / "j.jsonl"), ledger=ledger,
        policy=ExitPolicy(), dry_run=False,
        breaker=CircuitState(path=tmp_path / "c.json"),
    )


def held(path, **over) -> Ledger:
    """A position whose net fill is already confirmed and whose legs were never kept."""
    base = {
        "structure_id": "s1", "name": "QQQ 765/775 call credit spread", "underlying": "QQQ",
        "qty": 1, "legs": {SHORT: -1, LONG: 1}, "opened_at": "2026-08-27T16:40:25+00:00",
        "entry_price": Decimal("-1.51"), "entry_filled": True, "order_id": "ord-1",
        "entry_legs": None,
    }
    return Ledger(path=path, structures=[OpenStructure(**{**base, **over})])


# --- the backfill ---------------------------------------------------------------

def test_a_position_held_since_before_the_field_existed_is_backfilled(tmp_path):
    led = held(tmp_path / "l.json")
    agent = agent_for(tmp_path, Broker(), led)

    assert asyncio.run(agent.refresh_leg_fills()) == 1
    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51"), LONG: Decimal(3)}


def test_refresh_fills_alone_would_never_have_reached_it(tmp_path):
    """Why this is a second pass and not a wider first one.

    `awaiting_fill_price` is bounded by `entry_filled`, which is already True here.
    Delete `refresh_leg_fills` and this position keeps its net price forever and never
    gets a leg table.
    """
    led = held(tmp_path / "l.json")
    broker = Broker()
    agent = agent_for(tmp_path, broker, led)

    assert led.awaiting_fill_price() == []
    assert asyncio.run(agent.refresh_fills()) == 0
    assert broker.asked == []
    assert led.structures[0].entry_legs is None


def test_the_backfill_lands_on_disk(tmp_path):
    """Not just in memory. A restart between the lookup and the next save would lose it."""
    path = tmp_path / "l.json"
    agent = agent_for(tmp_path, Broker(), held(path))
    asyncio.run(agent.refresh_leg_fills())

    assert Ledger.load(path).structures[0].entry_legs[SHORT] == Decimal("4.51")


def test_it_asks_once_and_then_stops(tmp_path):
    """The whole point of writing `{}` rather than leaving `None`."""
    led = held(tmp_path / "l.json")
    broker = Broker()
    agent = agent_for(tmp_path, broker, led)

    for _ in range(5):
        asyncio.run(agent.refresh_leg_fills())
    assert broker.asked == ["ord-1"]


def test_an_order_with_no_legs_also_stops_being_asked(tmp_path):
    """The termination case. Otherwise this is one broker call a cycle, forever."""
    led = held(tmp_path / "l.json")
    broker = Broker(order={"id": "ord-1", "status": "filled",
                           "filled_avg_price": "-1.51"})
    agent = agent_for(tmp_path, broker, led)

    assert asyncio.run(agent.refresh_leg_fills()) == 0
    assert led.structures[0].entry_legs == {}
    asyncio.run(agent.refresh_leg_fills())
    assert broker.asked == ["ord-1"], "asked once, learned nothing, did not ask again"


def test_an_unfilled_order_is_left_to_be_asked_again(tmp_path):
    """The opposite case: nothing to learn *yet*, so the state must not be closed off."""
    led = held(tmp_path / "l.json")
    broker = Broker(order={"id": "ord-1", "status": "pending_new",
                           "legs": [{"symbol": SHORT, "filled_avg_price": None}]})
    agent = agent_for(tmp_path, broker, led)

    assert asyncio.run(agent.refresh_leg_fills()) == 0
    assert led.structures[0].entry_legs is None, "still unasked — it has not filled"
    asyncio.run(agent.refresh_leg_fills())
    assert broker.asked == ["ord-1", "ord-1"]


def test_a_broker_failure_leaves_the_structure_askable(tmp_path):
    led = held(tmp_path / "l.json")
    agent = agent_for(tmp_path, Broker(error=MCPError("no route to host")), led)

    assert asyncio.run(agent.refresh_leg_fills()) == 0
    assert led.structures[0].entry_legs is None


def test_a_broker_failure_does_not_journal_an_error(tmp_path):
    """It costs a leg table its prices for one cycle. Nothing is waiting on it.

    `refresh_fills` journals its failures because a missing net price biases the exit
    policy. This one has no such consequence, and an error line per cycle per position
    would bury the ones that matter.
    """
    led = held(tmp_path / "l.json")
    agent = agent_for(tmp_path, Broker(error=MCPError("boom")), led)
    asyncio.run(agent.refresh_leg_fills())

    written = (tmp_path / "j.jsonl").read_text() if (tmp_path / "j.jsonl").exists() else ""
    assert "boom" not in written


def test_one_structures_failure_does_not_cost_the_others_their_backfill(tmp_path):
    class Flaky(Broker):
        async def get_order(self, order_id):
            self.asked.append(order_id)
            if order_id == "ord-1":
                raise MCPError("just this one")
            return {"id": order_id, "status": "filled", **FILLS}

    led = held(tmp_path / "l.json")
    led.structures.append(OpenStructure(
        structure_id="s2", name="second", underlying="QQQ", qty=1,
        legs={SHORT: -1, LONG: 1}, opened_at="2026-08-27T17:00:00+00:00",
        entry_price=Decimal("-1.40"), entry_filled=True, order_id="ord-2"))
    agent = agent_for(tmp_path, Flaky(), led)

    assert asyncio.run(agent.refresh_leg_fills()) == 1
    assert led.structures[0].entry_legs is None
    assert led.structures[1].entry_legs == {SHORT: Decimal("4.51"), LONG: Decimal(3)}


def test_a_closed_structure_is_backfilled_from_its_closing_order(tmp_path):
    led = held(tmp_path / "l.json", entry_legs={SHORT: Decimal("4.51")},
               closed_at="2026-08-27T19:30:00+00:00", exit_order_id="ord-x",
               exit_price=Decimal("1.20"), exit_filled=True)
    broker = Broker(order={"id": "ord-x", "status": "filled", "legs": [
        {"symbol": SHORT, "filled_avg_price": "2.05"},
        {"symbol": LONG, "filled_avg_price": "0.85"}]})
    agent = agent_for(tmp_path, broker, led)

    assert asyncio.run(agent.refresh_leg_fills()) == 1
    assert broker.asked == ["ord-x"], "the closing order, not the opening one"
    assert led.structures[0].exit_legs == {SHORT: Decimal("2.05"), LONG: Decimal("0.85")}
    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51")}, "untouched"


# --- the ordinary path, off the order refresh_fills already fetched -------------

def test_a_pending_entry_gets_both_its_net_and_its_legs_from_one_lookup(tmp_path):
    """No extra broker call for the common case. `refresh_fills` already has the order."""
    led = held(tmp_path / "l.json", entry_price=Decimal("-1.49"), entry_filled=False)
    broker = Broker()
    agent = agent_for(tmp_path, broker, led)

    assert asyncio.run(agent.refresh_fills()) == 1
    assert broker.asked == ["ord-1"], "one lookup, both answers"
    assert led.structures[0].entry_price == Decimal("-1.51")
    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51"), LONG: Decimal(3)}


def test_the_leg_backfill_is_not_counted_as_a_price_correction(tmp_path):
    """`refresh_fills` returns a count of corrected prices and tests read it as one.

    Adding leg backfills to that number would make it mean two things, and the soak
    harness asserts on it.
    """
    led = held(tmp_path / "l.json")
    agent = agent_for(tmp_path, Broker(), led)

    assert asyncio.run(agent.refresh_fills()) == 0, "no price changed"
    assert asyncio.run(agent.refresh_leg_fills()) == 1


@pytest.mark.parametrize("method", ["refresh_fills", "refresh_leg_fills"])
def test_neither_pass_touches_the_broker_on_an_empty_book(tmp_path, method):
    broker = Broker()
    agent = agent_for(tmp_path, broker, Ledger(path=tmp_path / "l.json"))
    asyncio.run(getattr(agent, method)())
    assert broker.asked == []


# --- wiring ---------------------------------------------------------------------

def test_managing_the_book_runs_the_backfill(tmp_path):
    """The method existing is not the same as it being called.

    A test that only exercises `refresh_leg_fills` directly passes forever after the
    call site is deleted, and the symptom — a leg table that never fills in — looks
    like a broker problem rather than a missing line.
    """
    led = held(tmp_path / "l.json")
    broker = Broker()
    agent = agent_for(tmp_path, broker, led)

    asyncio.run(agent.manage_exits())

    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51"), LONG: Decimal(3)}
