"""What reaches the menu, and what should not.

Two failures found on the live account, both structural rather than unlucky.

A **one-strike-wide spread** carried $54 of max gain against $45 of round-trip friction
on a 3-lot. It passed every gate and every EV check because the scenario deducts
friction honestly and the number still came out positive — barely. What no rule caught
was that the trade needed the market to do almost nothing wrong before the spread it
had already paid ate the edge. Structures like that are how an account bleeds out
while every individual decision looks defensible.

A **credit-only menu** meant a bullish read had one expression: sell puts. In a regime
where realized vol runs above implied that has negative expectancy by construction, so
the agent correctly declined everything and traded nothing for a whole session.
"""
from datetime import date
from decimal import Decimal

from halstreet.marketdata.occ import Right, occ
from halstreet.strategy import profiles as P
from halstreet.strategy.candidates import (
    Candidate,
    clears_friction,
    generate,
)

EXPIRY = date(2026, 10, 16)


def _cand(max_gain, slip, legs=2):
    return Candidate(
        name="test", kind=P.CALL_CREDIT,
        legs=[{"symbol": "x", "side": "sell"}] * legs,
        net=Decimal(-1), max_loss_usd=Decimal(500),
        max_gain_usd=Decimal(str(max_gain)), dte=45,
        short_delta=Decimal("0.3"), worst_spread_pct=Decimal(5),
        min_open_interest=1000, min_volume=100,
        slippage_usd=None if slip is None else Decimal(str(slip)), pop=0.7,
    )


def test_a_structure_whose_edge_the_spread_would_eat_is_refused():
    """$54 of max gain against $22.50 of round-trip crossing. Not a loss on paper —
    a trade that has to be right before it can pay for having been placed."""
    assert not clears_friction(_cand(max_gain=54, slip=Decimal("11.25")))


def test_a_structure_with_room_over_its_own_friction_passes():
    assert clears_friction(_cand(max_gain=300, slip=Decimal("11.25")))


def test_friction_is_counted_as_the_round_trip_not_one_crossing():
    """`slippage_usd` is the one-way cost. The position has to be closed as well as
    opened, and a floor that forgets the second crossing is half a floor."""
    # $80 gain against $20 one-way: fine on one crossing, not on two at 3x.
    assert not clears_friction(_cand(max_gain=80, slip=Decimal(20)))


def test_a_candidate_that_cannot_price_its_own_friction_is_kept():
    """Unknown slippage is not zero and it is not disqualifying either. The liquidity
    gates already refuse a leg nobody can quote; this rule is about the ones that can
    be quoted and still are not worth crossing."""
    assert clears_friction(_cand(max_gain=54, slip=None))


# --- and the menu builds both sides of volatility -------------------------------------

def _chain():
    """A clean SPY ladder: calls and puts, five points apart, priced sanely."""
    rows = {}
    for strike, cb, ca, pb, pa, cd in (
        (755, "15.0", "15.2", "2.3", "2.5", "0.74"),
        (760, "12.0", "12.2", "4.3", "4.5", "0.62"),
        (765, "9.0", "9.2", "6.4", "6.6", "0.50"),
        (770, "6.4", "6.6", "9.0", "9.2", "0.38"),
        (775, "4.3", "4.5", "12.0", "12.2", "0.26"),
        (780, "2.3", "2.5", "15.0", "15.2", "0.16"),
    ):
        for right, bid, ask, delta in ((Right.CALL, cb, ca, cd),
                                       (Right.PUT, pb, pa, str(-(1 - float(cd))))):
            rows[occ("SPY", EXPIRY, right, Decimal(strike))] = {
                "latestQuote": {"bp": bid, "ap": ask},
                "greeks": {"delta": delta},
                "impliedVolatility": "0.20",
                "openInterest": 5000,
                "dailyBar": {"v": 500},
            }
    return rows


def test_a_profile_that_builds_debit_verticals_gets_them_on_the_menu():
    profile = P.replace_structures(P.MODERATE, P.ALL_STRUCTURES)
    menu = generate(_chain(), spot=Decimal(765), target_dte=45, profile=profile,
                    asof=date(2026, 9, 2), limit=12)
    kinds = {c.kind for c in menu}
    assert P.DEBIT_STRUCTURES & kinds, f"no long vertical on a menu of {kinds}"


def test_a_credit_only_profile_is_unchanged():
    """The default has to stay what it was until someone chooses otherwise. A builder
    that appears on every menu the moment it is written is a behaviour change nobody
    signed off."""
    menu = generate(_chain(), spot=Decimal(765), target_dte=45,
                    profile=P.replace_structures(P.MODERATE, P.VERTICALS_AND_CONDORS),
                    asof=date(2026, 9, 2), limit=12)
    assert not (P.DEBIT_STRUCTURES & {c.kind for c in menu})
