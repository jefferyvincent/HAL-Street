"""Contract validation and the DTE floor. Each test proves a rejection."""

from __future__ import annotations

from decimal import Decimal

from halstreet.gates.contract import (
    CONTRACT_EXISTS,
    DTE_FLOOR,
    contract_exists,
    dte_floor,
    on_the_menu,
)
from halstreet.marketdata.occ import Right
from tests.gates.conftest import SOON, TODAY, leg, offered, proposal, sym


def test_rejects_a_strike_that_was_never_listed(ctx):
    """The anti-hallucination case: 762.50 parses fine and does not exist."""
    ghost = sym(Decimal("762.5"))
    from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
    from halstreet.gates.base import Proposal
    bad = Proposal(
        Structure("ghost strike",
                  (Leg(ghost, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),),
                  limit_price=Decimal("1.00")),
        "SPY",
    )
    r = contract_exists(bad, ctx)
    assert not r.passed
    assert r.gate == CONTRACT_EXISTS
    assert "hallucinated strike" in r.reason


def test_rejects_a_leg_on_the_wrong_underlying(ctx):
    from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
    from halstreet.gates.base import Proposal
    from halstreet.marketdata.occ import occ
    from tests.gates.conftest import FAR
    wrong = occ("QQQ", FAR, Right.CALL, Decimal(765))
    ctx.chain[wrong] = {"latestQuote": {"bp": 1, "ap": 1.1}, "openInterest": 9999}
    p = Proposal(
        Structure("mixed", (Leg(wrong, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),),
                  limit_price=Decimal("1.00")),
        "SPY",
    )
    r = contract_exists(p, ctx)
    assert not r.passed
    assert "wrong underlying" in r.reason


def test_fails_closed_with_no_chain(vertical_spread, ctx, limits):
    from halstreet.gates.base import GateContext
    empty = GateContext(account=ctx.account, chain={}, limits=limits, asof=TODAY)
    r = contract_exists(vertical_spread, empty)
    assert not r.passed
    assert "no chain supplied" in r.reason


def test_allows_legs_present_in_the_chain(vertical_spread, ctx):
    assert contract_exists(vertical_spread, ctx).passed


def test_rejects_a_short_leg_two_days_out(ctx):
    """docs/TESTING.md: 'Short leg 2 DTE' -> DTE floor."""
    p = proposal(leg(765, expiry=SOON), leg(770, long=False, expiry=SOON))
    r = dte_floor(p, ctx)
    assert not r.passed
    assert r.gate == DTE_FLOOR
    assert "2 days to expiry" in r.reason


def test_dte_judged_on_the_nearest_leg_not_the_furthest(ctx):
    """A calendar whose front leg expires in 2 days is a 2-day problem."""
    p = proposal(leg(765, expiry=SOON, long=False), leg(765))
    assert not dte_floor(p, ctx).passed


def test_zero_dte_rejection_names_the_greeks_consequence(ctx):
    """0DTE is refused for risk AND because Alpaca returns no greeks for it."""
    p = proposal(leg(765, expiry=TODAY), leg(770, long=False, expiry=TODAY))
    r = dte_floor(p, ctx)
    assert not r.passed
    assert "no greeks for 0DTE" in r.reason


def test_allows_a_far_dated_structure(vertical_spread, ctx):
    assert dte_floor(vertical_spread, ctx).passed


# --- from-the-menu ----------------------------------------------------------------
#
# The gate that closes the one place this project's thesis leaked. "Legs come from the
# candidates given to you" was a sentence in the system prompt for the whole build.
# The model complied; nothing made it.

def test_a_structure_from_the_menu_passes(ctx):
    p = proposal(leg(765), leg(770, long=False))
    assert on_the_menu(p, offered(ctx, p)).passed


def test_a_structure_that_was_never_offered_is_rejected(ctx):
    """The gap `contract-validation` cannot see.

    Every leg here is a real, listed contract, so the anti-hallucination gate passes
    it happily. But the strategy engine never built this combination, so it carries no
    score, no liquidity screen and no viability check against friction — it would be
    the one trade in the run that nothing deterministic ever looked at.
    """
    on_menu = proposal(leg(765), leg(770, long=False))
    invented = proposal(leg(775), leg(780, long=False))
    ctx_with_menu = offered(ctx, on_menu)

    assert contract_exists(invented, ctx_with_menu).passed, "the strikes are real"
    result = on_the_menu(invented, ctx_with_menu)
    assert not result.passed
    assert "not on the menu" in result.reason


def test_legs_recombined_across_two_candidates_are_rejected(ctx):
    """The subtle version, and the reason the gate compares signatures.

    Both candidates were offered and every leg is real. The structure is not: it is a
    third thing, assembled from halves of two others, with a payoff nobody scored.
    """
    a = proposal(leg(765), leg(770, long=False))
    b = proposal(leg(780), leg(785, long=False))
    frankenstein = proposal(leg(765), leg(785, long=False))
    assert not on_the_menu(frankenstein, offered(ctx, a, b)).passed


def test_leg_order_and_structure_name_do_not_matter(ctx):
    """A trade is its legs. Re-ordering them or renaming it changes nothing."""
    built = proposal(leg(765), leg(770, long=False), name="put credit spread")
    reordered = proposal(leg(770, long=False), leg(765), name="something else")
    assert on_the_menu(reordered, offered(ctx, built)).passed


def test_size_is_not_part_of_the_signature(ctx):
    """Quantity is a separate question, and the sizing gates already ask it.

    Folding qty into this gate would reject a menu structure the model chose to take
    ten of, and blame the wrong rule for it — `max-loss-per-position` is the gate that
    has an opinion about size, and it should be the one that speaks.
    """
    one = proposal(leg(765), leg(770, long=False), qty=1)
    ten = proposal(leg(765), leg(770, long=False), qty=10)
    assert on_the_menu(ten, offered(ctx, one)).passed


def test_it_fails_closed_when_no_menu_was_recorded(ctx):
    """A gate that cannot see what was offered must not certify that this came from it."""
    p = proposal(leg(765), leg(770, long=False))
    result = on_the_menu(p, ctx)
    assert not result.passed
    assert "no candidate menu" in result.reason
