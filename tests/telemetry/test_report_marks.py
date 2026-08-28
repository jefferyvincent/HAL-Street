"""Marking the open book for the results report.

Two rules with money behind them. A structure gets an unrealized figure only if every
leg priced — a mark computed from one leg of a vertical is not a smaller number, it is
a wrong one, and it goes into a report a judge reads. And an unreachable broker has to
be distinguishable from an empty book, because both produce `{}` and only one of them
means the unrealized column is missing rather than zero.

This is the one part of `./start.sh report` with a decision in it, and it had no test
while it sat in `scripts/report.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.hippocampus.ledger import OpenStructure
from halstreet.config import ConfigError
from halstreet.execution.mcp_client import MCPError
from halstreet.telemetry import report


class _Book:
    """Just the attribute `live_marks` and `marks_from` read off a ledger."""

    def __init__(self, *structures):
        self.open_structures = list(structures)


def _structure(sid="s1", **legs):
    return OpenStructure(structure_id=sid, name=f"{sid} spread", underlying="SPY",
                         qty=1, legs=legs or {"SPY261016C00760000": -1},
                         opened_at="2026-08-20T14:00:00Z")


def _quote(bid, ask):
    return {"latestQuote": {"bp": bid, "ap": ask}}


VERTICAL = _structure("v1", SPY261016C00760000=-1, SPY261016C00765000=1)


# --- snapshot_chain -----------------------------------------------------------


def test_the_quote_map_is_unwrapped_when_the_response_wraps_it():
    inner = {"SPY261016C00760000": _quote("1.00", "1.10")}
    assert report.snapshot_chain({"snapshots": inner}) == inner


def test_a_bare_quote_map_is_used_as_is():
    payload = {"SPY261016C00760000": _quote("1.00", "1.10")}
    assert report.snapshot_chain(payload) == payload


@pytest.mark.parametrize("payload", [None, [], "text", 7])
def test_a_shape_that_is_not_a_map_yields_no_quotes(payload):
    assert report.snapshot_chain(payload) == {}


# --- marks_from ---------------------------------------------------------------


def test_a_fully_priced_structure_is_marked():
    chain = {"SPY261016C00760000": _quote("2.00", "2.20"),
             "SPY261016C00765000": _quote("1.00", "1.20")}
    marks = report.marks_from(_Book(VERTICAL), chain)
    # Short the 760 at a 2.10 mid, long the 765 at 1.10: held for a 1.00 credit.
    assert marks == {"v1": Decimal("-1.00")}


def test_a_structure_missing_one_leg_quote_is_left_out_entirely():
    """Not marked at a partial value — omitted.

    One leg of a vertical priced without the other reads as an outright position, and
    the figure it produces is not "less accurate", it is a different trade.
    """
    chain = {"SPY261016C00760000": _quote("2.00", "2.20")}
    assert report.marks_from(_Book(VERTICAL), chain) == {}


def test_a_leg_quoted_with_no_prices_counts_as_missing():
    chain = {"SPY261016C00760000": _quote("2.00", "2.20"),
             "SPY261016C00765000": {"latestQuote": {}}}
    assert report.marks_from(_Book(VERTICAL), chain) == {}


def test_one_unpriceable_structure_does_not_suppress_the_others():
    priced = _structure("s2", SPY261016P00745000=-1)
    chain = {"SPY261016P00745000": _quote("0.90", "1.10")}
    marks = report.marks_from(_Book(VERTICAL, priced), chain)
    assert set(marks) == {"s2"}


def test_an_empty_chain_marks_nothing_rather_than_marking_zero():
    assert report.marks_from(_Book(VERTICAL), {}) == {}


# --- live_marks: why it is empty ----------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_book_returns_no_note():
    """Nothing open is not a problem, and must not print as one."""
    marks, note = await report.live_marks("dev", _Book())
    assert marks == {}
    assert note is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    MCPError("server not installed"),
    ConfigError("no keys for dev"),
])
async def test_an_unreachable_broker_is_reported_rather_than_read_as_flat(
        failure, monkeypatch):
    """The distinction Constitution VII exists for, in the place where it costs a number.

    Both outcomes are `{}`. Only one of them means "the unrealized column is missing";
    the other means "every position is worth nothing". Printed without the note, a
    report of realized P&L alone looks complete.
    """
    def _boom(env):
        raise failure

    monkeypatch.setattr(report.AlpacaMCP, "from_env", staticmethod(_boom))
    marks, note = await report.live_marks("dev", _Book(VERTICAL))
    assert marks == {}
    assert note and "unrealized P&L omitted" in note
    assert str(failure) in note


@pytest.mark.asyncio
async def test_quotes_are_requested_once_for_the_deduplicated_legs(monkeypatch):
    asked: list[list[str]] = []

    class _Client:
        async def get_option_snapshot(self, symbols):
            asked.append(list(symbols))
            return {"snapshots": {s: _quote("1.00", "1.00") for s in symbols}}

    monkeypatch.setattr(report.AlpacaMCP, "from_env", staticmethod(lambda env: _Client()))
    shared = _structure("s3", SPY261016C00760000=1)
    marks, note = await report.live_marks("dev", _Book(VERTICAL, shared))

    assert note is None
    assert set(marks) == {"v1", "s3"}
    # One call, sorted, each symbol once — the 760 leg is in both structures.
    assert asked == [["SPY261016C00760000", "SPY261016C00765000"]]
