"""Exits. The half of the system that decides the P&L number.

Numbers here are taken from the live round trip on 2026-08-26 where possible, so the
tests describe positions this account actually held.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.agent.manager import (
    Action,
    ExitPolicy,
    closing_order,
    evaluate_exit,
    exit_levels,
    mark_structure,
    review,
)
from halstreet.execution.structures import iron_condor, vertical

TODAY = date(2026, 8, 26)
P755, P760 = "SPY261016P00755000", "SPY261016P00760000"
C770, C775 = "SPY261016C00770000", "SPY261016C00775000"
C765 = "SPY261016C00765000"


def chain(**mids) -> dict[str, dict]:
    """A chain whose mids are exactly the values asked for.

    Built with Decimal arithmetic rather than floats: `float(10.78) - 0.02` is
    10.760000000000002, and that noise propagates straight through the mark into the
    P&L assertions. Alpaca's own JSON numbers round-trip cleanly through
    `Decimal(str(x))`, so this is a test-fixture concern rather than a production one —
    but a fixture that cannot express 4.04 exactly cannot test a $23 loss.
    """
    out = {}
    for sym, m in mids.items():
        mid = Decimal(str(m))
        out[sym] = {"latestQuote": {"bp": str(mid - Decimal("0.02")),
                                    "ap": str(mid + Decimal("0.02"))}}
    return out


@pytest.fixture
def policy():
    return ExitPolicy()


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(path=tmp_path / "l.json")


@pytest.fixture
def condor(ledger):
    """The condor actually traded: opened for a 4.04 credit."""
    ledger.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                       structure_id="c1", entry_price=Decimal("-4.04"))
    return ledger.open_structures[0]


@pytest.fixture
def debit_spread(ledger):
    """The vertical actually traded: opened for a 2.99 debit."""
    ledger.record_open(vertical("Oct vertical", C765, C770), "SPY",
                       structure_id="v1", entry_price=Decimal("2.99"))
    return ledger.open_structures[0]


# --- expiry beats everything -------------------------------------------------------

def test_forced_close_fires_inside_the_window(condor, policy):
    d = evaluate_exit(condor, chain(), policy, asof=date(2026, 10, 13))  # 3 DTE
    assert d.action is Action.CLOSE_BEFORE_EXPIRY
    assert d.should_close
    assert "assignment risk" in d.reason


def test_forced_close_does_not_need_a_mark(condor, policy):
    """A position we cannot price is still one we must not carry into expiry."""
    d = evaluate_exit(condor, {}, policy, asof=date(2026, 10, 14))
    assert d.action is Action.CLOSE_BEFORE_EXPIRY


def test_expiry_is_checked_before_profit(condor, policy):
    """Deep in profit but 2 DTE: it still closes for expiry, not for profit."""
    cheap = chain(**{P755: 0.01, P760: 0.02, C770: 0.02, C775: 0.01})
    d = evaluate_exit(condor, cheap, policy, asof=date(2026, 10, 14))
    assert d.action is Action.CLOSE_BEFORE_EXPIRY


# --- credit structures --------------------------------------------------------------

def test_takes_profit_at_the_target(condor, policy):
    """Opened for 4.04 credit; buy it back near 2.00 and half the credit is captured."""
    now = chain(**{P755: 0.50, P760: 1.00, C770: 2.00, C775: 1.00})
    d = evaluate_exit(condor, now, policy, asof=TODAY)
    assert d.action is Action.TAKE_PROFIT
    assert d.unrealized_usd > 0
    assert "target 50%" in d.reason


def test_stops_out_when_the_loss_doubles_the_credit(condor, policy):
    now = chain(**{P755: 0.20, P760: 1.00, C770: 12.50, C775: 0.30})
    d = evaluate_exit(condor, now, policy, asof=TODAY)
    assert d.action is Action.STOP_LOSS
    assert d.unrealized_usd < 0
    assert "stop 200%" in d.reason


def test_holds_in_between(condor, policy):
    now = chain(**{P755: 0.60, P760: 1.30, C770: 3.60, C775: 0.90})
    d = evaluate_exit(condor, now, policy, asof=TODAY)
    assert d.action is Action.HOLD
    assert not d.should_close


# --- debit structures ---------------------------------------------------------------

def test_debit_spread_profit_is_measured_against_the_premium_paid(debit_spread, policy):
    """Paid 2.99; worth ~4.60 is a >50% gain on the premium."""
    d = evaluate_exit(debit_spread, chain(**{C765: 20.00, C770: 15.40}), policy, asof=TODAY)
    assert d.action is Action.TAKE_PROFIT
    assert "paid" in d.reason


def test_debit_spread_stop_cannot_exceed_the_premium(debit_spread, policy):
    """A 200% stop on a debit spread can never fire — you cannot lose more than you
    paid — so a near-worthless spread simply holds to the expiry rule."""
    d = evaluate_exit(debit_spread, chain(**{C765: 0.10, C770: 0.05}), policy, asof=TODAY)
    assert d.action is Action.HOLD


# --- refusing to act on bad data -----------------------------------------------------

def test_will_not_act_on_a_partial_mark(condor, policy):
    """Three of four legs is not a mark."""
    partial = chain(**{P755: 0.50, P760: 1.00, C770: 2.00})
    d = evaluate_exit(condor, partial, policy, asof=TODAY)
    assert d.action is Action.UNKNOWN
    assert not d.should_close
    assert "partial mark" in d.reason


def test_reports_a_missing_entry_price_rather_than_guessing(ledger, policy):
    ledger.record_open(vertical("v", C765, C770), "SPY", structure_id="v1")
    d = evaluate_exit(ledger.open_structures[0], chain(**{C765: 5, C770: 3}),
                      policy, asof=TODAY)
    assert d.action is Action.UNKNOWN
    assert "no entry price" in d.reason


def test_mark_reports_which_legs_are_missing(condor):
    m = mark_structure(condor, chain(**{P755: 0.5, P760: 1.0}))
    assert not m.complete
    assert set(m.missing) == {C770, C775}


# --- the closing order ----------------------------------------------------------------

def test_closes_a_condor_as_one_four_leg_order(condor):
    """Legging out of a defined-risk structure re-introduces the risk it bounded."""
    order = closing_order(condor)
    assert len(order.legs) == 4
    assert order.is_multileg
    assert all(leg.position_intent.value.endswith("_to_close") for leg in order.legs)


def test_closing_order_inverts_every_leg(condor):
    sides = {leg.symbol: leg.side.value for leg in closing_order(condor).legs}
    assert sides[P755] == "sell"   # was bought
    assert sides[P760] == "buy"    # was sold
    assert sides[C770] == "buy"    # was sold
    assert sides[C775] == "sell"   # was bought


def test_closing_order_is_built_from_the_ledger_not_the_broker(condor, ledger):
    """The broker nets legs across structures; only the ledger knows the grouping."""
    assert {leg.symbol for leg in closing_order(condor).legs} == set(condor.legs)


# --- policy ---------------------------------------------------------------------------

def test_policy_reads_the_environment():
    p = ExitPolicy.from_env({"TAKE_PROFIT_PCT": "35", "STOP_LOSS_PCT": "150",
                             "FORCE_CLOSE_DTE": "7"})
    assert (p.take_profit_pct, p.stop_loss_pct, p.force_close_dte) == (
        Decimal(35), Decimal(150), 7)


def test_warns_when_the_target_is_smaller_than_the_round_trip_cost(policy):
    """Measured live: a full open->roll->close cycle cost $73.40."""
    assert policy.sanity_check(Decimal(59)) is not None
    assert "noise, not edge" in policy.sanity_check(Decimal(59))
    assert policy.sanity_check(Decimal(800)) is None


def test_friction_is_priced_per_leg_not_per_structure():
    # The original constant was $73.40 — the *total* cost of a verification run that
    # opened, rolled and closed three separate structures across 16 leg-fills.
    # Comparing that lump against one structure's per-contract max gain overstated
    # friction roughly 4x on a condor, and the agent declined trades on the strength
    # of it.
    from halstreet.agent.manager import FRICTION_PER_LEG_USD, round_trip_cost
    assert round_trip_cost(2) == FRICTION_PER_LEG_USD * 2      # ~$15 a spread
    assert round_trip_cost(4) == FRICTION_PER_LEG_USD * 4      # ~$30 a condor
    assert round_trip_cost(4, qty=10) == round_trip_cost(4) * 10


def test_the_friction_warning_is_size_invariant():
    # Both the target and the cost scale with quantity, so trading more of a
    # structure whose edge does not cover its friction must not silence the warning.
    policy = ExitPolicy(take_profit_pct=Decimal(50))
    thin = Decimal(14)            # the live QQQ spread: $14 max gain, 2 legs
    assert policy.sanity_check(thin, legs=2, qty=1) is not None
    assert policy.sanity_check(thin, legs=2, qty=50) is not None
    # And a structure that does clear its friction stays quiet at any size.
    fat = Decimal(180)
    assert policy.sanity_check(fat, legs=2, qty=1) is None
    assert policy.sanity_check(fat, legs=4, qty=25) is None


def test_more_legs_cost_more_to_get_out_of():
    policy = ExitPolicy(take_profit_pct=Decimal(50))
    gain = Decimal(50)            # $25 target at 50%
    assert policy.sanity_check(gain, legs=2) is None       # $15 to trade — worth it
    assert policy.sanity_check(gain, legs=4) is not None   # $30 to trade — not


def test_review_judges_every_open_structure(ledger, policy, condor, debit_spread):
    assert len(review(ledger, chain(), policy, asof=TODAY)) == 2


# --- the sign convention, pinned ------------------------------------------------------

def test_pnl_is_zero_at_the_moment_of_entry(condor, policy):
    """mark and entry_price share a convention, so at entry they cancel exactly.

    Regression: negating the mark here reported a profitable debit spread as a 254%
    loss and would have stopped out every winning position.
    """
    at_entry = chain(**{P755: 10.78, P760: 12.28, C770: 14.05, C775: 11.51})
    d = evaluate_exit(condor, at_entry, policy, asof=TODAY)
    assert d.mark == Decimal("-4.04")
    assert d.unrealized_usd == Decimal("0.00")
    assert d.action is Action.HOLD


def test_debit_spread_pnl_matches_the_live_fills(debit_spread, policy):
    """Bought at 2.99; the real closing fill was 2.84, a $15 loss."""
    d = evaluate_exit(debit_spread, chain(**{C765: 16.84, C770: 14.00}), policy, asof=TODAY)
    assert d.mark == Decimal("2.84")
    assert d.unrealized_usd == Decimal("-15.00")


def test_credit_pnl_matches_the_live_condor_round_trip(condor, policy):
    """Opened for 4.04 credit; the real closing fill was 4.27, a $23 loss."""
    d = evaluate_exit(condor, chain(**{P755: 0.50, P760: 1.00, C770: 4.87, C775: 1.10}),
                      policy, asof=TODAY)
    assert d.mark == Decimal("-4.27")
    assert d.unrealized_usd == Decimal("-23.00")


# --- ordering: exits run before entries -------------------------------------------

def test_exit_review_consults_no_gates():
    """Exits are never gated. If gates/ ever leaks into this module, say so loudly.

    HAL's risk engine blocks entries only, for the reason that matters here: when the
    kill switch is latched or the account is in drawdown, you need to be *more* able to
    close, not less.
    """
    import inspect

    from halstreet.agent import manager
    source = inspect.getsource(manager)
    assert "from halstreet.gates" not in source
    assert "evaluate(" not in source


# --- exit levels, which the chart draws -------------------------------------------

def _at_mark(structure, mark: Decimal) -> dict:
    """A chain pricing `structure` at exactly `mark`, with both legs quoted positive.

    mark = mid(long) - mid(short), so the pair is anchored at whichever base keeps
    both sides above zero. Pinning one leg at a constant instead puts the other
    negative for large marks, and `mark_structure` refuses a leg with a non-positive
    ask — which is the *missing data* path, not the threshold path this is testing.
    """
    symbols = list(structure.legs)
    short = next(s for s in symbols if structure.legs[s] < 0)
    long_ = next(s for s in symbols if structure.legs[s] > 0)
    base = max(Decimal("0.20"), Decimal("0.20") - mark)
    short_mid, long_mid = base, base + mark

    def quote(m: Decimal) -> dict:
        return {"latestQuote": {"bp": str(m - Decimal("0.01")), "ap": str(m + Decimal("0.01"))}}

    return {short: quote(short_mid), long_: quote(long_mid)}


@pytest.mark.parametrize("entry", [Decimal("-1.60"), Decimal("-0.75"), Decimal("2.00")])
def test_levels_agree_with_the_policy_that_acts_on_them(entry):
    """The chart's lines and the exit's thresholds must be one rule, not two.

    `exit_levels` converts the policy into mark space so it can be drawn; `evaluate_exit`
    applies it in dollars. Two derivations of one rule is how a chart starts lying while
    looking confident, so this walks a structure across each boundary and asserts the
    action flips exactly where the levels say it will.
    """
    policy = ExitPolicy()
    structure = OpenStructure(
        structure_id="lv", name="spread", underlying="SPY", qty=1,
        legs={C770: -1, C775: 1}, opened_at="2026-08-26T00:00:00+00:00",
        entry_price=entry,
    )
    levels = exit_levels(entry, policy)
    nudge = Decimal("0.02")

    # Direction is the same for credit and debit: take-profit fires as the mark rises
    # through the target, the stop as it falls through the stop. Only the levels move.
    assert evaluate_exit(structure, _at_mark(structure, levels.target - nudge), policy,
                         asof=TODAY).action is not Action.TAKE_PROFIT
    assert evaluate_exit(structure, _at_mark(structure, levels.target + nudge), policy,
                         asof=TODAY).action is Action.TAKE_PROFIT

    # A 200% stop on a debit structure is unreachable — you cannot lose more than the
    # premium you paid — and `Levels.stop_reachable` is how that is now said rather
    # than left as a gap in this test. Where the stop *can* print, it must print
    # exactly where the chart draws it.
    assert levels.stop_reachable == (levels.credit or levels.stop > 0)
    if levels.stop_reachable:
        assert evaluate_exit(structure, _at_mark(structure, levels.stop + nudge), policy,
                             asof=TODAY).action is not Action.STOP_LOSS
        assert evaluate_exit(structure, _at_mark(structure, levels.stop - nudge), policy,
                             asof=TODAY).action is Action.STOP_LOSS
    else:
        # Clamped to zero: a worthless long structure. The policy does not act here,
        # and the flag is what stops the chart implying it would.
        assert levels.stop == 0
        assert evaluate_exit(structure, _at_mark(structure, Decimal("0.01")), policy,
                             asof=TODAY).action is not Action.STOP_LOSS


def test_levels_do_not_move_with_size():
    """A target is a price. Trading ten does not change where you get out."""
    one = exit_levels(Decimal("-1.60"), ExitPolicy())
    assert one.target == Decimal("-1.60") * Decimal("0.5")
    assert one.stop == Decimal("-1.60") * Decimal(3)



# --- a level the market cannot print --------------------------------------------------

def test_a_debit_stop_is_never_a_negative_price():
    """The chart's half of the unreachable-stop problem.

    `evaluate_exit` simply never fires there, which is correct and was documented. The
    chart is the half that would have been visibly wrong: the arithmetic puts a 200%
    stop on a $2.99 debit at **-$2.99**, and a line at a negative price sits off the
    bottom of an axis whose series never goes below zero. A stop line the market
    cannot reach is worse than none, because it reads as protection.
    """
    levels = exit_levels(Decimal("2.99"), ExitPolicy(
        take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200), force_close_dte=5))
    assert levels.stop >= 0, "a long structure's mark cannot go below zero"
    assert levels.stop == 0, "clamped to worthless, which is the real maximum loss"
    assert levels.stop_reachable is False


def test_a_debit_stop_inside_the_premium_is_reachable_and_exact():
    # Below 100% the stop is an ordinary level and must stay exact — the clamp must
    # not round off a stop that can actually print.
    levels = exit_levels(Decimal("3.00"), ExitPolicy(
        take_profit_pct=Decimal(50), stop_loss_pct=Decimal(60), force_close_dte=5))
    assert levels.stop == Decimal("1.20") and levels.stop_reachable is True


def test_a_stop_at_exactly_the_whole_premium_is_still_reachable():
    # 100% is the boundary: the structure expiring worthless is a real outcome the
    # policy can act on, so zero is reachable rather than clamped.
    levels = exit_levels(Decimal("2.50"), ExitPolicy(
        take_profit_pct=Decimal(50), stop_loss_pct=Decimal(100), force_close_dte=5))
    assert levels.stop == 0 and levels.stop_reachable is True


def test_a_credit_stop_has_no_ceiling_and_is_always_reachable():
    # The short leg can be bought back at any price, so there is no equivalent bound
    # on this side. The clamp must not touch it.
    levels = exit_levels(Decimal("-1.00"), ExitPolicy(
        take_profit_pct=Decimal(50), stop_loss_pct=Decimal(500), force_close_dte=5))
    assert levels.stop == Decimal(-6) and levels.stop_reachable is True


def test_reachability_reaches_the_panel():
    # The flag is only worth having if the thing that draws the line can see it.
    levels = exit_levels(Decimal("2.99"), ExitPolicy(
        take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200), force_close_dte=5))
    assert levels.to_prompt()["stop_reachable"] is False
