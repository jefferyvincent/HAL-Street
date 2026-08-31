"""Contracts you have ordered are exposure, whether or not the broker has booked them.

Both concentration gates count gross contracts out of `ctx.positions`, which is the
broker's list — and a resting limit order is not in it. So on 2026-08-31 the agent
placed a SPY spread at 14:15, the order sat unfilled, and at 14:45 the gate looked,
saw no SPY contracts, and approved a second one. It would have done that every half
hour until the throttle stopped it, and if several filled together the book would hold
several times the cap the gate believed it was enforcing.

The commitment is real the moment the order is accepted. Counting it is the
conservative reading and the only one that matches what the account can end up holding.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.gates.base import Limits
from halstreet.gates.circuit import correlated_exposure
from halstreet.gates.portfolio import underlying_concentration


def _committed(symbol: str, qty: int) -> dict:
    return {"symbol": symbol, "qty": Decimal(qty)}


def test_a_working_order_counts_against_the_per_name_cap(ctx, vertical_spread):
    """The reported bug, as a gate."""
    from dataclasses import replace

    at_cap = replace(ctx, limits=Limits(max_positions_per_underlying=1),
                     pending=[_committed("SPY261016P00765000", -2),
                              _committed("SPY261016P00763000", 2)])
    assert not underlying_concentration(vertical_spread, at_cap).passed


def test_it_is_counted_alongside_what_the_broker_has_booked(ctx, vertical_spread):
    """Not instead of. A book holding one filled spread and one working order is
    carrying both, and a gate that saw only the newer would let it double."""
    from dataclasses import replace

    both = replace(ctx, limits=Limits(max_positions_per_underlying=2),
                   positions=[_committed("SPY261016P00700000", -2)],
                   pending=[_committed("SPY261016P00765000", -2)])
    assert not underlying_concentration(vertical_spread, both).passed


def test_the_correlated_basket_counts_it_too(ctx, vertical_spread):
    """Otherwise the size problem simply relocates to the group."""
    from dataclasses import replace

    at_cap = replace(ctx, limits=Limits(max_correlated_positions=1),
                     pending=[_committed("QQQ261016C00765000", -2),
                              _committed("QQQ261016C00775000", 2)])
    assert not correlated_exposure(vertical_spread, at_cap).passed


def test_nothing_committed_leaves_the_gate_exactly_as_it_was(ctx, vertical_spread):
    assert underlying_concentration(vertical_spread, ctx).passed


def test_the_reason_says_the_contracts_are_ordered_not_held(ctx, vertical_spread):
    """A reader comparing the gate's number against the broker's positions would
    otherwise find it inexplicably too high."""
    from dataclasses import replace

    over = replace(ctx, limits=Limits(max_positions_per_underlying=1),
                   pending=[_committed("SPY261016P00765000", -2),
                            _committed("SPY261016P00763000", 2)])
    reason = underlying_concentration(vertical_spread, over).reason
    assert "order" in reason.lower() or "working" in reason.lower()
