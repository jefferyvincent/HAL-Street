"""The loop's exit path: ordering, and refusing to skip it quietly."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import Action, ExitPolicy
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.execution.mcp_client import MCPError
from halstreet.execution.structures import iron_condor
from halstreet.gates.base import Limits
from halstreet.telemetry.journal import Journal

P755, P760 = "SPY261016P00755000", "SPY261016P00760000"
C770, C775 = "SPY261016C00770000", "SPY261016C00775000"


def quote(mid):
    d = Decimal(str(mid))
    return {"latestQuote": {"bp": str(d - Decimal("0.02")), "ap": str(d + Decimal("0.02"))}}


class FakeClient:
    """Records calls; returns a profitable mark for the held condor."""

    option_feed = "indicative"

    def __init__(self, snapshot_error: Exception | None = None):
        self.placed = []
        self.snapshot_error = snapshot_error

    async def get_option_snapshot(self, symbols, **kw):
        if self.snapshot_error:
            raise self.snapshot_error
        return {"snapshots": {P755: quote(0.50), P760: quote(1.00),
                              C770: quote(2.00), C775: quote(1.00)}}

    async def place_structure(self, structure):
        self.placed.append(structure)
        return {"id": "ord-1", "status": "filled", "filled_qty": "1",
                "filled_avg_price": "1.50"}


@pytest.fixture
def ledger(tmp_path: Path):
    led = Ledger(path=tmp_path / "l.json")
    led.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                    structure_id="c1", entry_price=Decimal("-4.04"))
    # And filled at it. `record_open` books on acceptance; the exit path only manages
    # what the broker actually gave us, which the guard added on 2026-08-31 enforces.
    led.record_fill("c1", Decimal("-4.04"))
    return led


@pytest.fixture
def journal(tmp_path: Path):
    return Journal.open(tmp_path / "j.jsonl")


def agent_for(client, ledger, journal, *, dry_run):
    return Agent(client, writer=None, limits=Limits(), journal=journal,
                 ledger=ledger, policy=ExitPolicy(), dry_run=dry_run)


def test_a_profitable_structure_is_closed(ledger, journal):
    client = FakeClient()
    decisions = asyncio.run(agent_for(client, ledger, journal, dry_run=False).manage_exits())
    assert [d.action for d in decisions] == [Action.TAKE_PROFIT]
    assert len(client.placed) == 1
    assert len(client.placed[0].legs) == 4     # closed atomically, not legged out
    assert ledger.open_structures == []        # retired
    assert ledger.structures[0].exit_price == Decimal("1.50")


def test_dry_run_decides_but_does_not_submit(ledger, journal):
    client = FakeClient()
    decisions = asyncio.run(agent_for(client, ledger, journal, dry_run=True).manage_exits())
    assert decisions[0].should_close
    assert client.placed == []
    assert len(ledger.open_structures) == 1    # still ours to manage


def test_a_failed_exit_leaves_the_structure_open(ledger, journal):
    """The most important journal entry there is: it still needs closing next cycle."""
    class Failing(FakeClient):
        async def place_structure(self, structure):
            raise MCPError("broker said no")

    asyncio.run(agent_for(Failing(), ledger, journal, dry_run=False).manage_exits())
    assert len(ledger.open_structures) == 1
    events = [r["event"] for r in journal.read()]
    assert "error" in events


def test_unpriceable_book_is_reported_not_skipped(ledger, journal):
    client = FakeClient(snapshot_error=MCPError("quotes down"))
    decisions = asyncio.run(agent_for(client, ledger, journal, dry_run=False).manage_exits())
    assert decisions[0].action is Action.UNKNOWN
    assert client.placed == []
    assert any(r["event"] == "error" for r in journal.read())


def test_no_open_structures_is_a_no_op(tmp_path, journal):
    empty = Ledger(path=tmp_path / "e.json")
    assert asyncio.run(agent_for(FakeClient(), empty, journal, dry_run=False).manage_exits()) == []


def test_exits_are_marked_against_held_symbols_not_the_scan_window(ledger, journal):
    """Open positions sit at whatever expiry they were opened at."""
    asked = {}

    class Recording(FakeClient):
        async def get_option_snapshot(self, symbols, **kw):
            asked["symbols"] = list(symbols)
            return await super().get_option_snapshot(symbols, **kw)

    asyncio.run(agent_for(Recording(), ledger, journal, dry_run=True).manage_exits())
    assert set(asked["symbols"]) == {P755, P760, C770, C775}


# --- a submission the broker did not acknowledge --------------------------------------
#
# Live, 2026-08-31 14:45:21: `submitted=True, order_id=None, status=None`. The response
# carried neither an id nor a status, and the ledger booked the structure anyway — so
# the book held a position that could never be looked up, re-priced, cancelled or
# reconciled. It showed on the console, it counted toward exposure, and every cycle
# after it logged a divergence nobody could act on.
#
# An order we cannot name is an order we do not have.

class Nameless(FakeClient):
    """A broker that accepts and says nothing useful about what it accepted."""

    def __init__(self, response):
        super().__init__()
        self.response = response

    async def place_structure(self, structure):
        self.placed.append(structure)
        return self.response


def _fresh(tmp_path):
    """An empty ledger — this is about opening, not about what is already held."""
    return Ledger(path=tmp_path / "fresh.json")


def _proposal():
    from halstreet.gates.base import Proposal
    return Proposal(underlying="SPY", rationale="", confidence=0.5,
                    structure=iron_condor("Oct condor", P755, P760, C770, C775))


def _submit_with(client, ledger, journal):
    from halstreet.agent.cerebellum.loop import CycleResult
    agent = agent_for(client, ledger, journal, dry_run=False)
    result = CycleResult(underlying="SPY")
    asyncio.run(agent._submit(_proposal(), result))
    return agent, result


@pytest.mark.parametrize("response", [{}, {"status": "accepted"}, {"id": ""},
                                      {"id": None, "status": "new"}])
def test_an_order_with_no_id_is_not_booked_as_a_position(response, tmp_path, journal):
    ledger = _fresh(tmp_path)
    _submit_with(Nameless(response), ledger, journal)
    assert ledger.open_structures == [], "booked a structure it can never look up"


def test_it_is_journalled_as_a_failure_rather_than_a_submission(tmp_path, journal):
    _agent, result = _submit_with(Nameless({}), _fresh(tmp_path), journal)
    order = next(e for e in journal.read() if e["event"] == "order")
    assert order["submitted"] is False
    assert "id" in (order["error"] or "").lower()
    assert result.submitted is False


def test_the_throttle_does_not_count_an_order_we_never_got(tmp_path, journal):
    """`record_entry` stamps the runaway guard. An unacknowledged submission is not an
    entry, and counting it spends the hour's budget on nothing."""
    agent, _ = _submit_with(Nameless({}), _fresh(tmp_path), journal)
    assert agent.breaker.entries_in_window() == 0


