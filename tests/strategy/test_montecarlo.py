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
    """A number without its assumption is the assumption made invisible. This one is
    priced on realized volatility with no drift, at expiry, ignoring early management."""
    note = run().note.lower()
    assert "expiry" in note and "vol" in note


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
    assert c.to_prompt()["scenario"]["ev_usd"] == str(c.scenario.ev_usd)


def test_the_round_trip_is_priced_not_just_the_entry():
    """Entry slippage is one crossing. Getting out is the other, and it is the half the
    desk keeps declining trades over."""
    from halstreet.strategy.candidates import Candidate, scenario_for

    def built(slip: Decimal):
        c = Candidate(name="SPY 2026-10-16 737/733 put credit spread",
                      kind="put_credit_spread",
                      legs=[{"symbol": "SPY261016P00737000", "side": "sell", "ratio_qty": 1},
                            {"symbol": "SPY261016P00733000", "side": "buy", "ratio_qty": 1}],
                      net=Decimal("-0.41"), max_loss_usd=Decimal(359),
                      max_gain_usd=Decimal(41), dte=49, slippage_usd=slip)
        return scenario_for(c, spot=SPOT, vol=0.18)

    assert built(Decimal(6)).ev_usd == built(Decimal(0)).ev_usd - Decimal(12)


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
