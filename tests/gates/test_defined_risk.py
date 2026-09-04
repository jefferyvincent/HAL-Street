"""Every gate here has a test that proves it REJECTS. See docs/TESTING.md.

The rejection is the point. A gate tested only on the happy path is decoration, and
these are also the demo: a judge watching a deliberately reckless proposal get stopped
by name is a stronger argument than any backtest curve.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
from halstreet.gates.base import GateContext, Limits, Proposal, evaluate
from halstreet.gates.defined_risk import (
    DEFINED_RISK,
    MAX_LOSS,
    PORTFOLIO_RISK,
    defined_risk_only,
    max_loss_per_contract,
    max_loss_per_position,
    options_buying_power,
    portfolio_risk_ceiling,
)
from halstreet.marketdata.occ import PayoffLeg, Right
from tests.gates.conftest import leg, proposal

# --- defined risk: the flagship ----------------------------------------------

def test_rejects_a_naked_short_call(naked_call, ctx):
    """The canonical case. Loss grows without limit as SPY rises."""
    r = defined_risk_only(naked_call, ctx)
    assert not r.passed
    assert r.gate == DEFINED_RISK
    assert "unbounded" in r.reason


def test_rejects_a_ratio_spread_that_is_net_short_calls(ctx):
    """Buy one, sell two. Looks like a spread; is not defined risk.

    This is why the gate works from payoff rather than from strategy names — nothing
    about the shape of this proposal says "naked".
    """
    p = proposal(leg(765), leg(770, long=False, ratio=2), limit=Decimal("1.00"))
    r = defined_risk_only(p, ctx)
    assert not r.passed
    assert "net short 1 call" in r.reason


def test_allows_a_vertical(vertical_spread, ctx):
    assert defined_risk_only(vertical_spread, ctx).passed


def test_allows_an_iron_condor(condor, ctx):
    assert defined_risk_only(condor, ctx).passed


def test_naked_short_put_is_bounded_and_left_to_the_size_gate(ctx):
    """A short put cannot lose without limit — the underlying stops at zero — so this
    gate passes it and the max-loss gate is what refuses it."""
    p = proposal(leg(750, Right.PUT, long=False), limit=Decimal("-5.00"))
    assert defined_risk_only(p, ctx).passed
    assert not max_loss_per_position(p, ctx).passed


def test_fails_closed_on_an_unparseable_symbol(ctx):
    bad = Structure(
        name="junk",
        legs=(Leg("NOT-AN-OCC-SYMBOL", 1, Side.BUY, PositionIntent.BUY_TO_OPEN),),
        limit_price=Decimal("1.00"),
    )
    r = defined_risk_only(Proposal(bad, "SPY"), ctx)
    assert not r.passed
    assert "not a parseable OCC" in r.reason


# --- max loss ------------------------------------------------------------------

def test_rejects_a_structure_over_the_per_position_cap(ctx, limits):
    """A 100-wide spread risks $5,000 against the cap.

    The cap is pinned explicitly here rather than taken from .env — a test that
    asserts whatever the config currently says proves nothing about the gate, and
    silently changes meaning every time someone tunes the limit.
    """
    from dataclasses import replace

    from halstreet.gates.base import GateContext
    tight = GateContext(
        account=ctx.account, positions=ctx.positions, chain=ctx.chain,
        limits=replace(limits, max_loss_per_position_usd=Decimal(250)),
        asof=ctx.asof, spot=ctx.spot,
    )
    p = proposal(leg(700), leg(800, long=False), limit=Decimal("50.00"))
    r = max_loss_per_position(p, tight)
    assert not r.passed
    assert r.gate == MAX_LOSS
    assert "exceeds the $250.00 cap" in r.reason


def test_rejects_when_size_pushes_it_over(ctx):
    """One contract fits; twenty do not. The cap is on the position, not the unit."""
    one = proposal(leg(765), leg(770, long=False), qty=1, limit=Decimal("2.00"))
    many = proposal(leg(765), leg(770, long=False), qty=20, limit=Decimal("2.00"))
    assert max_loss_per_position(one, ctx).passed
    assert not max_loss_per_position(many, ctx).passed


def test_fails_closed_without_a_limit_price(ctx):
    """No limit price means the premium — and so the max loss — is unknown."""
    p = proposal(leg(765), leg(770, long=False), limit=None)
    r = max_loss_per_position(p, ctx)
    assert not r.passed
    assert "unknown at gate time" in r.reason


def test_debit_spread_max_loss_is_the_premium_paid():
    """Long 765 / short 770 for $2.00: risk the $200 paid, nothing more."""
    legs = [
        PayoffLeg(Right.CALL, Decimal(765), 1, True),
        PayoffLeg(Right.CALL, Decimal(770), 1, False),
    ]
    assert max_loss_per_contract(legs, Decimal("2.00")) == Decimal("200.00")


def test_credit_spread_max_loss_is_width_less_credit():
    """Short 765 / long 770 for a $2.00 credit: $500 wide, keep $200, risk $300."""
    legs = [
        PayoffLeg(Right.CALL, Decimal(765), 1, False),
        PayoffLeg(Right.CALL, Decimal(770), 1, True),
    ]
    assert max_loss_per_contract(legs, Decimal("-2.00")) == Decimal("300.00")


def test_unbounded_structure_has_no_max_loss():
    legs = [PayoffLeg(Right.CALL, Decimal(770), 1, False)]
    assert max_loss_per_contract(legs, Decimal("-3.00")) is None


# --- portfolio ceiling ----------------------------------------------------------

def test_rejects_when_max_loss_is_too_large_a_share_of_equity(ctx, limits):
    """$10,000 of risk is 10% of $100k and passes; against $20k of equity it is 50%."""
    p = proposal(leg(700), leg(800, long=False), limit=Decimal("50.00"))
    small = GateContext(
        account={"equity": "20000.00", "account_number": "PA1"},
        chain=ctx.chain, limits=limits, asof=ctx.asof,
    )
    r = portfolio_risk_ceiling(p, small)
    assert not r.passed
    assert r.gate == PORTFOLIO_RISK
    assert "over the 15% ceiling" in r.reason


def test_fails_closed_on_unreadable_equity(vertical_spread, ctx, limits):
    broken = GateContext(
        account={"equity": None, "account_number": "PA1"},
        chain=ctx.chain, limits=limits, asof=ctx.asof,
    )
    r = portfolio_risk_ceiling(vertical_spread, broken)
    assert not r.passed
    assert "unreadable" in r.reason


# --- the framework itself --------------------------------------------------------

GATES = [defined_risk_only, max_loss_per_position, portfolio_risk_ceiling]


def test_every_gate_runs_even_after_one_rejects(naked_call, ctx):
    """No short-circuit: the journal wants every reason, not the first one."""
    decision = evaluate(naked_call, ctx, GATES)
    assert len(decision.results) == len(GATES)
    assert not decision.approved
    assert len(decision.rejections) >= 2


def test_a_gate_that_raises_counts_as_a_rejection(vertical_spread, ctx):
    """A crashing gate has not proven anything safe."""
    def exploding(proposal, ctx):
        raise RuntimeError("boom")
    exploding.gate_name = "exploding"

    decision = evaluate(vertical_spread, ctx, [exploding])
    assert not decision.approved
    assert "gate raised RuntimeError" in decision.rejections[0].reason


def test_approved_proposal_passes_every_gate(vertical_spread, ctx):
    decision = evaluate(vertical_spread, ctx, GATES)
    assert decision.approved, decision.summary()
    assert "APPROVED" in decision.summary()


def test_summary_names_each_failing_gate(naked_call, ctx):
    summary = evaluate(naked_call, ctx, GATES).summary()
    assert "REJECTED" in summary
    assert DEFINED_RISK in summary


# --- options buying power -------------------------------------------------------

def test_a_structure_bigger_than_options_buying_power_is_rejected(vertical_spread, ctx):
    # Every other sizing gate measures against equity. The broker collateralises
    # options out of `options_buying_power`, which is cash and much smaller than the
    # headline margin figure — measured on this account, $89,817 against $359,270.
    import dataclasses
    ctx = dataclasses.replace(ctx, account={**ctx.account, "options_buying_power": "100.00"})
    result = options_buying_power(vertical_spread, ctx)
    assert not result.passed
    assert "collateral" in result.reason


def test_the_headline_buying_power_is_not_what_is_checked(vertical_spread, ctx):
    # A gate reading `buying_power` would see 4x margin and approve a structure the
    # broker cannot collateralise.
    import dataclasses
    ctx = dataclasses.replace(ctx, account={**ctx.account,
                                            "buying_power": "400000.00",
                                            "options_buying_power": "10.00"})
    assert not options_buying_power(vertical_spread, ctx).passed


def test_a_reserve_is_kept_back_to_pay_for_exits(vertical_spread, ctx):
    # Running buying power to exactly zero leaves nothing to close with, and some
    # exits are debits. This spread is a $2.00 debit on $5 of width, so max loss —
    # and therefore collateral — is $200. At $220 available the structure fits, and
    # only the reserve stops it.
    import dataclasses
    account = {**ctx.account, "options_buying_power": "220.00"}

    reserved = dataclasses.replace(
        ctx, account=account, limits=Limits(min_buying_power_headroom_pct=Decimal(20)))
    assert not options_buying_power(vertical_spread, reserved).passed

    # The same account with no reserve would have taken it — which is what shows the
    # rejection came from the headroom rule and not from the size.
    none_kept = dataclasses.replace(
        ctx, account=account, limits=Limits(min_buying_power_headroom_pct=Decimal(0)))
    assert options_buying_power(vertical_spread, none_kept).passed


def test_unreadable_buying_power_fails_closed(vertical_spread, ctx):
    import dataclasses
    for bad in (None, "", "n/a"):
        broken = dataclasses.replace(ctx, account={**ctx.account, "options_buying_power": bad})
        assert not options_buying_power(vertical_spread, broken).passed


def test_an_unpriced_structure_has_unknown_collateral(ctx):
    from halstreet.execution.structures import Structure
    from halstreet.gates.base import Proposal

    from .conftest import leg
    unpriced = Proposal(
        structure=Structure(name="unpriced", legs=(leg(765), leg(770, long=False)),
                            qty=1, limit_price=None),
        underlying="SPY")
    assert not options_buying_power(unpriced, ctx).passed
