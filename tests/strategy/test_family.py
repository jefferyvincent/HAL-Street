"""Which family a held structure belongs to, read off its legs.

The ledger records legs and a name, never a family — the name is prose built for a
human ("2026-10-16 765/775 call credit spread") and parsing prose to make a trading
decision is how a rename becomes a bug. The legs are the fact.

This exists so the loss cooldown can key on *what was traded*, not only on the
underlying: losing three times selling calls into a rally says nothing about whether a
put spread on the same name is a bad idea.
"""

from __future__ import annotations

from halstreet.strategy.family import OTHER, classify
from halstreet.strategy.profiles import CALL_CREDIT, IRON_CONDOR, PUT_CREDIT

P750, P760 = "SPY261016P00750000", "SPY261016P00760000"
C770, C780 = "SPY261016C00770000", "SPY261016C00780000"


def test_two_puts_are_a_put_spread():
    assert classify({P760: -1, P750: 1}) == PUT_CREDIT


def test_two_calls_are_a_call_spread():
    assert classify({C770: -1, C780: 1}) == CALL_CREDIT


def test_two_of_each_is_a_condor():
    assert classify({P750: 1, P760: -1, C770: -1, C780: 1}) == IRON_CONDOR


def test_size_does_not_change_the_family():
    """A two-contract spread is the same trade as a one-contract spread. Keying the
    cooldown on a size-sensitive family would let the same losing idea back in at a
    different quantity."""
    assert classify({P760: -2, P750: 2}) == PUT_CREDIT


def test_a_shape_it_does_not_recognise_is_named_rather_than_dropped():
    """`other`, never None.

    A structure whose family cannot be read still has a P&L, and a losing streak that
    quietly skipped it would be a cooldown with a hole in exactly the trades nobody
    anticipated. Lumping unrecognised shapes together can only bench sooner, which is
    the safe direction for a rule whose whole job is to stop losing.
    """
    assert classify({C770: -1}) == OTHER
    assert classify({P750: 1, C770: 1, C780: -1}) == OTHER
    assert classify({}) == OTHER


def test_an_unreadable_symbol_does_not_become_a_family():
    assert classify({"NOTACONTRACT": -1, C780: 1}) == OTHER
