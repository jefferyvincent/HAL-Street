"""Portfolio-level gates: concentration, greek bounds, assignment proximity.

The concentration tests encode the finding from the live paper run on 2026-08-26:
Alpaca nets legs across structures, so the account reports contracts, not structures.
A gate counting structures would have scored a shared short strike as diversification.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.gates.base import GateContext
from halstreet.gates.portfolio import (
    ASSIGNMENT,
    CONCENTRATION,
    GREEK_BOUNDS,
    assignment_proximity,
    net_contracts_by_root,
    portfolio_greek_bounds,
    underlying_concentration,
)
from tests.gates.conftest import SOON, SPOT, TODAY, leg, proposal, sym

# --- concentration, counted in contracts ---------------------------------------

def test_netting_is_measured_the_way_the_broker_reports_it():
    """Regression on the live finding: two structures sharing a short strike net.

    The account showed SPY261016C00770000 at qty -2 after a vertical and a condor both
    sold it — one position, not two tagged to their parents.
    """
    positions = [
        {"symbol": "SPY261016C00770000", "qty": "-2"},
        {"symbol": "SPY261016C00775000", "qty": "1"},
    ]
    assert net_contracts_by_root(positions) == {"SPY": Decimal(-1)}


def test_rejects_when_the_underlying_is_already_full(vertical_spread, ctx, limits):
    """Existing SPY contracts plus the proposal exceed the implied cap."""
    loaded = GateContext(
        account=ctx.account,
        positions=[
            {"symbol": "SPY261016C00770000", "qty": "-2"},
            {"symbol": "SPY261016C00775000", "qty": "2"},
        ],
        chain=ctx.chain, limits=limits, asof=TODAY, spot=SPOT,
    )
    r = underlying_concentration(vertical_spread, loaded)
    assert not r.passed
    assert r.gate == CONCENTRATION
    assert "counts contracts, not structures" in r.reason


def test_a_different_underlying_does_not_count(vertical_spread, ctx, limits):
    other = GateContext(
        account=ctx.account,
        positions=[{"symbol": "QQQ261016C00500000", "qty": "-8"}],
        chain=ctx.chain, limits=limits, asof=TODAY, spot=SPOT,
    )
    assert underlying_concentration(vertical_spread, other).passed


def test_allows_the_first_position(vertical_spread, ctx):
    assert underlying_concentration(vertical_spread, ctx).passed


# --- greek bounds ----------------------------------------------------------------

def test_fails_closed_when_a_leg_has_no_greeks(vertical_spread, ctx):
    """Alpaca omits greeks deep ITM/OTM. Unassessable is not acceptable."""
    del ctx.chain[sym(770)]["greeks"]
    r = portfolio_greek_bounds(vertical_spread, ctx)
    assert not r.passed
    assert r.gate == GREEK_BOUNDS
    assert "fails closed" in r.reason


def test_rejects_when_net_delta_breaches_the_bound(ctx, limits):
    """A big long call position runs the book's delta past the cap.

    120 contracts at 0.5 delta is 6,000 share-equivalents against a 5,000 bound —
    i.e. the book would move like 6,000 shares of SPY, which is the number the limit
    is actually about.
    """
    p = proposal(leg(765), qty=120, limit=Decimal("5.00"))
    r = portfolio_greek_bounds(p, ctx)
    assert not r.passed
    assert "net delta +6,000 share-equivalents" in r.reason


def test_delta_bound_is_in_shares_not_per_contract_deltas(ctx):
    """Regression: the bound once carried a hidden x100, so 50 meant 5,000.

    Anyone tuning MAX_NET_DELTA would have been off by two orders of magnitude.
    """
    p = proposal(leg(765), qty=99, limit=Decimal("5.00"))
    r = portfolio_greek_bounds(p, ctx)
    assert r.passed, r.reason
    assert "+4,950" in r.reason


def test_existing_positions_count_toward_the_bound(vertical_spread, ctx, limits):
    """The proposal alone is fine; the book plus the proposal is not."""
    assert portfolio_greek_bounds(vertical_spread, ctx).passed
    loaded = GateContext(
        account=ctx.account,
        positions=[{"symbol": sym(765), "qty": "120"}],
        chain=ctx.chain, limits=limits, asof=TODAY, spot=SPOT,
    )
    assert not portfolio_greek_bounds(vertical_spread, loaded).passed


def test_a_balanced_structure_passes(vertical_spread, ctx):
    assert portfolio_greek_bounds(vertical_spread, ctx).passed


# --- assignment proximity ---------------------------------------------------------

def test_rejects_a_short_leg_in_the_money_near_expiry(ctx):
    """docs/TESTING.md: ITM short legs near expiry."""
    p = proposal(leg(760, long=False, expiry=SOON), leg(755, expiry=SOON))
    r = assignment_proximity(p, ctx)
    assert not r.passed
    assert r.gate == ASSIGNMENT
    assert "ITM" in r.reason


def test_rejects_a_short_leg_just_out_of_the_money_near_expiry(ctx):
    """765 spot, 770 short call at 2 DTE: 0.65% away, inside the 2% band."""
    p = proposal(leg(770, long=False, expiry=SOON), leg(775, expiry=SOON))
    assert not assignment_proximity(p, ctx).passed


def test_the_same_strike_is_fine_with_45_days_left(ctx):
    """Distance only matters near expiry — that is the whole point of the gate."""
    p = proposal(leg(770, long=False), leg(775))
    assert assignment_proximity(p, ctx).passed


def test_long_legs_are_never_an_assignment_risk(ctx):
    """You choose whether to exercise what you own."""
    p = proposal(leg(760, expiry=SOON), leg(755, long=False, expiry=SOON))
    r = assignment_proximity(p, ctx)
    assert r.passed or "755" in r.reason


def test_fails_closed_without_a_spot_price(vertical_spread, ctx, limits):
    blind = GateContext(
        account=ctx.account, chain=ctx.chain, limits=limits, asof=TODAY, spot=None
    )
    r = assignment_proximity(vertical_spread, blind)
    assert not r.passed
    assert "no spot price" in r.reason
