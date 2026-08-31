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
