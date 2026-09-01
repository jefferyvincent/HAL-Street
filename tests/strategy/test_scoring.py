"""Ranking: bias, profiles, and the rule that a profile can never loosen a gate."""

from __future__ import annotations

from decimal import Decimal

from halstreet.gates.base import Limits
from halstreet.strategy import bias, pop, scoring
from halstreet.strategy import profiles as P
from halstreet.strategy.indicators import Macd

# --- bias ---------------------------------------------------------------------

def _snap(**kw) -> bias.Snapshot:
    base = {"symbol": "SPY", "spot": 100.0, "sma50": 95.0, "ema20": 98.0, "ema50": 94.0,
            "rsi14": 58.0, "macd": Macd(value=1.0, signal=0.5, histogram=0.5)}
    base.update(kw)
    return bias.Snapshot(**base)


def test_an_aligned_tape_reads_bullish_with_its_reasons():
    result = bias.derive(_snap())
    assert result.direction == bias.BULLISH
    assert result.coverage == 5
    assert "price above 50-EMA" in result.reasons


def test_the_mirror_image_reads_bearish():
    result = bias.derive(_snap(sma50=105.0, ema20=101.0, ema50=106.0, rsi14=42.0,
                               macd=Macd(value=-1.0, signal=-0.5, histogram=-0.5)))
    assert result.direction == bias.BEARISH


def test_a_one_vote_margin_is_not_a_direction():
    # Two bullish, one bearish, nothing else: a margin of one is noise, and the
    # structures this agent trades are at their best when it says so.
    result = bias.derive(_snap(rsi14=None, macd=None, sma50=105.0))
    assert result.bullish - result.bearish == 1
    assert result.direction == bias.NEUTRAL


def test_missing_indicators_abstain_rather_than_voting_neutral():
    result = bias.derive(bias.Snapshot(symbol="SPY", spot=100.0))
    assert result.direction == bias.NEUTRAL
    assert (result.bullish, result.bearish, result.coverage) == (0, 0, 0)
    assert result.reasons == []


def test_an_overbought_rsi_votes_against_the_trend():
    hot = bias.derive(_snap(rsi14=78.0))
    warm = bias.derive(_snap(rsi14=58.0))
    assert hot.bearish > warm.bearish


def test_a_macd_with_trend_and_momentum_disagreeing_casts_no_vote():
    voting = bias.derive(_snap())
    mixed = bias.derive(_snap(macd=Macd(value=1.0, signal=0.5, histogram=-0.2)))
    # A MACD line above its signal with a shrinking histogram is a trend running out
    # of fuel. It casts no vote rather than half of one, so the tally drops by two.
    assert voting.bullish - mixed.bullish == 2
    assert mixed.bearish == voting.bearish
    assert "MACD mixed (no signal)" in mixed.reasons


# --- probability of profit -----------------------------------------------------

def test_a_credit_widens_the_odds_past_the_short_strike():
    bare = pop.credit_put_spread(765, 745, 0.0, 45, 0.15)
    paid = pop.credit_put_spread(765, 745, 2.0, 45, 0.15)
    assert paid > bare


def test_a_condor_is_less_likely_than_either_side_alone():
    put = pop.credit_put_spread(765, 745, 1.2, 45, 0.15)
    call = pop.credit_call_spread(765, 790, 1.1, 45, 0.15)
    condor = pop.iron_condor(765, 745, 790, 2.3, 45, 0.15, 0.15)
    assert condor < min(put, call)


def test_skew_is_used_when_both_ivs_are_known():
    # Index put skew makes the downside tail fatter. Pricing both tails at the put's
    # IV — the vendor's single-volatility shortcut — understates the odds.
    skewed = pop.iron_condor(765, 745, 790, 2.3, 45, 0.16, 0.12)
    shared = pop.iron_condor(765, 745, 790, 2.3, 45, 0.16)
    assert skewed > shared


def test_crossed_short_strikes_are_not_a_condor():
    assert pop.iron_condor(765, 790, 745, 2.3, 45, 0.15) is None


# --- profiles ------------------------------------------------------------------

def test_the_moderate_profile_does_not_override_the_configured_volume_floor():
    # The vendor's 25 silently beat a deliberate MIN_DAILY_VOLUME and starved QQQ of
    # candidates entirely. Retuned to 5, the two agree and neither hides the other.
    limits = Limits(min_daily_volume=5)
    floor = P.EffectiveFloor.compose(P.MODERATE, limits)
    assert floor.min_daily_volume == 5
    assert not any("daily volume" in n for n in floor.notes)


