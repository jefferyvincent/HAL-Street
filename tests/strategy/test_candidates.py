"""Candidate construction: pricing, strike selection, and the liquidity pre-filter."""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

from halstreet.gates.base import Limits
from halstreet.strategy import blackscholes as bs
from halstreet.strategy import candidates as C
from halstreet.strategy import profiles as P
from halstreet.strategy import scoring
from halstreet.strategy.bias import BULLISH, NEUTRAL

ASOF = date(2026, 8, 26)
EXPIRY = ASOF + timedelta(days=45)          # 2026-10-10
SPOT = Decimal(765)


def _occ(strike: int, right: str) -> str:
    return f"SPY{EXPIRY:%y%m%d}{right}{strike * 1000:08d}"


def _snapshot(*, bid: float, ask: float, delta: float, iv: float = 0.15,
              oi: int = 5000, vol: int = 800) -> dict:
    return {
        "latestQuote": {"bp": bid, "ap": ask},
        "greeks": {"delta": delta},
        "impliedVolatility": iv,
        "openInterest": oi,
        "dailyBar": {"v": vol},
    }


def _chain(**overrides) -> dict[str, dict]:
    """A synthetic SPY chain: strikes every 2 points from 700 to 830.

    Deltas *and* prices come from the same Black-Scholes surface the strategy layer
    uses, at 15% vol and 45 DTE. That coherence is the point. Two earlier versions of
    this fixture failed in ways that looked like code bugs and were not: hand-drawn
    deltas that broke monotonicity produced a chain on which no iron condor could be
    built, and a price proxy linear in delta produced adjacent-strike credits larger
    than the strike width, which is arbitrage and which `credit_spread` correctly
    refused to construct.

    Every leg is quoted ten cents wide — around 1-3% at these premiums, which is what
    the live 45-DTE index chains actually show.
    """
    chain: dict[str, dict] = {}
    discount = math.exp(-bs.RISK_FREE_RATE * 45 / bs.DAYS_PER_YEAR)
    for strike in range(700, 832, 2):
        c = bs.coefficients(float(SPOT), float(strike), 45, 0.15)
        call_delta = bs.norm_cdf(c.d1)
        call_mid = float(SPOT) * call_delta - strike * discount * bs.norm_cdf(c.d2)
        put_mid = strike * discount * bs.norm_cdf(-c.d2) - float(SPOT) * bs.norm_cdf(-c.d1)
        chain[_occ(strike, "C")] = _snapshot(
            bid=round(call_mid - 0.05, 2), ask=round(call_mid + 0.05, 2),
            delta=round(call_delta, 4))
        chain[_occ(strike, "P")] = _snapshot(
            bid=round(put_mid - 0.05, 2), ask=round(put_mid + 0.05, 2),
            delta=round(call_delta - 1.0, 4))
    chain.update(overrides)
    return chain


def _quotes() -> list[C.Quote]:
    return C.quotes_for(_chain(), EXPIRY)


# --- reading the chain ---------------------------------------------------------

def test_quotes_carry_the_iv_the_pop_calculation_needs():
    quote = _quotes()[0]
    assert quote.iv == Decimal("0.15")
    assert quote.delta is not None


def test_a_crossed_or_missing_quote_is_dropped_rather_than_repaired():
    chain = _chain(**{
        _occ(700, "C"): _snapshot(bid=5.0, ask=4.0, delta=0.9),      # crossed
        _occ(705, "C"): {"latestQuote": {"bp": 1.0}, "greeks": {"delta": 0.9}},  # no ask
        _occ(710, "C"): _snapshot(bid=0.0, ask=0.0, delta=0.9),      # no market
    })
    symbols = {q.contract.symbol for q in C.quotes_for(chain, EXPIRY)}
    assert _occ(700, "C") not in symbols
    assert _occ(705, "C") not in symbols
    assert _occ(710, "C") not in symbols


def test_the_expiry_floor_is_respected_when_choosing_a_target():
    chain = _chain()
    chain.update({f"SPY{ASOF + timedelta(days=2):%y%m%d}C00765000": _snapshot(
        bid=1.0, ask=1.1, delta=0.5)})
    # The 2-DTE expiry is nearer the requested 3 DTE, and is refused anyway.
    assert C.nearest_expiry(chain, 3, asof=ASOF, min_dte=7) == EXPIRY


# --- pricing -------------------------------------------------------------------

def test_a_credit_spread_is_priced_at_the_touch_not_the_mid():
    quotes = _quotes()
    spread = C.credit_spread(quotes, C.Right.PUT, Decimal("0.30"), 2, 45, spot=SPOT)
    short = next(q for q, side in spread.quotes if side == "sell")
    long_ = next(q for q, side in spread.quotes if side == "buy")
    # Sell at the bid, buy at the ask — what actually fills, not what looks good.
    assert -spread.net == short.bid - long_.ask
    assert -spread.net < short.mid - long_.mid


