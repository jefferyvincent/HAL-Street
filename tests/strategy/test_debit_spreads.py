"""Long verticals — the half of the menu that was missing.

Every profile built credit structures only, so a bullish read could be expressed one
way: by selling puts. On 2026-09-02 the judge said so itself on DELL — "the correct
expression would be a long-delta debit structure, which was not on the menu" — declined,
and the agent traded nothing all day. Six of its seven closed trades to that point were
short call spreads and the book was down $65.

It matters more than a missing option. Selling premium is a bet that implied vol is
generous; every name scanned that day had realized vol running *above* implied, which
is the condition under which short premium has negative expectancy by construction. In
that regime the agent could correctly refuse to trade and could do nothing else. A long
vertical is the trade that regime calls for, and it could not build one.
"""
from datetime import date
from decimal import Decimal

import pytest

from halstreet.marketdata.occ import Right
from halstreet.strategy import profiles as P
from halstreet.strategy.candidates import Quote, debit_spread

EXPIRY = date(2026, 10, 16)


def _q(strike, right, bid, ask, delta, iv="0.20"):
    from halstreet.marketdata.occ import occ, parse
    sym = occ("SPY", EXPIRY, right, Decimal(str(strike)))
    return Quote(contract=parse(sym), bid=Decimal(str(bid)), ask=Decimal(str(ask)),
                 delta=Decimal(str(delta)), iv=Decimal(iv),
                 open_interest=1000, volume=100)


CALLS = [
    _q(760, Right.CALL, "12.00", "12.20", "0.62"),
    _q(765, Right.CALL, "9.00", "9.20", "0.50"),
    _q(770, Right.CALL, "6.40", "6.60", "0.38"),
    _q(775, Right.CALL, "4.30", "4.50", "0.26"),
]
PUTS = [
    _q(750, Right.PUT, "4.30", "4.50", "-0.26"),
    _q(755, Right.PUT, "6.40", "6.60", "-0.38"),
    _q(760, Right.PUT, "9.00", "9.20", "-0.50"),
    _q(765, Right.PUT, "12.00", "12.20", "-0.62"),
]


def test_a_long_call_vertical_buys_the_near_strike_and_sells_the_far_one():
    c = debit_spread(CALLS + PUTS, Right.CALL, Decimal("0.50"), 1, 45,
                     spot=Decimal(765))
    assert c is not None
    sides = {leg["symbol"][-8:]: leg["side"] for leg in c.legs}
    assert sides == {"00765000": "buy", "00770000": "sell"}


def test_a_long_put_vertical_sells_the_lower_strike():
    """The mirror. Buying the 760 put and selling the 755 profits as price falls —
    getting the sign wrong here builds a credit spread wearing a debit spread's name."""
    c = debit_spread(CALLS + PUTS, Right.PUT, Decimal("0.50"), 1, 45,
                     spot=Decimal(760))
    assert c is not None
    sides = {leg["symbol"][-8:]: leg["side"] for leg in c.legs}
    assert sides == {"00760000": "buy", "00755000": "sell"}


def test_the_net_is_a_debit_and_priced_against_us_on_both_legs():
    """Buy at the ask, sell at the bid — the same convention the credit builder uses.
    Quoting at mid is how a structure acquires edge it never had."""
    c = debit_spread(CALLS + PUTS, Right.CALL, Decimal("0.50"), 1, 45,
                     spot=Decimal(765))
    assert c.net == Decimal("9.20") - Decimal("6.40")   # long ask, short bid
    assert c.net > 0


def test_max_loss_is_the_premium_paid_and_nothing_more():
    """The whole argument for a debit structure overnight: the gap cannot take more
    than what was staked."""
    c = debit_spread(CALLS + PUTS, Right.CALL, Decimal("0.50"), 1, 45,
                     spot=Decimal(765))
    assert c.max_loss_usd == Decimal("2.80") * 100


def test_max_gain_is_the_width_less_the_premium():
    c = debit_spread(CALLS + PUTS, Right.CALL, Decimal("0.50"), 1, 45,
                     spot=Decimal(765))
    assert c.max_gain_usd == (Decimal(5) - Decimal("2.80")) * 100


def test_a_debit_wider_than_the_spread_itself_is_refused():
    """It can never profit. Paying $6 for $5 of width is a structure whose best
    outcome is a loss, and it must not reach the menu to be ranked."""
    silly = [_q(765, Right.CALL, "9.00", "12.00", "0.50"),
             _q(770, Right.CALL, "1.00", "6.60", "0.38")]
    assert debit_spread(silly, Right.CALL, Decimal("0.50"), 1, 45,
                        spot=Decimal(765)) is None


def test_it_is_named_and_kinded_as_a_debit():
    c = debit_spread(CALLS + PUTS, Right.CALL, Decimal("0.50"), 1, 45,
                     spot=Decimal(765))
    assert c.kind == P.CALL_DEBIT
    assert "call debit spread" in c.name
    assert c.name.startswith("SPY ")


def test_a_strike_the_chain_does_not_carry_builds_nothing():
    assert debit_spread(CALLS, Right.CALL, Decimal("0.50"), 99, 45,
                        spot=Decimal(765)) is None


def test_the_debit_kinds_are_registered_as_debit_structures():
    """`scoring.iv_regime_fit` reads these sets to decide that a long vertical wants
    *low* implied vol. Left out, a debit structure would be scored as though it wanted
    the same regime as the credit spreads it exists to replace."""
    assert P.CALL_DEBIT in P.DEBIT_STRUCTURES
    assert P.PUT_DEBIT in P.DEBIT_STRUCTURES
    assert not (P.DEBIT_STRUCTURES & P.CREDIT_STRUCTURES)


@pytest.mark.parametrize("kind,wants", [(P.CALL_DEBIT, "bullish"), (P.PUT_DEBIT, "bearish")])
def test_the_direction_each_one_wants_is_declared(kind, wants):
    """A long call vertical is bullish; the credit spread that wants the same thing is
    the *put* credit spread. Getting this mapping wrong scores every candidate against
    the opposite of the read that built it."""
    from halstreet.strategy.scoring import STRUCTURE_BIAS
    assert STRUCTURE_BIAS[kind] == wants
