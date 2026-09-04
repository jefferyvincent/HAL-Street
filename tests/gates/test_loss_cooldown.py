"""The cooldown gate must reject. Per docs/TESTING.md, the rejection is the test.

The agent already tells the model about its losses — `committee.reflection` puts closed
structures and their realized P&L in front of the judge. That is advice, and a
confident model can talk its way past advice; a proposal arriving with a paragraph
about why *this* time is different is exactly what a losing streak looks like from the
inside.

So the record is deterministic and the refusal is a gate. What the model may do is
propose something else.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from halstreet.gates.circuit import loss_cooldown
from halstreet.marketdata.occ import Right
from halstreet.strategy.profiles import PUT_CREDIT

from .conftest import leg, proposal


def put_spread(qty=1):
    return proposal(leg(760, Right.PUT, long=False), leg(750, Right.PUT, long=True),
                    qty=qty, limit=Decimal("-1.60"))


def call_spread():
    return proposal(leg(770, Right.CALL, long=False), leg(780, Right.CALL, long=True),
                    limit=Decimal("-1.60"))


def with_bench(ctx, record):
    return dataclasses.replace(ctx, benched=record)


def test_rejects_a_pair_that_is_resting(ctx):
    benched = {("SPY", PUT_CREDIT): "2 losing put_credit_spread trade(s) in a row"}
    result = loss_cooldown(put_spread(), with_bench(ctx, benched))
    assert not result.passed
    assert "2 losing" in result.reason


def test_allows_a_different_family_on_the_same_underlying(ctx):
    """Being wrong twice about puts says nothing about calls. A cooldown that benched
    the whole symbol would throw away the half of the book that was never tested."""
    benched = {("SPY", PUT_CREDIT): "resting"}
    assert loss_cooldown(call_spread(), with_bench(ctx, benched)).passed is True


def test_allows_the_same_family_on_a_different_underlying(ctx):
    benched = {("QQQ", PUT_CREDIT): "resting"}
    assert loss_cooldown(put_spread(), with_bench(ctx, benched)).passed is True


def test_allows_when_nothing_is_resting(ctx):
    assert loss_cooldown(put_spread(), with_bench(ctx, {})).passed is True


def test_fails_closed_when_the_record_was_never_wired(ctx):
    """`None` is not `{}`. An empty record is a measured statement that nothing is
    resting; a missing one means nobody looked, and a gate that read those the same way
    would wave every proposal through on the day the caller forgot to load the ledger.
    """
    result = loss_cooldown(put_spread(), with_bench(ctx, None))
    assert not result.passed
    assert "not available" in result.reason


def test_size_does_not_get_a_benched_pair_back_in(ctx):
    benched = {("SPY", PUT_CREDIT): "resting"}
    assert loss_cooldown(put_spread(qty=5), with_bench(ctx, benched)).passed is False
