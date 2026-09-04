"""The distribution behind a structure, not just its odds.

`pop.py` answers "how often does this finish profitable" analytically and exactly, and
that is the right tool for that question. It is not the question the judge keeps
asking. Every decline this week has been about the *shape*: "$16 max gain against ~$15
round-trip friction", "a 1:11 reward/risk that only works if SPY does nothing for 49
days". Those are claims about expectation and about the size of the tail, and the agent
was reaching them in prose because nothing computed them.

Simulation rather than more closed form because the awkward part is not the
probability, it is the average — and the mean of a piecewise-linear payoff over a
lognormal, minus a fixed cost, is far easier to sample than to derive per structure.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.marketdata.occ import PayoffLeg, Right
from halstreet.strategy import montecarlo as mc

SPOT = Decimal(750)


def put_credit_spread(short: int = 737, long: int = 733) -> list[PayoffLeg]:
    """Short the near put, long the far one. Four wide, the shape the agent builds."""
    return [
        PayoffLeg(right=Right.PUT, strike=Decimal(short), ratio=1, long=False),
        PayoffLeg(right=Right.PUT, strike=Decimal(long), ratio=1, long=True),
    ]


def run(**over):
    args = {"legs": put_credit_spread(), "net": Decimal("-0.41"), "spot": SPOT,
            "dte": 49, "vol": 0.18, "friction_usd": Decimal(0), "seed": 7}
    return mc.simulate(**{**args, **over})


# --- the arithmetic it must not get wrong -------------------------------------------

def test_a_defined_risk_structure_never_loses_more_than_its_width():
    """The claim the whole book rests on. If simulation finds a worse path than the
    gate's own max-loss arithmetic, one of the two is wrong and it matters which."""
    assert run().worst_usd >= Decimal(-359)


def test_it_never_makes_more_than_the_credit():
    assert run().best_usd <= Decimal(41)


def test_a_motionless_tape_pays_the_credit():
    """Zero volatility has an answer you can do in your head: the price cannot move,
    both puts expire worthless, and the credit is the whole result."""
    out = run(vol=0.0)
    assert out.ev_usd == Decimal(41)
    assert out.p_profit == 1.0


def test_expiry_today_is_settled_by_where_the_price_already_is():
    assert run(dte=0).ev_usd == Decimal(41), "750 is well above the 737 short strike"


# --- the numbers it exists to produce ------------------------------------------------

def test_friction_comes_straight_off_the_expectation():
    """The judge's actual complaint, as a number. Nothing about the trade changes —
    the same paths, the same payoffs, a fixed cost at the door."""
    assert run(friction_usd=Decimal(15)).ev_usd == run().ev_usd - Decimal(15)


def test_friction_can_turn_a_winning_structure_into_a_losing_one():
    """The whole point of computing it. A frequent winner at $20 a time is not an edge
    when it costs $15 to get in and out."""
    assert run(net=Decimal("-0.20"), friction_usd=Decimal(15)).ev_usd < 0


def test_the_odds_land_near_the_closed_form_answer():
    """Not a replacement for `pop`, and it has to agree with it. A simulation that
    disagrees with exact arithmetic on the one number they both compute is one nobody
    should read the rest of."""
    from halstreet.strategy.pop import credit_put_spread

    exact = credit_put_spread(spot=float(SPOT), short_strike=737.0, credit=0.41,
                              dte=49, vol=0.18)
    assert abs(run().p_profit - exact) < 0.02


def test_the_tail_is_reported_rather_than_averaged_away():
    """"How often does this lose everything" is a different question from "how often
    does it lose", and it is the one a defined-risk book has to answer."""
    out = run()
    assert 0.0 < out.p_max_loss < out.p_loss


def test_a_wider_tape_widens_the_spread_of_outcomes():
    calm, wild = run(vol=0.12), run(vol=0.45)
    assert wild.p_max_loss > calm.p_max_loss
    assert wild.p_profit < calm.p_profit


# --- being readable twice --------------------------------------------------------------