def test_max_loss_is_the_width_less_the_credit():
    quotes = _quotes()
    spread = C.credit_spread(quotes, C.Right.PUT, Decimal("0.30"), 2, 45, spot=SPOT)
    short = next(q for q, side in spread.quotes if side == "sell")
    long_ = next(q for q, side in spread.quotes if side == "buy")
    width = abs(long_.contract.strike - short.contract.strike)
    assert spread.max_loss_usd == (width + spread.net) * 100
    assert spread.max_gain_usd == -spread.net * 100


def test_slippage_is_the_half_spread_summed_across_every_leg():
    quotes = _quotes()
    condor = C.iron_condor(quotes, Decimal("0.25"), 2, 45, spot=SPOT)
    expected = sum((q.half_spread_usd for q, _ in condor.quotes), Decimal(0))
    assert condor.slippage_usd == expected
    assert len(condor.legs) == 4


def test_a_put_spread_sells_below_the_money_and_a_call_spread_above():
    quotes = _quotes()
    put = C.credit_spread(quotes, C.Right.PUT, Decimal("0.25"), 2, 45, spot=SPOT)
    call = C.credit_spread(quotes, C.Right.CALL, Decimal("0.25"), 2, 45, spot=SPOT)
    assert put.shorts[0].contract.strike < SPOT < call.shorts[0].contract.strike
    # And the long wing is further out than the short leg on both sides.
    assert put.quotes[1][0].contract.strike < put.shorts[0].contract.strike
    assert call.quotes[1][0].contract.strike > call.shorts[0].contract.strike


def test_strikes_are_chosen_by_delta_not_by_distance():
    quotes = _quotes()
    near = C.credit_spread(quotes, C.Right.PUT, Decimal("0.40"), 2, 45, spot=SPOT)
    far = C.credit_spread(quotes, C.Right.PUT, Decimal("0.15"), 2, 45, spot=SPOT)
    assert far.shorts[0].contract.strike < near.shorts[0].contract.strike
    assert far.short_delta < near.short_delta


def test_a_condor_carries_a_pop_computed_from_both_shorts_own_ivs():
    condor = C.iron_condor(_quotes(), Decimal("0.25"), 2, 45, spot=SPOT)
    assert condor.kind == P.IRON_CONDOR
    assert 0.0 < condor.pop < 1.0


def test_pop_is_none_without_a_spot_rather_than_assumed():
    spread = C.credit_spread(_quotes(), C.Right.PUT, Decimal("0.30"), 2, 45, spot=None)
    assert spread.pop is None


# --- the liquidity pre-filter --------------------------------------------------

def _floor(**kw) -> P.EffectiveFloor:
    return P.EffectiveFloor.compose(P.MODERATE, Limits(**kw))


def test_an_unknown_open_interest_fails_closed():
    chain = _chain()
    for symbol in list(chain):
        chain[symbol] = {**chain[symbol], "openInterest": None}
    spread = C.credit_spread(C.quotes_for(chain, EXPIRY), C.Right.PUT,
                             Decimal("0.30"), 2, 45, spot=SPOT)
    assert spread.min_open_interest is None
    assert not C.tradeable(spread, _floor())


def test_a_thin_leg_disqualifies_the_whole_structure():
    chain = _chain()
    quotes = C.quotes_for(chain, EXPIRY)
    spread = C.credit_spread(quotes, C.Right.PUT, Decimal("0.30"), 2, 45, spot=SPOT)
    assert C.tradeable(spread, _floor(min_open_interest=250))
    # One leg below the floor is enough: we would have to trade all of them.
    thin = _occ(int(spread.shorts[0].contract.strike), "P")
    chain[thin] = {**chain[thin], "openInterest": 3}
    thin_spread = C.credit_spread(C.quotes_for(chain, EXPIRY), C.Right.PUT,
                                  Decimal("0.30"), 2, 45, spot=SPOT)
    assert not C.tradeable(thin_spread, _floor(min_open_interest=250))


def test_a_wide_leg_disqualifies_the_structure_whatever_it_costs():
    # The pre-filter must never be looser than the gate it anticipates, so the
    # ceiling is a flat percentage with no mid-dependent exemption for cheap wings.
    # See `profiles.LiquidityFloor` for the measurement behind that decision.
    floor = _floor(max_bid_ask_width_pct=Decimal(10))
    clean = C.credit_spread(_quotes(), C.Right.PUT, Decimal("0.20"), 2, 45, spot=SPOT)
    assert C.tradeable(clean, floor)

    # Widen the long wing around its own mid — the structure keeps its economics and
    # loses only its tradeability, which is the thing under test.
    chain = _chain()
    hurt = clean.legs[1]["symbol"]
    mid = C.quotes_for(chain, EXPIRY)
    mid = next(q for q in mid if q.contract.symbol == hurt).mid
    chain[hurt] = {**chain[hurt],
                   "latestQuote": {"bp": float(mid) * 0.85, "ap": float(mid) * 1.15}}
    quotes = C.quotes_for(chain, EXPIRY)
    assert next(q for q in quotes if q.contract.symbol == hurt).spread_pct > 10

    spread = C.credit_spread(quotes, C.Right.PUT, Decimal("0.20"), 2, 45, spot=SPOT)
    assert hurt in [leg["symbol"] for leg in spread.legs]
    assert not C.tradeable(spread, floor)