def test_volume_floors_still_rank_by_profile_caution():
    volumes = [P.PROFILES[n].liquidity.min_daily_volume for n in
               ("ultra_conservative", "conservative", "moderate",
                "moderate_short", "aggressive", "ultra_aggressive")]
    assert volumes == sorted(volumes, reverse=True)
    # Every profile, not a list someone remembered to extend. `moderate_short` was
    # added later and would have sat outside this rule entirely.
    assert len(volumes) == len(P.PROFILES)


def test_the_conservative_profiles_do_not_sell_condors():
    # A condor is two short verticals. A profile unwilling to sell one side has no
    # business selling both.
    assert not P.CONSERVATIVE.builds(P.IRON_CONDOR)
    assert P.CONSERVATIVE.builds(P.PUT_CREDIT)
    assert P.MODERATE.builds(P.IRON_CONDOR)


def test_delta_targets_span_the_profiles_band():
    deltas = P.MODERATE.short_deltas
    assert deltas[0] == P.MODERATE.short_delta_min
    assert deltas[-1] == P.MODERATE.short_delta_max
    assert len(deltas) == 3


def test_a_profile_can_never_loosen_a_gate():
    # The load-bearing rule of the whole file. ultra_aggressive asks for OI 100,
    # volume 5 and 12% spreads; the .env limits say 250 / 10 / 10%.
    limits = Limits(min_open_interest=250, min_daily_volume=5,
                    max_bid_ask_width_pct=Decimal(10), min_dte=7)
    floor = P.EffectiveFloor.compose(P.ULTRA_AGGRESSIVE, limits)
    assert floor.min_open_interest == 250
    assert floor.min_daily_volume == 5
    assert floor.max_spread_pct == Decimal(10)
    assert floor.min_dte == 7
    assert len(floor.clamped) == 3
    assert all("loosened by .env" in n for n in floor.notes)


def test_a_profile_stricter_than_the_gates_is_honoured():
    # Searching less than you are allowed to is a preference, not a risk.
    limits = Limits(min_open_interest=250, min_daily_volume=5,
                    max_bid_ask_width_pct=Decimal(10), min_dte=7)
    floor = P.EffectiveFloor.compose(P.ULTRA_CONSERVATIVE, limits)
    assert floor.min_open_interest == 500
    assert floor.max_spread_pct == Decimal(5)
    assert floor.min_dte == 30
    assert floor.clamped == []
    # But the disagreement is still reported. A ported vendor default silently
    # tightening a limit the operator chose in .env is the surprising direction,
    # and it once starved a whole underlying of candidates without saying why.
    assert any("daily volume 5 -> 15" in n for n in floor.tightened)
    assert all("tightened by profile" in n for n in floor.notes)


def test_the_spread_ceiling_is_the_stricter_of_profile_and_gate():
    # The vendor's mid-dependent dollar rule is deliberately not ported — it would
    # make this layer looser than the gate it anticipates. See
    # `profiles.LiquidityFloor` for the measurement behind that decision.
    limits = Limits(max_bid_ask_width_pct=Decimal(10))
    assert P.MODERATE.liquidity.max_spread_pct == Decimal(8)
    assert P.EffectiveFloor.compose(P.MODERATE, limits).max_spread_pct == Decimal(8)

    assert P.ULTRA_AGGRESSIVE.liquidity.max_spread_pct == Decimal(12)
    assert P.EffectiveFloor.compose(P.ULTRA_AGGRESSIVE, limits).max_spread_pct == Decimal(10)


def test_an_unknown_profile_raises_rather_than_falling_back():
    # Silently trading a different profile than the one written in the config is
    # worse than refusing to start.
    assert P.from_env({}).name == "moderate"
    assert P.from_env({"RISK_PROFILE": "aggressive"}).name == "aggressive"
    try:
        P.from_env({"RISK_PROFILE": "yolo"})
    except P.UnknownProfile as exc:
        assert "yolo" in str(exc)
    else:
        raise AssertionError("an unknown profile must raise")


# --- scoring -------------------------------------------------------------------

def _ctx(**kw) -> scoring.Context:
    base = {"bias": bias.NEUTRAL, "regime": "medium",
                "events": scoring.EventWindow(known=True), "weights": P.MODERATE.weights}
    base.update(kw)
    return scoring.Context(**base)


def _score(kind: str, ctx: scoring.Context, **kw) -> scoring.ScoreBreakdown:
    args = {"max_gain_usd": 120.0, "max_loss_usd": 380.0, "slippage_usd": 9.0, "pop": 0.76}
    args.update(kw)
    return scoring.score(kind=kind, ctx=ctx, **args)


def test_a_structure_that_wants_the_tapes_direction_beats_one_that_opposes_it():
    ctx = _ctx(bias=bias.BULLISH)
    assert _score(P.PUT_CREDIT, ctx).total > _score(P.CALL_CREDIT, ctx).total