def test_the_same_structure_always_simulates_the_same():
    """It goes in the journal, and a record that cannot be reproduced is not a record.

    Seeded from the structure rather than the clock, so re-running a cycle against the
    same chain gives the same figures — and a reader comparing two journal entries is
    comparing the structures rather than the weather in the random number generator.
    """
    assert run().ev_usd == run().ev_usd
    assert run().p_profit == run().p_profit


def test_a_different_seed_moves_the_answer_only_slightly():
    """If it did not, the path count would be too low to report to two decimals."""
    assert abs(run(seed=1).p_profit - run(seed=99).p_profit) < 0.02


# --- refusing to guess -------------------------------------------------------------

def test_an_unknown_volatility_produces_nothing_rather_than_a_default():
    """The one input that cannot be defaulted. A structure simulated at a made-up 20%
    is a confident number about a market nobody measured — Constitution VII, in the
    place it would do the most damage."""
    assert mc.simulate(legs=put_credit_spread(), net=Decimal("-0.41"), spot=SPOT,
                       dte=49, vol=None, friction_usd=Decimal(0), seed=7) is None


def test_a_structure_with_no_legs_is_not_simulated():
    assert mc.simulate(legs=[], net=Decimal("-0.41"), spot=SPOT, dte=49, vol=0.18,
                       friction_usd=Decimal(0), seed=7) is None


def test_a_nonsensical_spot_is_not_simulated():
    assert mc.simulate(legs=put_credit_spread(), net=Decimal("-0.41"), spot=Decimal(0),
                       dte=49, vol=0.18, friction_usd=Decimal(0), seed=7) is None


def test_money_leaves_as_decimal_never_float():
    """Constitution IV. The sampling is float because it is a statistical estimate;
    what it hands back is money, and money in this codebase is Decimal."""
    out = run()
    for value in (out.ev_usd, out.worst_usd, out.best_usd, out.p50_usd):
        assert isinstance(value, Decimal), value


def test_it_says_what_it_assumed():
    """A number without its assumption is the assumption made invisible: settled at
    expiry, on one volatility, ignoring how the book is actually managed."""
    note = run().note.lower()
    assert "expiry" in note and "drift" in note


# --- reaching the menu ---------------------------------------------------------------

def test_the_menu_carries_each_structures_scenario_to_the_model():
    """A number computed and not shown is a number nobody acts on. The model already
    reasons about expectation in prose; this puts the arithmetic in front of it."""
    from halstreet.strategy.candidates import Candidate, scenario_for

    c = Candidate(name="SPY 2026-10-16 737/733 put credit spread", kind="put_credit_spread",
                  legs=[{"symbol": "SPY261016P00737000", "side": "sell", "ratio_qty": 1},
                        {"symbol": "SPY261016P00733000", "side": "buy", "ratio_qty": 1}],
                  net=Decimal("-0.41"), max_loss_usd=Decimal(359),
                  max_gain_usd=Decimal(41), dte=49, slippage_usd=Decimal(6))
    c.scenario = scenario_for(c, spot=SPOT, vol=0.18)
    assert c.scenario is not None
    shape = c.to_prompt()["scenario"]
    assert shape["at_realized"]["ev_usd"] == str(c.scenario.at_realized.ev_usd)


def test_a_leg_that_cannot_be_parsed_stops_the_simulation_rather_than_shrinking_it():
    """A structure sampled with a wing missing is not a conservative estimate of that
    structure. It is a confident estimate of a different and far riskier one."""
    from halstreet.strategy.candidates import Candidate, scenario_for

    c = Candidate(name="broken", kind="put_credit_spread",
                  legs=[{"symbol": "SPY261016P00737000", "side": "sell", "ratio_qty": 1},
                        {"symbol": "not-an-occ-symbol", "side": "buy", "ratio_qty": 1}],
                  net=Decimal("-0.41"), max_loss_usd=Decimal(359),
                  max_gain_usd=Decimal(41), dte=49)
    assert scenario_for(c, spot=SPOT, vol=0.18) is None