def test_an_acknowledged_order_is_booked_exactly_as_before(tmp_path, journal):
    ledger = _fresh(tmp_path)
    _submit_with(Nameless({"id": "abc-123", "status": "new"}), ledger, journal)
    assert len(ledger.open_structures) == 1
    assert ledger.open_structures[0].order_id == "abc-123"


# --- the working-order loop ------------------------------------------------------------
#
# The agent had an entry path and an exit path and nothing in between. It submitted a
# `day` limit and forgot the order existed: never asked whether it filled, never
# re-priced, never cancelled. A SPY spread sat unfilled from 14:15 to the close while a
# second went on top of it, and the ledger carried both as positions.

class _Orders(FakeClient):
    """A broker with an order book we can script."""

    def __init__(self, statuses: dict[str, dict]):
        super().__init__()
        self.statuses = statuses
        self.cancelled: list[str] = []

    async def get_order(self, order_id):
        return self.statuses[order_id]

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"id": order_id, "status": "canceled"}


def _working(tmp_path, *, order_id="ord-9", age_minutes=45):
    """A ledger holding one accepted-but-unfilled structure."""
    from datetime import UTC, datetime, timedelta
    led = Ledger(path=tmp_path / "w.json")
    led.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                    structure_id="w1", entry_price=Decimal("-4.04"), order_id=order_id)
    when = datetime.now(UTC) - timedelta(minutes=age_minutes)
    led.structures[-1].opened_at = when.isoformat()
    led.save()
    return led


def _work(client, ledger, journal):
    return asyncio.run(agent_for(client, ledger, journal, dry_run=False).work_orders())


def test_a_filled_order_is_recorded_rather_than_cancelled(tmp_path, journal):
    ledger = _working(tmp_path)
    client = _Orders({"ord-9": {"status": "filled", "filled_avg_price": "-4.10"}})
    _work(client, ledger, journal)
    assert client.cancelled == []
    assert ledger.open_structures[0].entry_filled is True
    assert ledger.open_structures[0].entry_price == Decimal("-4.10")


