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


# --- chasing the fill --------------------------------------------------------------
#
# Withdrawing a working order returns it to the next scan, which is correct and slow.
# The live case: a SPY spread priced at 0.34 credit against a book paying 0.27 — seven
# cents out, drifting in and out of reach all afternoon. Cancelling that throws away a
# trade the desk wanted over a price difference smaller than one tick of the underlying.
#
# So it walks the limit toward the book. What it must never do is walk it anywhere: the
# expectancy that justified the trade was computed at the credit it was scored on, and a
# chase with no floor turns a considered position into whatever the market will pay.

def _book(short_bid, long_ask):
    """Quotes where selling P760 and buying P755 nets `short_bid - long_ask` of credit."""
    return {P760: {"latestQuote": {"bp": str(short_bid), "ap": str(short_bid + 0.02)}},
            P755: {"latestQuote": {"bp": str(long_ask - 0.02), "ap": str(long_ask)}}}


def _spread(tmp_path, *, limit="-1.00", order_id="ord-9", age=45, reprices=0):
    from datetime import UTC, datetime, timedelta

    from halstreet.execution.structures import vertical
    led = Ledger(path=tmp_path / "c.json")
    led.record_open(vertical("Oct spread", P755, P760), "SPY",
                    structure_id="c1", entry_price=Decimal(limit), order_id=order_id)
    s = led.structures[-1]
    s.opened_at = (datetime.now(UTC) - timedelta(minutes=age)).isoformat()
    s.reprices = reprices
    led.save()
    return led


class _Chaser(_Orders):
    def __init__(self, statuses, book):
        super().__init__(statuses)
        self.book, self.replaced = book, []

    async def get_option_snapshot(self, symbols, **kw):
        return {"snapshots": self.book}

    async def replace_order(self, order_id, limit_price):
        self.replaced.append((order_id, limit_price))
        return {"id": "ord-10", "status": "new"}


def _chase(client, ledger, journal):
    return asyncio.run(agent_for(client, ledger, journal, dry_run=False).work_orders())


def test_a_limit_asking_more_than_the_book_pays_is_walked_to_the_book(tmp_path, journal):
    ledger = _spread(tmp_path, limit="-0.34")
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.30, 5.03))
    _chase(client, ledger, journal)
    assert client.replaced == [("ord-9", Decimal("-0.27"))]
    assert client.cancelled == []


def test_an_already_marketable_limit_is_left_to_fill(tmp_path, journal):
    """Asking less credit than the book pays. Moving it would give away money for a
    fill that is already coming."""
    ledger = _spread(tmp_path, limit="-0.10")
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.30, 5.03))
    _chase(client, ledger, journal)
    assert client.replaced == [] and client.cancelled == []


def test_it_will_not_chase_below_the_credit_the_trade_was_scored_on(tmp_path, journal):
    """The expectancy that justified this was computed at the original credit. Halve
    that and the trade is a different one nobody assessed — so it is withdrawn instead,
    and the next scan may propose it again at a price it can defend."""
    ledger = _spread(tmp_path, limit="-1.00", age=5)
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.10, 5.03))   # 0.07 credit
    _chase(client, ledger, journal)
    assert client.replaced == []
    assert client.cancelled == [], "a floor says do not move it, not pull it"


def test_it_will_not_chase_a_credit_that_no_longer_clears_its_own_exit(tmp_path, journal):
    """Max gain has to stay worth more than getting out costs. Below that the position
    is friction with a lottery ticket attached, whatever the reward/risk says."""
    ledger = _spread(tmp_path, limit="-0.40", age=5)
    # 0.30 of credit — which is above half the scored credit, so the credit floor is
    # satisfied — but each leg is 0.30 wide, so getting out costs $30 against a $30
    # max gain.
    wide = {P760: {"latestQuote": {"bp": "5.40", "ap": "5.70"}},
            P755: {"latestQuote": {"bp": "4.80", "ap": "5.10"}}}
    client = _Chaser({"ord-9": {"status": "new"}}, wide)
    _chase(client, ledger, journal)
    assert client.replaced == []
    assert client.cancelled == []


def test_the_chase_is_bounded(tmp_path, journal):
    """A limit that has already been walked its allowance is withdrawn rather than
    followed further down. Otherwise a drifting book drags it to nothing one tick at a
    time, each step defensible and the sum of them not."""
    ledger = _spread(tmp_path, limit="-0.34", reprices=3)
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.30, 5.03))
    _chase(client, ledger, journal)
    assert client.replaced == []


def test_a_replace_records_the_new_price_and_the_new_order_id(tmp_path, journal):
    """A replacement is a different order at the broker. Keeping the old id would leave
    the next cycle asking about something that no longer exists."""
    ledger = _spread(tmp_path, limit="-0.34")
    _chase(_Chaser({"ord-9": {"status": "new"}}, _book(5.30, 5.03)), ledger, journal)
    s = Ledger.load(str(ledger.path)).open_structures[0]
    assert s.entry_price == Decimal("-0.27")
    assert s.order_id == "ord-10"
    assert s.reprices == 1


def test_a_book_it_cannot_read_changes_nothing(tmp_path, journal):
    """No quotes, no chase, no cancel. Not knowing the price is not a reason to move."""
    ledger = _spread(tmp_path, limit="-0.34")
    client = _Chaser({"ord-9": {"status": "new"}}, {})
    _chase(client, ledger, journal)
    assert client.replaced == [] and client.cancelled == []


def test_a_freshly_walked_limit_gets_its_own_grace(tmp_path, journal):
    """The clock restarts on every move. Otherwise the between-scan job, which runs each
    minute, walks the limit its whole allowance inside three of them — spending every
    step before the book has had a chance to come back."""
    from datetime import UTC, datetime
    ledger = _spread(tmp_path, limit="-0.34", age=45)
    ledger.structures[-1].repriced_at = datetime.now(UTC).isoformat()
    ledger.save()
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.30, 5.03))
    _chase(client, ledger, journal)
    assert client.replaced == [] and client.cancelled == []


def test_a_floor_holds_the_order_rather_than_pulling_it(tmp_path, journal):
    """The distinction the first draft of this missed. A floor answers "should the limit
    move", and the answer being no is not an argument for cancelling — at a three-minute
    grace that would pull orders the thirty-five-minute rule would have left to fill."""
    ledger = _spread(tmp_path, limit="-0.34", age=5)
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.10, 5.05))   # 0.05 credit
    _chase(client, ledger, journal)
    assert client.replaced == [] and client.cancelled == []


def test_past_the_backstop_an_unchaseable_order_is_withdrawn(tmp_path, journal):
    ledger = _spread(tmp_path, limit="-0.34", age=45)
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.10, 5.05))
    _chase(client, ledger, journal)
    assert client.replaced == []
    assert client.cancelled == ["ord-9"]


def test_the_backstop_is_measured_from_when_the_order_was_written(tmp_path, journal):
    """Not from the last move. Otherwise each chase resets the backstop and a limit that
    keeps just barely qualifying never reaches it — the exact shape of a stale order the
    thirty-five-minute rule exists to catch."""
    from datetime import UTC, datetime, timedelta
    ledger = _spread(tmp_path, limit="-0.34", age=90)
    ledger.structures[-1].repriced_at = (datetime.now(UTC)
                                         - timedelta(minutes=5)).isoformat()
    ledger.save()
    client = _Chaser({"ord-9": {"status": "new"}}, _book(5.10, 5.05))
    _chase(client, ledger, journal)
    assert client.cancelled == ["ord-9"]