def test_direction_is_exact_rather_than_a_coin_flip():
    # The vendor listed 'vertical_call' as both bullish and bearish because a
    # vertical there might be a credit or a debit. Here the kind says which.
    ctx = _ctx(bias=bias.BULLISH)
    assert scoring.bias_fit(P.PUT_CREDIT, ctx.bias) == 1.0
    assert scoring.bias_fit(P.CALL_CREDIT, ctx.bias) == 0.0


def test_a_condor_is_what_a_neutral_read_is_for():
    assert scoring.bias_fit(P.IRON_CONDOR, bias.NEUTRAL) == 1.0
    assert scoring.bias_fit(P.PUT_CREDIT, bias.NEUTRAL) == 0.5


def test_credit_structures_prefer_a_high_volatility_tape():
    high = _score(P.IRON_CONDOR, _ctx(regime="high")).total
    low = _score(P.IRON_CONDOR, _ctx(regime="low")).total
    assert high > low


def test_an_unknown_regime_scores_the_middle_not_zero():
    # Every candidate in one scan shares a regime, so zero would change no ordering
    # while making the whole menu look worthless.
    assert scoring.iv_regime_fit(P.IRON_CONDOR, "unknown") == 0.5


def test_paying_more_of_the_risk_to_the_spread_scores_worse():
    tight = _score(P.PUT_CREDIT, _ctx(), slippage_usd=4.0).liquidity
    wide = _score(P.PUT_CREDIT, _ctx(), slippage_usd=40.0).liquidity
    assert tight > wide >= 0.0


def test_unknown_slippage_scores_zero_because_spread_is_always_available():
    assert scoring.liquidity_fit(None, 380.0) == 0.0


def test_unknown_pop_is_a_disadvantage_not_a_pass():
    # Unlike the regime, POP varies across the menu — a candidate whose odds cannot
    # be computed should lose to one whose can.
    assert scoring.pop_fit(None) == 0.0
    assert _score(P.PUT_CREDIT, _ctx(), pop=None).total < _score(P.PUT_CREDIT, _ctx()).total


def test_reward_risk_is_capped_so_lottery_wings_cannot_dominate():
    assert scoring.reward_risk_fit(5000.0, 100.0) == 1.0
    assert scoring.reward_risk_fit(500.0, 100.0) == 1.0
    assert scoring.reward_risk_fit(100.0, 100.0) < 1.0
    assert scoring.reward_risk_fit(100.0, 0.0) == 0.0


def test_an_unchecked_earnings_calendar_is_penalised_like_a_known_event():
    # Fail closed: "I could not check" is not "there are none".
    # An unread calendar is not a clear one. These used to be the same answer for any
    # index ETF, which is how the term became a constant across the whole universe.
    unread = scoring.EventWindow(known=False)
    clear = scoring.EventWindow(known=True)
    assert unread.risk_for(45) == scoring.EVENT_UNKNOWN
    assert clear.risk_for(45) == scoring.EVENT_NONE
    assert scoring.event_penalty(scoring.EVENT_UNKNOWN) == 1.0
    assert scoring.event_penalty(scoring.EVENT_PRESENT) == 1.0
    assert scoring.event_penalty(scoring.EVENT_NONE) == 0.0


def test_the_profile_decides_what_matters():
    # Same candidate, same tape, different profile: ultra_conservative weights the
    # volatility regime at 0.35 and direction at 0.05; aggressive inverts that.
    tape = {"bias": bias.BULLISH, "regime": "low", "events": scoring.EventWindow(known=True)}
    cautious = _score(P.PUT_CREDIT, scoring.Context(**tape, weights=P.ULTRA_CONSERVATIVE.weights))
    bold = _score(P.PUT_CREDIT, scoring.Context(**tape, weights=P.AGGRESSIVE.weights))
    assert bold.total > cautious.total
    # The terms themselves are identical — only the weighting moved.
    assert (bold.bias_fit, bold.iv_regime_fit) == (cautious.bias_fit, cautious.iv_regime_fit)


def test_the_breakdown_survives_into_the_journal():
    breakdown = _score(P.PUT_CREDIT, _ctx())
    prompt = breakdown.to_prompt()
    assert set(prompt) == {"bias_fit", "iv_regime_fit", "liquidity", "reward_risk",
                           "pop", "event_risk", "total"}


def test_scores_are_recorded_as_stable_decimals():
    # A score is not money and the arithmetic is float on purpose, but the recorded
    # value has to be byte-stable for the journal to be reproducible.
    assert scoring.as_decimal(71.98765) == Decimal("71.9877")
    assert str(scoring.as_decimal(60.0)) == "60.0000"


