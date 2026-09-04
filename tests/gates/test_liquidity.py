"""Liquidity floor and quoted width. Each test proves a rejection."""

from __future__ import annotations

from halstreet.gates.liquidity import LIQUIDITY, SPREAD_WIDTH, liquidity_floor, spread_width
from tests.gates.conftest import sym


def test_rejects_a_leg_with_three_open_interest(vertical_spread, ctx):
    """docs/TESTING.md: 'Leg with 3 open interest' -> liquidity floor."""
    ctx.chain[sym(770)]["openInterest"] = 3
    r = liquidity_floor(vertical_spread, ctx)
    assert not r.passed
    assert r.gate == LIQUIDITY
    assert "OI=3" in r.reason


def test_fails_closed_when_open_interest_is_absent(vertical_spread, ctx):
    """An unmeasurable leg is not a liquid one."""
    del ctx.chain[sym(770)]["openInterest"]
    r = liquidity_floor(vertical_spread, ctx)
    assert not r.passed
    assert "no openInterest" in r.reason


def test_rejects_a_forty_percent_wide_quote(vertical_spread, ctx):
    """docs/TESTING.md: 'Bid/ask 40% wide' -> spread width."""
    ctx.chain[sym(770)]["latestQuote"] = {"bp": 0.80, "ap": 1.20}
    r = spread_width(vertical_spread, ctx)
    assert not r.passed
    assert r.gate == SPREAD_WIDTH
    assert "40.0%" in r.reason


def test_one_bad_leg_condemns_the_whole_structure(condor, ctx):
    """Three liquid legs and one 40% wide is not 75% fine."""
    from tests.gates.conftest import sym as s
    ctx.chain[s(790)]["latestQuote"] = {"bp": 0.80, "ap": 1.20}
    assert not spread_width(condor, ctx).passed


def test_fails_closed_on_a_missing_quote(vertical_spread, ctx):
    ctx.chain[sym(770)]["latestQuote"] = {}
    r = spread_width(vertical_spread, ctx)
    assert not r.passed
    assert "no quote" in r.reason


def test_fails_closed_on_a_crossed_quote(vertical_spread, ctx):
    ctx.chain[sym(770)]["latestQuote"] = {"bp": 5.0, "ap": 1.0}
    assert not spread_width(vertical_spread, ctx).passed


def test_allows_tight_liquid_legs(vertical_spread, ctx):
    assert liquidity_floor(vertical_spread, ctx).passed
    assert spread_width(vertical_spread, ctx).passed


# --- open interest comes from a different endpoint than the chain ----------------

def test_missing_open_interest_names_the_actual_cause(vertical_spread, ctx):
    """Regression on a real gap: open interest is not in the chain snapshot at all.

    get_option_chain returns quotes, bars, greeks and IV; open_interest lives only in
    get_option_contracts. The gate failing closed is how that was found, so the
    message points at the merge rather than at the data.
    """
    del ctx.chain[sym(770)]["openInterest"]
    r = liquidity_floor(vertical_spread, ctx)
    assert not r.passed
    assert "chain not enriched" in r.reason


def test_rejects_a_contract_nobody_traded_today(vertical_spread, ctx):
    """Open interest is published daily and lags; volume is the live half."""
    ctx.chain[sym(770)]["dailyBar"] = {"v": 2}
    r = liquidity_floor(vertical_spread, ctx)
    assert not r.passed
    assert "vol=2" in r.reason
    assert "day stale" in r.reason


def test_fails_closed_when_volume_is_absent(vertical_spread, ctx):
    del ctx.chain[sym(770)]["dailyBar"]
    r = liquidity_floor(vertical_spread, ctx)
    assert not r.passed
    assert "no daily volume" in r.reason