def test_an_unmeasured_volatility_leaves_the_menu_unsimulated():
    """The default that must not exist. Every other candidate on the menu carries a
    measured scenario, and one carrying a guessed one would look identical."""
    from halstreet.strategy.candidates import Candidate, scenario_for

    c = Candidate(name="SPY 2026-10-16 737/733 put credit spread", kind="put_credit_spread",
                  legs=[{"symbol": "SPY261016P00737000", "side": "sell", "ratio_qty": 1},
                        {"symbol": "SPY261016P00733000", "side": "buy", "ratio_qty": 1}],
                  net=Decimal("-0.41"), max_loss_usd=Decimal(359),
                  max_gain_usd=Decimal(41), dte=49)
    assert scenario_for(c, spot=SPOT, vol=None) is None


def test_the_cycle_hands_the_ranking_the_volatility_it_measured():
    """`regime` computes realized vol every cycle and it was reaching the ranking as a
    label only — so the menu could say "high volatility" and not what that was."""
    import inspect

    from halstreet.agent.cerebellum import loop
    source = inspect.getsource(loop.Agent.run_cycle)
    assert "realized_vol" in source


def test_there_is_one_contract_multiplier_in_the_codebase():
    """A hundred shares to a contract is a fact about the instrument, and it was
    written down in three places.

    Not a bug today — it is a hundred everywhere — but it is the shape of one this
    project has already paid for: `verify_multileg.py` carried its own `parse_occ`
    with a comment saying the real one should be ported, the port landed, the comment
    stayed, and the copy went on parsing symbols its own way for months.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "halstreet"
    owners = [p for p in src.rglob("*.py")
              if re.search(r"^[A-Z_]*MULTIPLIER\s*=", p.read_text(), re.MULTILINE)]
    assert [p.name for p in owners] == ["occ.py"], \
        f"the multiplier is defined in more than one place: {[p.name for p in owners]}"


# --- the volatility the market used, beside the one the tape ran at -------------------
#
# The caveat became load-bearing the moment a judge reasoned from it. On a live NVDA
# menu every structure printed negative EV, and the judge concluded: "the sim telling
# us realized vol (42.9%) is running above the implied vol that quoted these credits —
# short-premium is the wrong side of that gap regardless of which strikes we pick."
#
# That reasoning is sound and the number it rests on was one-sided. A structure is
# *priced* at implied vol and *simulated* at realized, so a single EV silently asserts
# that the tape's trailing behaviour is the better forecast. Sometimes it is. The
# disagreement between the two is not noise to be resolved by picking one — it is the
# whole trade thesis, and it belongs on the page.

def outlook(**over):
    args = {"legs": put_credit_spread(), "net": Decimal("-0.41"), "spot": SPOT,
            "dte": 49, "vol_realized": 0.18, "vol_implied": 0.24,
            "friction_usd": Decimal(0), "seed": 7}
    return mc.outlook(**{**args, **over})


def test_a_structure_is_priced_at_both_volatilities():
    out = outlook()
    assert out.at_realized is not None and out.at_implied is not None
    assert out.at_realized.vol == 0.18
    assert out.at_implied.vol == 0.24


def test_selling_premium_looks_better_when_the_market_charges_more_than_the_tape_moves():
    """The usual case for index options, and the reason a one-sided EV flatters or
    damns short premium depending only on which volatility it happened to use."""
    out = outlook(vol_realized=0.18, vol_implied=0.30)
    assert out.at_realized.ev_usd > out.at_implied.ev_usd


def test_the_two_agreeing_is_reported_as_agreement():
    """Both negative, or both positive, is a conclusion. The judge can stop there."""
    assert outlook(vol_realized=0.60, vol_implied=0.60).agree is True


def test_the_two_disagreeing_is_reported_rather_than_averaged():
    """A trade that is good at implied and bad at realized is a bet on which volatility
    is the better forecast. Averaging them would hide the only question that matters."""
    # Measured: this structure flips sign between 5% and 8% volatility. Below the
    # flip the market is charging enough for the tail; above it, it is not.
    out = outlook(vol_realized=0.30, vol_implied=0.05)
    assert out.at_implied.ev_usd > 0 > out.at_realized.ev_usd
    assert out.agree is False


def test_a_missing_implied_leaves_the_realized_read_standing():
    """A chain without IV is common enough. Losing the realized read too would trade a
    partial answer for none."""
    out = outlook(vol_implied=None)
    assert out.at_implied is None and out.at_realized is not None
    assert out.agree is None, "one opinion cannot agree with itself"


def test_a_structure_nobody_could_price_either_way_is_no_outlook():
    assert outlook(vol_realized=None, vol_implied=None).at_realized is None


def test_the_prompt_names_which_volatility_each_figure_used():
    """A figure without its assumption hides the assumption, and here the assumption
    is the disagreement the whole read is about."""
    shape = outlook().to_prompt()
    assert shape["at_implied"]["vol"] == 0.24
    assert shape["at_realized"]["vol"] == 0.18
    assert "agree" in shape


def test_the_menu_prices_each_structure_at_the_iv_it_was_quoted_at():
    """The short strike's own IV, from the quote that set the credit — not a number
    from somewhere else in the surface."""
    import inspect

    from halstreet.strategy import candidates
    source = inspect.getsource(candidates.scenario_for)
    assert "iv" in source


def test_the_proposal_prompt_says_how_to_read_two_disagreeing_volatilities():
    """Computed and never named is how a number gets misread with confidence.

    A live judge, given a one-sided EV, concluded "short premium is the wrong side of
    that gap regardless of which strikes we pick" — a real inference from a figure that
    had only seen the tape's volatility and not the market's. Both are on the menu now,
    and a model has to be told what their disagreement means or it will pick one.
    """
    from halstreet.agent.cortex.llm import SYSTEM_PROMPT

    text = SYSTEM_PROMPT.lower()
    assert "at_implied" in text and "at_realized" in text
    assert "forecast" in text


def test_the_entry_crossing_is_not_charged_twice():
    """`net` is already `short.bid - long.ask` — the worst of both touches.

    The credit a candidate carries is what you actually receive after crossing the
    spread to get in, so the entry cost is *inside* `net`. Charging `slippage_usd`
    again on entry deducted it twice and made every structure on every menu look worse
    than it is, in the one direction that stops an agent trading.

    What is still owed is the exit. The simulation settles at expiry where there is no
    exit trade at all, but the book does not hold to expiry — the manager takes profit
    at 50% and force-closes at 5 DTE — so one crossing out is the honest charge.
    """
    from halstreet.strategy.candidates import Candidate, scenario_for

    def built(slip: Decimal):
        c = Candidate(name="SPY 2026-10-16 737/733 put credit spread",
                      kind="put_credit_spread",
                      legs=[{"symbol": "SPY261016P00737000", "side": "sell", "ratio_qty": 1},
                            {"symbol": "SPY261016P00733000", "side": "buy", "ratio_qty": 1}],
                      net=Decimal("-0.41"), max_loss_usd=Decimal(359),
                      max_gain_usd=Decimal(41), dte=49, slippage_usd=slip)
        return scenario_for(c, spot=SPOT, vol=0.18).at_realized

    # One crossing, not two: a $6 half-spread sum costs $6 to get out of, not $12.
    assert built(Decimal(6)).ev_usd == built(Decimal(0)).ev_usd - Decimal(6)


def test_the_scenario_says_what_friction_it_already_charged():
    """Otherwise the reader subtracts it again, and a live judge just did.

    Shown an EV of +$13.80 and an `entry_slippage_usd` of $3, it reasoned: "only the $3
    entry slippage is netted out ... the remaining ~$12 of exit cost takes the
    realized-vol EV from $13.80 to roughly $2". The exit cost was already in the
    figure. A number that has had a cost deducted must say so, or the next reader
    deducts it twice — which is the same mistake this module had made in code an hour
    earlier, now made in prose.
    """
    shape = run(friction_usd=Decimal(6)).to_prompt()
    assert shape["friction_usd"] == "6"
    assert "friction" in shape["note"].lower()
