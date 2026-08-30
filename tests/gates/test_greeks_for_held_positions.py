"""The gate that quietly capped the book at one underlying.

`portfolio-greek-bounds` reads greeks out of `ctx.chain` and fails closed on a missing
one, which is right: a book you cannot measure is a book you must not add to. But the
chain handed to it is the one fetched for the underlying being *scanned*, and a held
position in any other name is not in it.

So the moment the agent held a QQQ spread, every SPY proposal was rejected — not
because the exposure was too large but because two QQQ contracts had no greeks in a SPY
chain nobody had asked to include them in. Measured on 2026-08-30: fifteen gates passed,
this one failed, and the record behind it is one position held since 27 August and no
second name ever opened.

The fail-closed instinct is correct and stays. What was wrong is the input.
"""

from __future__ import annotations

import pytest


class _Client:
    """Records which symbols were asked for, and answers with greeks."""

    option_feed = "indicative"

    def __init__(self):
        self.snapshot_calls: list[list[str]] = []

    async def get_option_snapshot(self, symbols):
        self.snapshot_calls.append(list(symbols))
        return {"snapshots": {s: {"greeks": {"delta": 0.2, "vega": 0.05}} for s in symbols}}


@pytest.mark.asyncio
async def test_the_scan_chain_is_topped_up_with_the_contracts_already_held():
    """One extra call for the legs the book is carrying, so the gate can measure them."""
    from halstreet.agent.cerebellum.loop import chain_with_held

    client = _Client()
    chain = {"SPY261016P00755000": {"greeks": {"delta": -0.3, "vega": 0.04}}}
    held = ["QQQ261016C00765000", "QQQ261016C00775000"]

    out = await chain_with_held(client, chain, held)
    assert set(out) == {"SPY261016P00755000", *held}
    assert client.snapshot_calls == [held], "only the ones the chain was missing"


@pytest.mark.asyncio
async def test_a_contract_already_in_the_chain_is_not_fetched_again():
    """The scanned name's own held legs are already priced. Asking twice is a round
    trip to learn nothing."""
    from halstreet.agent.cerebellum.loop import chain_with_held

    client = _Client()
    chain = {"SPY261016P00755000": {"greeks": {"delta": -0.3, "vega": 0.04}}}
    out = await chain_with_held(client, chain, ["SPY261016P00755000"])
    assert client.snapshot_calls == []
    assert out == chain


@pytest.mark.asyncio
async def test_nothing_held_costs_no_call_at_all():
    from halstreet.agent.cerebellum.loop import chain_with_held

    client = _Client()
    assert await chain_with_held(client, {"X": {}}, []) == {"X": {}}
    assert client.snapshot_calls == []


@pytest.mark.asyncio
async def test_the_scan_chain_wins_where_both_have_a_contract():
    """The scan chain was fetched for this cycle with this cycle's window. A snapshot
    top-up must not overwrite it with a second opinion about the same contract."""
    from halstreet.agent.cerebellum.loop import chain_with_held

    client = _Client()
    chain = {"A": {"greeks": {"delta": 0.9, "vega": 0.9}}}
    out = await chain_with_held(client, chain, ["A", "B"])
    assert out["A"]["greeks"]["delta"] == 0.9


@pytest.mark.asyncio
async def test_a_failed_top_up_leaves_the_scan_chain_alone_rather_than_emptying_it():
    """The gate still fails closed on what is missing — which is the correct outcome
    and the correct reason. Losing the scanned chain too would turn one unmeasurable
    position into an unmeasurable cycle."""
    from halstreet.agent.cerebellum.loop import chain_with_held
    from halstreet.execution.mcp_client import MCPError

    class Broken(_Client):
        async def get_option_snapshot(self, symbols):
            raise MCPError("snapshot unavailable")

    chain = {"SPY261016P00755000": {"greeks": {"delta": -0.3}}}
    assert await chain_with_held(Broken(), chain, ["QQQ261016C00765000"]) == chain


@pytest.mark.asyncio
async def test_the_cycle_tops_the_chain_up_before_the_gates_see_it():
    """The whole point. A gate handed the untopped chain rejects on a contract nobody
    asked the broker about."""
    import inspect

    from halstreet.agent.cerebellum import loop
    assert "chain_with_held" in inspect.getsource(loop.Agent.snapshot)