# --- what pop can and cannot check for itself -------------------------------------

def test_a_negative_credit_is_refused_rather_than_priced():
    """A negative credit narrows the profit zone instead of widening it.

    Which means the number that came back was not conservative — it was a different
    structure's answer wearing this one's name, and it would have gone into the
    ranking as a probability of profit.
    """
    assert pop.credit_put_spread(765, 745, -2.0, 45, 0.15) is None
    assert pop.credit_call_spread(765, 790, -2.0, 45, 0.15) is None
    assert pop.iron_condor(765, 745, 790, -2.0, 45, 0.15) is None
    assert pop.debit_call_spread(765, 770, -1.0, 45, 0.15) is None
    assert pop.debit_put_spread(765, 760, -1.0, 45, 0.15) is None


def test_a_zero_credit_is_the_limit_case_and_still_answers():
    # Breakevens sitting on the short strikes. Not a trade anyone takes, but it is how
    # you show what the credit is worth, and refusing it would break that comparison.
    assert pop.credit_put_spread(765, 745, 0.0, 45, 0.15) is not None
    assert pop.iron_condor(765, 745, 790, 0.0, 45, 0.15) is not None


def test_pop_cannot_see_the_wing_width_and_does_not_pretend_to():
    """The invariant these functions depend on and cannot check.

    None of them receives the wing width, so none can tell a real premium from a
    crossed quote: a 99-point credit on a 2-point wing widens the profit zone by 99
    and returns a serene 95%, which would put the structure top of the ranking. That
    is not a bug here — it is arithmetic on impossible inputs — but it is worth
    pinning that the number really is that confident, because it is the reason
    `candidates.py` must reject the structure before this is ever called.

    See `test_every_structure_built_can_actually_lose_something`, which is where the
    guarantee actually lives.
    """
    absurd = pop.iron_condor(765, 755, 760, 99.0, 45, 0.15)
    assert absurd is not None and absurd > 0.9, (
        "this is the confident wrong answer the strategy layer exists to prevent "
        "reaching; if it ever returns None on its own, the note above is stale"
    )


class TestModerateShortProfile:
    """The short-window profile, and what it deliberately does *not* change.

    It exists because the DTE band and the risk posture were welded together. Going
    faster than 21 DTE meant switching to `aggressive`, which also widens the short
    delta band from 0.20-0.45 to 0.30-0.55, drops the liquidity floors and raises the
    sizing cap — three risk increases riding along with the one that was wanted.

    So this profile holds every selection rule at moderate's setting and moves the
    window alone. That is not a claim it carries identical risk: a 10 DTE spread at the
    same delta has more gamma than a 45 DTE one, and it will lose faster when it loses.
    What is held constant is how a candidate is *chosen*, not what it does afterwards.
    """

    def test_it_selects_exactly_as_moderate_does(self):
        short, moderate = P.MODERATE_SHORT, P.MODERATE
        assert short.short_delta_min == moderate.short_delta_min
        assert short.short_delta_max == moderate.short_delta_max
        assert short.liquidity == moderate.liquidity
        assert short.weights == moderate.weights
        assert short.position_sizing_cap_pct == moderate.position_sizing_cap_pct
        assert short.structures == moderate.structures

    def test_only_the_window_moves(self):
        assert (P.MODERATE_SHORT.min_dte, P.MODERATE_SHORT.max_dte) == (7, 21)
        assert (P.MODERATE.min_dte, P.MODERATE.max_dte) == (21, 60)

    def test_it_stays_clear_of_the_zero_dte_hole(self):
        """Alpaca returns no greeks at same-day expiry, so the delta and vega gates
        fail closed there. The floor keeps the profile out of that band by
        construction rather than by the operator remembering to."""
        assert P.MODERATE_SHORT.min_dte >= 1

    def test_it_is_reachable_by_name(self):
        assert P.get("moderate_short") is P.MODERATE_SHORT
        assert P.from_env({"RISK_PROFILE": "moderate_short"}).name == "moderate_short"

    def test_a_request_outside_the_band_is_clamped_into_it(self):
        # The 45-day default would otherwise sail past a short profile's ceiling.
        assert P.MODERATE_SHORT.target_dte(45) == 21
        assert P.MODERATE_SHORT.target_dte(1) == 7
        assert P.MODERATE_SHORT.target_dte(14) == 14

    def test_it_cannot_loosen_a_gate_either(self):
        """Same rule as every other profile: strictest wins. A short profile asking
        for 7 DTE against a MIN_DTE of 10 gets 10."""
        limits = Limits(min_dte=10)
        assert P.EffectiveFloor.compose(P.MODERATE_SHORT, limits).min_dte == 10