# --- the ranked menu -----------------------------------------------------------

def _generate(profile=P.MODERATE, ctx=None, **kw):
    return C.generate(_chain(), spot=SPOT, target_dte=45, limits=Limits(),
                      profile=profile, ctx=ctx, asof=ASOF, **kw)


def test_the_menu_is_scored_capped_and_led_by_the_best_candidate():
    menu = _generate(limit=4)
    everything = _generate(limit=999)
    assert 0 < len(menu) <= 4
    assert all(c.breakdown is not None for c in menu)
    assert menu[0].score == max(c.score for c in everything)


def test_within_one_kind_the_menu_is_in_score_order():
    # Diversification reorders across kinds, never inside one.
    menu = _generate(limit=999)
    for kind in {c.kind for c in menu}:
        scores = [c.score for c in menu if c.kind == kind]
        assert scores == sorted(scores, reverse=True)


def test_the_menu_offers_a_genuine_alternative_not_six_of_the_same_thing():
    # Measured failure: under a bullish read the six best-scoring SPY candidates
    # were all put credit spreads on the same short strike, differing only in wing
    # width. The model was choosing between rounding errors.
    menu = _generate(ctx=scoring.Context(bias=BULLISH, regime="high",
                                         events=scoring.EventWindow(known=True),
                                         weights=P.MODERATE.weights), limit=6)
    assert len({c.kind for c in menu}) > 1
    assert menu[0].kind == P.PUT_CREDIT      # the bias still decides the top pick


def test_a_structure_that_cannot_outrun_its_own_spread_is_never_offered():
    # Live QQQ, 710/708 put spread: $14 max gain against $32.50 of one-way entry
    # slippage. Every gate passes it — they judge risk, not edge.
    doomed = C.Candidate(name="doomed", kind=P.PUT_CREDIT, legs=[], net=Decimal("-0.14"),
                         max_loss_usd=Decimal(186), max_gain_usd=Decimal(14),
                         dte=51, slippage_usd=Decimal("32.50"))
    assert not C.viable(doomed)
    doomed.slippage_usd = Decimal("4.50")
    assert C.viable(doomed)


def test_unmeasurable_slippage_does_not_disqualify_on_its_own():
    # The liquidity pre-filter already rejects a leg with no readable spread; this
    # check is about edge, and it should not double as a second liquidity gate.
    unknown = C.Candidate(name="?", kind=P.PUT_CREDIT, legs=[], net=Decimal("-0.14"),
                          max_loss_usd=Decimal(186), max_gain_usd=Decimal(14),
                          dte=51, slippage_usd=None)
    assert C.viable(unknown)


def test_diversify_falls_back_to_score_order_when_there_is_only_one_kind():
    menu = _generate(profile=P.CONSERVATIVE, limit=999)
    only_puts = [c for c in menu if c.kind == P.PUT_CREDIT]
    assert C.diversify(only_puts, 3) == only_puts[:3]
    assert C.diversify(only_puts, 0) == []


def test_the_same_chain_always_produces_the_same_order():
    # Ties break on POP then name, so nothing depends on dict iteration order.
    first = [c.name for c in _generate()]
    second = [c.name for c in _generate()]
    assert first == second


def test_a_conservative_profile_is_offered_no_condors():
    menu = _generate(profile=P.CONSERVATIVE)
    assert menu
    assert all(c.kind != P.IRON_CONDOR for c in menu)


def test_the_bias_reorders_the_menu_without_changing_what_is_legal():
    # An uncapped menu, so the comparison is about ordering rather than truncation.
    bullish = _generate(ctx=scoring.Context(bias=BULLISH, regime="high",
                                            events=scoring.EventWindow(known=True),
                                            weights=P.MODERATE.weights), limit=999)
    neutral = _generate(ctx=scoring.Context(bias=NEUTRAL, regime="high",
                                            events=scoring.EventWindow(known=True),
                                            weights=P.MODERATE.weights), limit=999)
    assert {c.name for c in bullish} == {c.name for c in neutral}
    assert bullish[0].kind == P.PUT_CREDIT          # the bullish credit structure
    assert neutral[0].kind == P.IRON_CONDOR         # what a neutral read is for


def test_no_structure_ever_exceeds_the_four_leg_ceiling():
    assert all(len(c.legs) <= 4 for c in _generate(limit=50))


def test_every_candidate_offered_would_survive_its_own_pre_filter():
    floor = P.EffectiveFloor.compose(P.MODERATE, Limits())
    assert all(C.tradeable(c, floor) for c in _generate(limit=50))


def test_the_prompt_shape_carries_the_reasoning_not_just_the_ranking():
    prompt = _generate(limit=1)[0].to_prompt()
    for key in ("kind", "legs", "net_price", "max_loss_usd", "prob_of_profit",
                "entry_slippage_usd", "score", "score_breakdown"):
        assert key in prompt
    # The raw quotes stay out: the model gets summary statistics, not the chain.
    assert "quotes" not in prompt


def test_an_empty_chain_yields_an_empty_menu_rather_than_raising():
    assert C.generate({}, spot=SPOT, limits=Limits(), asof=ASOF) == []
