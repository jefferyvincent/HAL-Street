"""Volatility regime, from realized vol — and honest about being a proxy.

Ported from TradeScans' `iv-rank.ts`, including the thing it was careful to admit:
this is **not IV rank**. IV rank compares today's implied volatility against a year
of its own history, and needs a year of stored IV, which neither TradeScans nor this
project has. What we compute instead is *HV rank* — today's 30-day realized
volatility against a trailing year of the same measure. `Regime.is_proxy` is True and
stays True, and every consumer that reports a regime says which one it read.

The two move together most of the time and diverge exactly when it matters — before
an event, implied climbs while realized has not moved yet. So a high HV rank means
"the tape has been wild", not "options are expensive". That difference is why the
regime is one weighted term among six rather than a gate.

Why the regime is in the ranking at all: a credit structure is short volatility. It
wants to be sold when volatility is high and mean-reverting, and it is a poor trade
when volatility is already at the floor — same structure, same greeks, different bet.

Method: log returns, sample standard deviation (n-1), annualized by sqrt(252). The
rank is the current value's percentile position between the trailing year's low and
high, which is a min-max rank rather than a count-based percentile — the same
definition TradeScans used and the one "IV rank" conventionally means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

TRADING_DAYS_PER_YEAR = 252
HV_WINDOW = 30
# A year of rank history plus the window it takes to produce the first value.
LOOKBACK_TRADING_DAYS = TRADING_DAYS_PER_YEAR + HV_WINDOW
# Below this many rank samples the low/high are set by too little history to mean
# anything, and a rank against them would be noise wearing a percentile's clothes.
MIN_RANK_SAMPLES = 30

LOW = "low"
MEDIUM = "medium"
HIGH = "high"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Regime:
    """Where volatility sits in its own trailing-year range."""

    label: str                      # low | medium | high | unknown
    rank: float | None              # 0-100, or None when unknown
    realized_vol: float | None      # annualized, as a fraction (0.18 = 18%)
    year_low: float | None
    year_high: float | None
    samples: int
    # Always True. See the module docstring: this is realized vol, not implied.
    is_proxy: bool = True

    @property
    def known(self) -> bool:
        return self.label != UNKNOWN

    def describe(self) -> str:
        if not self.known:
            return "volatility regime unknown (not enough history)"
        return (
            f"{self.label} volatility — 30d realized {self.realized_vol * 100:.1f}%, "
            f"rank {self.rank:.0f}/100 of the trailing year "
            f"({self.year_low * 100:.1f}%-{self.year_high * 100:.1f}%), "
            f"realized-vol proxy over {self.samples} samples"
        )


UNKNOWN_REGIME = Regime(label=UNKNOWN, rank=None, realized_vol=None,
                        year_low=None, year_high=None, samples=0)


def log_returns(closes: list[float]) -> list[float]:
    return [
        math.log(curr / prev)
        for prev, curr in pairwise(closes)
        if prev > 0 and curr > 0
    ]


def annualized_vol(returns: list[float]) -> float:
    """Sample standard deviation of log returns, annualized.

    n-1 in the denominator, not n. With a 30-day window the difference is ~1.7%
    of the answer — small, but it is the difference between an unbiased estimate
    and a biased one, and it costs nothing.
    """
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def rolling_vol(closes: list[float], window: int = HV_WINDOW) -> list[float]:
    """One realized-vol reading per bar, once there are enough bars to fill a window."""
    if len(closes) <= window:
        return []
    return [
        annualized_vol(log_returns(closes[end - window:end + 1]))
        for end in range(window, len(closes))
    ]


def rank_in(value: float, history: list[float]) -> float:
    """Min-max position of `value` inside `history`, 0-100.

    A flat history returns 50 rather than dividing by zero: if volatility has not
    moved all year, today is neither high nor low within it.
    """
    if not history:
        return 0.0
    low, high = min(history), max(history)
    if high == low:
        return 50.0
    clamped = max(low, min(high, value))
    return (clamped - low) / (high - low) * 100.0


def classify(rank: float) -> str:
    """TradeScans' thresholds, unchanged: under 30 low, over 70 high."""
    if rank < 30:
        return LOW
    if rank <= 70:
        return MEDIUM
    return HIGH


def build(closes: list[float], *, window: int = HV_WINDOW) -> Regime:
    """The regime for one underlying from its daily closes, oldest first.

    Returns the unknown regime rather than a guess whenever the history is too
    short. Consumers are built to handle unknown; none of them is built to notice
    that a confident-looking rank came from six weeks of data.
    """
    series = rolling_vol(closes, window)
    if len(series) < MIN_RANK_SAMPLES + 1:
        return UNKNOWN_REGIME

    current = series[-1]
    # Exclude the current reading from its own comparison window — ranking a value
    # against a set containing itself pins it to 100 whenever today is the year's
    # high, which is exactly when the number is being leaned on.
    history = series[-TRADING_DAYS_PER_YEAR:-1]
    if len(history) < MIN_RANK_SAMPLES:
        return UNKNOWN_REGIME

    rank = rank_in(current, history)
    return Regime(
        label=classify(rank),
        rank=rank,
        realized_vol=current,
        year_low=min(history),
        year_high=max(history),
        samples=len(history),
    )