def test_an_order_that_died_is_dropped_from_the_book(tmp_path, journal):
    """Cancelled, expired or rejected — it never became a position, and leaving it in
    the ledger is what produced a divergence nobody could act on."""
    for status in ("canceled", "expired", "rejected"):
        ledger = _working(tmp_path)
        _work(_Orders({"ord-9": {"status": status}}), ledger, journal)
        assert ledger.open_structures == [], status


def test_a_stale_working_order_is_cancelled(tmp_path, journal):
    """Not re-priced here. Cancelling returns it to the normal path, where the next
    cycle prices it off fresh quotes and puts it through the whole EV and gate chain
    again — which is a better price than any bespoke chase, and needs no second
    definition of what a trade is worth."""
    ledger = _working(tmp_path, age_minutes=45)
    client = _Orders({"ord-9": {"status": "new", "filled_qty": "0"}})
    _work(client, ledger, journal)
    assert client.cancelled == ["ord-9"]
    assert ledger.open_structures == []


def test_a_fresh_working_order_is_left_alone(tmp_path, journal):
    """One cycle's grace. Cancelling an order placed ninety seconds ago is churn."""
    ledger = _working(tmp_path, age_minutes=1)
    client = _Orders({"ord-9": {"status": "new", "filled_qty": "0"}})
    _work(client, ledger, journal)
    assert client.cancelled == []
    assert len(ledger.open_structures) == 1


def test_a_partial_fill_is_never_cancelled(tmp_path, journal):
    """Half a spread is a position, and an unbalanced one. Cancelling the remainder
    leaves naked legs — the one outcome the defined-risk gate exists to prevent."""
    ledger = _working(tmp_path, age_minutes=45)
    client = _Orders({"ord-9": {"status": "partially_filled", "filled_qty": "1"}})
    _work(client, ledger, journal)
    assert client.cancelled == []


def test_a_broker_that_will_not_answer_changes_nothing(tmp_path, journal):
    """Not knowing is not a reason to cancel. The order stays and we ask again."""
    class Mute(_Orders):
        async def get_order(self, order_id):
            raise MCPError("order lookup failed")

    ledger = _working(tmp_path, age_minutes=45)
    client = Mute({})
    _work(client, ledger, journal)
    assert client.cancelled == []
    assert len(ledger.open_structures) == 1


def test_a_filled_structure_is_never_looked_at(tmp_path, journal):
    """This manages orders, not positions. The exit path owns what filled."""
    ledger = _working(tmp_path)
    ledger.record_fill("w1", Decimal("-4.04"))
    client = _Orders({})
    _work(client, ledger, journal)
    assert client.cancelled == []


def test_every_decision_is_journalled(tmp_path, journal):
    ledger = _working(tmp_path, age_minutes=45)
    _work(_Orders({"ord-9": {"status": "new"}}), ledger, journal)
    kinds = [e["event"] for e in journal.read()]
    assert "working_order" in kinds


def test_an_unfilled_structure_with_no_order_id_is_dropped(tmp_path, journal):
    """It cannot be looked up, re-priced or cancelled — there is nothing to name.

    `_submit` refuses to create these now, but one exists in the live book from before
    that guard: the broker returned no id on 2026-08-31 at 14:45, the ledger booked it
    anyway, and every cycle since has logged a divergence about contracts nobody can
    act on. Left to `work_orders` alone it would sit there forever, because the loop
    only walks orders it can ask about.
    """
    from datetime import UTC, datetime, timedelta

    led = Ledger(path=tmp_path / "o.json")
    led.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                    structure_id="o1", entry_price=Decimal("-4.04"))
    led.structures[-1].opened_at = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    led.save()
    assert led.open_structures[0].order_id is None

    _work(_Orders({}), led, journal)
    assert led.open_structures == []
    note = next(e for e in journal.read() if e["event"] == "working_order")
    assert note["action"] == "unnameable"


def test_a_fresh_structure_with_no_order_id_is_given_its_moment(tmp_path, journal):
    """The submission may still be in flight. Dropping it the same second it was
    written would race the code that wrote it."""
    led = Ledger(path=tmp_path / "o.json")
    led.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                    structure_id="o1", entry_price=Decimal("-4.04"))
    _work(_Orders({}), led, journal)
    assert len(led.open_structures) == 1
