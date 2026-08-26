"""Durability across a restart — the gap where the two live-only defects lived.

Both defects found by the first real submission were invisible to unit tests, and it
is worth being precise about *why*: neither is a wrong calculation. Both are about
what survives between a real order reaching the broker and the process being restarted
before it tidied up.

  1. `record_open` mutated the ledger in memory and left persistence to the caller.
     The loop does call `save()`, so it was correct in practice — but an order accepted
     by the broker with no ledger record is an untracked position, and reconciliation
     reports it as a divergence forever.
  2. Entry price was the *limit*, written at submission when the order is `pending_new`
     and no fill exists yet. A limit is by definition the worst price you were willing
     to accept, so every figure derived from it — realized P&L, the exit policy's
     percentage thresholds — was biased one way.

A test that calls a function and checks its return value cannot see either. These
tests kill the object instead: mutate, drop every in-memory reference, reload from
disk, and assert on what came back. That is the only shape that would have caught
them, and it needs no broker.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import ClassVar

import pytest

from halstreet.agent.breaker import CircuitState
from halstreet.agent.ledger import Ledger
from halstreet.agent.loop import Agent
from halstreet.agent.manager import ExitPolicy
from halstreet.execution.mcp_client import MCPError
from halstreet.execution.structures import vertical
from halstreet.gates.base import Limits
from halstreet.telemetry.journal import Journal

SHORT, LONG = "QQQ261016C00755000", "QQQ261016C00765000"


def spread():
    # The real one: sell the 755 call, buy the 765 for the wing. `vertical` takes the
    # long leg first, so the arguments read in the opposite order to the name.
    return vertical("QQQ 755/765 call credit spread", LONG, SHORT,
                    limit_price=Decimal("-1.59"))


class Broker:
    """A broker that accepts orders and can be told what they filled at.

    Mirrors the real one's timing: `place_structure` returns `pending_new` with no
    fill price, exactly as Alpaca did for order 365deebd. The fill only becomes
    visible through a later `get_order` — which is the whole reason `refresh_fills`
    exists.
    """

    option_feed = "indicative"

    def __init__(self, fill: str | None = "-1.60", order_error: Exception | None = None):
        self.fill = fill
        self.order_error = order_error
        self.placed: list = []

    async def place_structure(self, structure):
        self.placed.append(structure)
        return {"id": "ord-1", "status": "pending_new",
                "filled_qty": "0", "filled_avg_price": None}

    async def get_order(self, order_id):
        if self.order_error:
            raise self.order_error
        return {"id": order_id, "status": "filled", "filled_avg_price": self.fill}

    async def get_option_snapshot(self, symbols, **kw):
        return {"snapshots": {}}


def agent_for(tmp_path, broker, ledger):
    return Agent(
        broker, writer=None, limits=Limits(),
        journal=Journal.open(tmp_path / "j.jsonl"), ledger=ledger,
        policy=ExitPolicy(), dry_run=False,
        breaker=CircuitState(path=tmp_path / "c.json"),
    )


@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "ledger.json"


# --- defect 1: an accepted order with no ledger record ---------------------------

def test_a_submitted_order_is_on_disk_before_the_caller_saves(tmp_path, ledger_path):
    # The window between the broker accepting an order and the loop's next save() is
    # small, but it is exactly where a crash leaves an untracked position.
    led = Ledger.load(ledger_path)
    broker = Broker()
    agent = agent_for(tmp_path, broker, led)

    class Result:
        submitted = False
        order_id = None
        error = None
        notes: ClassVar[list] = []

    from halstreet.gates.base import Proposal
    asyncio.run(agent._submit(Proposal(structure=spread(), underlying="QQQ",
                                       rationale="because"), Result()))
    assert broker.placed, "the order must actually have gone out"

    # Drop every in-memory reference and come back from disk, as a restart would.
    reloaded = Ledger.load(ledger_path)
    assert len(reloaded.open_structures) == 1
    assert reloaded.open_structures[0].order_id == "ord-1"
    assert reloaded.expected_positions() == {SHORT: -1, LONG: 1}


def test_a_restart_does_not_orphan_the_position(tmp_path, ledger_path):
    # The consequence the durability fix prevents: a broker holding contracts the
    # ledger has never heard of shows up as a permanent divergence, and nothing knows
    # what the structure was meant to be or when to close it.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    broker_positions = [{"symbol": SHORT, "qty": "-1"}, {"symbol": LONG, "qty": "1"}]
    assert Ledger.load(ledger_path).reconcile(broker_positions) == []


def test_a_closed_structure_does_not_come_back_open(tmp_path, ledger_path):
    # Mirrored: if a close did not persist, the next cycle after a restart would
    # submit a second closing order against a position that is already flat.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    led.record_close("s1", exit_price=Decimal("1.69"))
    assert Ledger.load(ledger_path).open_structures == []


# --- defect 2: the limit price is not the fill price ------------------------------

def test_the_provisional_limit_is_replaced_by_the_real_fill(tmp_path, ledger_path):
    # Live: limit -1.59, filled -1.60. A dollar on one contract; the reported result
    # over a competition window.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    agent = agent_for(tmp_path, Broker(fill="-1.60"), led)

    assert asyncio.run(agent.refresh_fills()) == 1
    assert Ledger.load(ledger_path).structures[0].entry_price == Decimal("-1.60")


def test_the_correction_is_journalled_rather_than_silent(tmp_path, ledger_path):
    # It moves every P&L figure derived from that structure, and a number that
    # changes without a record is one nobody can reconcile later.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    agent = agent_for(tmp_path, Broker(fill="-1.60"), led)
    asyncio.run(agent.refresh_fills())

    events = [e for e in agent.journal.read() if e["event"] == "fill_correction"]
    assert len(events) == 1
    assert events[0]["limit_price"] == "-1.59"
    assert events[0]["fill_price"] == "-1.60"


def test_an_unfilled_order_leaves_the_provisional_price_alone(tmp_path, ledger_path):
    # `pending_new` carries no fill. Overwriting the limit with None would be worse
    # than the bias it replaces.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    agent = agent_for(tmp_path, Broker(fill=None), led)
    assert asyncio.run(agent.refresh_fills()) == 0
    assert Ledger.load(ledger_path).structures[0].entry_price == Decimal("-1.59")


def test_a_failed_lookup_degrades_rather_than_stopping_the_cycle(tmp_path, ledger_path):
    # An approximate entry price is worth far more than none, and a transport blip
    # must not prevent exits from being judged this cycle.
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    agent = agent_for(tmp_path, Broker(order_error=MCPError("transport blip")), led)

    assert asyncio.run(agent.refresh_fills()) == 0
    assert Ledger.load(ledger_path).structures[0].entry_price == Decimal("-1.59")
    assert any(e["event"] == "error" for e in agent.journal.read())


def test_the_fill_survives_the_restart_it_was_written_for(tmp_path, ledger_path):
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    asyncio.run(agent_for(tmp_path, Broker(fill="-1.60"), led).refresh_fills())

    # A second process, seeing only what is on disk, must not re-correct.
    fresh = Ledger.load(ledger_path)
    agent2 = agent_for(tmp_path, Broker(fill="-1.60"), fresh)
    assert asyncio.run(agent2.refresh_fills()) == 0


def test_realized_pnl_uses_the_fill_not_the_limit(tmp_path, ledger_path):
    # The end of the chain, and the reason any of this matters: the number in the
    # write-up. Limit -1.59 -> +1.69 reports -$10.00; the real fills give -$9.00.
    from halstreet.telemetry import pnl
    led = Ledger.load(ledger_path)
    led.record_open(spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="ord-1")
    asyncio.run(agent_for(tmp_path, Broker(fill="-1.60"), led).refresh_fills())
    Ledger.load(ledger_path)  # prove it round-trips
    led = Ledger.load(ledger_path)
    led.record_close("s1", exit_price=Decimal("1.69"))

    report = pnl.build(Ledger.load(ledger_path), Journal.open(tmp_path / "j.jsonl"))
    assert report.realized_usd == Decimal("-9.00")
