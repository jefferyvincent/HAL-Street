"""Black-Scholes probabilities, indicators, and the volatility regime."""

from __future__ import annotations

import math

from halstreet.strategy import blackscholes as bs
from halstreet.strategy import indicators as ind
from halstreet.strategy import regime

# --- Black-Scholes ------------------------------------------------------------

def test_normal_cdf_matches_known_quantiles():
    assert bs.norm_cdf(0) == 0.5
    assert round(bs.norm_cdf(1.959964), 4) == 0.975
    assert round(bs.norm_cdf(-1.959964), 4) == 0.025


def test_the_two_tails_sum_to_one():
    above = bs.prob_above(765, 780, 45, 0.15)
    below = bs.prob_below(765, 780, 45, 0.15)
    assert round(above + below, 12) == 1.0


def test_at_the_money_is_close_to_a_coin_flip():
    # Slightly above 0.5 for a call: the drift term nudges d2, but only just.
    p = bs.prob_above(100, 100, 30, 0.20)
    assert 0.48 < p < 0.55


def test_a_further_strike_is_less_likely_to_be_reached():
    near = bs.prob_above(765, 775, 45, 0.15)
    far = bs.prob_above(765, 820, 45, 0.15)
    assert far < near


def test_more_volatility_fattens_both_tails():
    calm = bs.prob_above(765, 820, 45, 0.10)
    wild = bs.prob_above(765, 820, 45, 0.40)
    assert wild > calm


def test_between_narrows_as_the_range_narrows():
    wide = bs.prob_between(765, 700, 830, 45, 0.15)
    narrow = bs.prob_between(765, 760, 770, 45, 0.15)
    assert wide > narrow > 0


def test_impossible_inputs_return_none_rather_than_a_guess():
    # Every one of these would produce a plausible-looking number if the module
    # substituted a default. None is the honest answer.
    assert bs.prob_above(765, 800, 0, 0.15) is None       # expired
    assert bs.prob_above(765, 800, 45, 0) is None         # no volatility
    assert bs.prob_above(0, 800, 45, 0.15) is None        # no spot
    assert bs.prob_above(765, 0, 45, 0.15) is None        # no strike
    assert bs.prob_between(765, 800, 700, 45, 0.15) is None   # inverted range


# --- indicators ---------------------------------------------------------------

def test_sma_is_the_mean_of_the_window():
    assert ind.sma([1, 2, 3, 4, 5, 6], 3) == 5.0


def test_ema_of_a_straight_line_equals_its_sma():
    # A perfectly linear series has no curvature for the smoothing to bite on, so
    # an SMA-seeded EMA lands exactly on the SMA. This is what proves the seeding
    # is SMA-based rather than first-close-based.
    closes = [float(x) for x in range(1, 101)]
    assert ind.ema(closes, 20) == ind.sma(closes, 20)


def test_macd_of_a_constant_slope_is_the_ema_lag_difference():
    # On a ramp of slope 1, EMA(n) lags the price by (n-1)/2 bars, so
    # EMA(12) - EMA(26) = (26 - 12) / 2 = 7 exactly.
    closes = [float(x) for x in range(1, 121)]
    macd = ind.macd(closes)
    assert round(macd.value, 9) == 7.0
    assert abs(macd.histogram) < 1e-9


def test_rsi_pins_at_100_when_every_day_is_an_up_day():
    assert ind.rsi([float(x) for x in range(1, 40)]) == 100.0


def test_rsi_is_50_on_a_flat_series():
    # No gains and no losses: neither overbought nor oversold, and emphatically not
    # a division by zero.
    assert ind.rsi([100.0] * 40) == 50.0


def test_rsi_of_a_choppy_series_sits_in_the_middle():
    closes = [100 + 5 * math.sin(i / 4) for i in range(120)]
    assert 20 < ind.rsi(closes) < 80


def test_indicators_return_none_rather_than_a_partial_answer():
    short = [1.0, 2.0, 3.0]
    assert ind.sma(short, 50) is None
    assert ind.ema(short, 50) is None
    assert ind.rsi(short) is None
    assert ind.macd(short) is None
    assert ind.ema_series(short, 50) == []


# --- volatility regime ---------------------------------------------------------

def _walk(n: int, sigma: float, seed: float = 1.0) -> list[float]:
    """A deterministic pseudo-random walk — no RNG, so the test cannot flake."""
    closes = [100.0]
    for i in range(n):
        step = math.sin(i * 12.9898 + seed) * 43758.5453
        closes.append(closes[-1] * math.exp((step - int(step) - 0.5) * sigma))
    return closes


def test_annualized_vol_scales_with_the_dispersion_of_returns():
    calm = regime.annualized_vol(regime.log_returns(_walk(300, 0.004)))
    wild = regime.annualized_vol(regime.log_returns(_walk(300, 0.040)))
    assert wild > calm > 0


def test_too_little_history_is_unknown_not_a_guess():
    assert regime.build([100.0] * 40).label == regime.UNKNOWN
    assert regime.build([]).rank is None


def test_a_volatility_spike_ranks_high():
    closes = _walk(300, 0.004) + _walk(25, 0.05, seed=3.0)[1:]
    result = regime.build(closes)
    assert result.label == regime.HIGH
    assert result.rank > 70


def test_the_rank_excludes_todays_own_reading():
    # Ranking a value against a window containing itself pins any new high to 100,
    # which is exactly when the number is being leaned on.
    series = [0.10] * 260
    assert regime.rank_in(0.20, series[:-1]) == 50.0


def test_a_flat_volatility_history_ranks_in_the_middle():
    assert regime.rank_in(0.15, [0.15] * 100) == 50.0


def test_the_regime_never_stops_declaring_itself_a_proxy():
    # HV rank is not IV rank. If this flag is ever conditional, the journal starts
    # claiming a measurement the project does not take.
    assert regime.build(_walk(320, 0.01)).is_proxy is True
    assert regime.UNKNOWN_REGIME.is_proxy is True
