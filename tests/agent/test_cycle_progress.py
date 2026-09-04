"""Saying what the scan is doing while it does it.

A cycle over a discovered universe is six symbols, each a full committee, and it took
73 seconds on the live run. Every result was printed at the end, so for those 73
seconds the terminal showed nothing at all — indistinguishable from a hang, and read
as one.

The fix is not a spinner. It is that the work already has natural units — one symbol,
then the next — and the loop knew which one it was on and did not say. So `run_once`
reports as it goes, and the caller decides how to render that; the loop still returns
the same list it always did, because the report is an addition to the cycle and not a
replacement for its result.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import ExitPolicy
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.gates.base import Limits
from halstreet.telemetry.journal import Journal


class _Writer:
    system_prompt = "RULES"


@pytest.fixture
def agent(tmp_path, monkeypatch):
    a = Agent(
        client=None, writer=_Writer(), limits=Limits(),
        journal=Journal.open(tmp_path / "run.jsonl"),
        ledger=Ledger.load(tmp_path / "ledger.json"),
        policy=ExitPolicy(take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200),
                          force_close_dte=5),
        dry_run=True, breaker=CircuitState(),
    )

    async def no_exits():
        return []

    async def fake_cycle(underlying):
        from halstreet.agent.cerebellum.loop import CycleResult
        return CycleResult(underlying=underlying)

    monkeypatch.setattr(a, "manage_exits", no_exits)
    monkeypatch.setattr(a, "run_cycle", fake_cycle)
    return a


@pytest.mark.asyncio
async def test_it_says_which_symbol_it_is_starting(agent):
    seen = []
    await agent.run_once(["SPY", "NVDA"], on_start=seen.append)
    assert seen == ["SPY", "NVDA"]


@pytest.mark.asyncio
async def test_it_reports_each_result_as_it_lands(agent):
    seen = []
    await agent.run_once(["SPY", "NVDA"], on_result=lambda r: seen.append(r.underlying))
    assert seen == ["SPY", "NVDA"]


@pytest.mark.asyncio
async def test_a_symbol_is_announced_before_it_is_finished(agent):
    """The whole point. Announced after, it is a summary and not progress."""
    order = []
    await agent.run_once(["SPY", "NVDA"],
                         on_start=lambda s: order.append(f"start {s}"),
                         on_result=lambda r: order.append(f"done {r.underlying}"))
    assert order == ["start SPY", "done SPY", "start NVDA", "done NVDA"]


@pytest.mark.asyncio
async def test_the_return_value_is_unchanged(agent):
    """The report is an addition to the cycle, not a replacement for its result."""
    results = await agent.run_once(["SPY", "NVDA"])
    assert [r.underlying for r in results] == ["SPY", "NVDA"]


@pytest.mark.asyncio
async def test_it_still_runs_with_nobody_listening(agent):
    assert len(await agent.run_once(["SPY"])) == 1


@pytest.mark.asyncio
async def test_a_symbol_that_failed_is_still_reported(agent, monkeypatch):
    """A cycle that raised is the one a watcher most wants to see land."""
    async def boom(underlying):
        raise RuntimeError("chain unavailable")

    monkeypatch.setattr(agent, "run_cycle", boom)
    seen = []
    await agent.run_once(["SPY"], on_result=lambda r: seen.append(r.error))
    assert seen and "chain unavailable" in seen[0]


@pytest.mark.asyncio
async def test_a_broken_reporter_does_not_stop_the_scan(agent):
    """Progress output is decoration; a scan is not.

    A closed pipe — `./start.sh | head` — must cost the printing, not the trading.
    """
    def explode(_):
        raise BrokenPipeError("stdout is gone")

    results = await agent.run_once(["SPY", "NVDA"], on_start=explode, on_result=explode)
    assert len(results) == 2
