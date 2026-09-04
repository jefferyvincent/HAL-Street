"""Trend indicators, computed from daily closes.

TradeScans *fetched* these — SMA, EMA, RSI, MACD — from a vendor's indicator
endpoints, one HTTP round trip each, cached for an hour. Alpaca has no indicator
endpoint, so HAL Street computes them from the daily bars it already pulls. That is
a better arrangement than the one it replaces: one bar request feeds every indicator,
the conventions are visible in this file rather than in a vendor's docs, and the
numbers are reproducible from the recorded closes months later.

Conventions are the standard ones, stated explicitly because indicator libraries
disagree and a silent disagreement here would quietly change the agent's bias:

* **SMA** — arithmetic mean of the last `period` closes.
* **EMA** — seeded with the SMA of the first `period` closes, then smoothed at
  `2/(period+1)`. Seeding matters: seeding on the first close instead makes early
  values wrong and takes ~3x the period to wash out.
* **RSI** — Wilder's smoothing (`1/period`), not a simple average of gains and
  losses. Wilder is what "RSI 14" means to everyone who reads one.
* **MACD** — EMA(12) - EMA(26), signal EMA(9) of that line, histogram the
  difference. The signal EMA is seeded the same way, so it needs 26 + 9 bars before
  it means anything.

Every function returns None rather than a partial answer when there are too few
bars. A trend read off nine days of data is not a trend.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise


def sma(closes: list[float], period: int) -> float | None:
    if period <= 0 or len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def ema_series(closes: list[float], period: int) -> list[float]:
    """The full EMA series, seeded on the SMA of the first `period` closes.

    Returned as a series rather than a single value because MACD needs to smooth one
    EMA with another, and a scalar EMA cannot be chained.
    """
    if period <= 0 or len(closes) < period:
        return []
    k = 2.0 / (period + 1.0)
    value = sum(closes[:period]) / period
    out = [value]
    for close in closes[period:]:
        value = close * k + value * (1.0 - k)
        out.append(value)
    return out


def ema(closes: list[float], period: int) -> float | None:
    series = ema_series(closes, period)
    return series[-1] if series else None


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. None until there are `period + 1` closes to difference."""
    if period <= 0 or len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, curr in pairwise(closes):
        change = curr - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    # An unbroken run of up days has no downside to divide by. RSI is 100 by
    # definition there, not undefined.
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass(frozen=True)
class Macd:
    value: float
    signal: float
    histogram: float


def macd(closes: list[float], fast: int = 12, slow: int = 26,
         signal_period: int = 9) -> Macd | None:
    """MACD line, signal, and histogram — or None without enough history.

    The two EMAs start at different bars (the fast one is seeded 14 closes earlier),
    so the fast series is trimmed to align with the slow one before differencing.
    Subtracting them tail-to-tail without aligning is the classic way to get a MACD
    that is subtly wrong in a way nothing warns you about.
    """
    if slow <= fast or len(closes) < slow + signal_period:
        return None
    fast_series = ema_series(closes, fast)
    slow_series = ema_series(closes, slow)
    if not fast_series or not slow_series:
        return None
    aligned_fast = fast_series[-len(slow_series):]
    line = [f - s for f, s in zip(aligned_fast, slow_series, strict=True)]

    signal_series = ema_series(line, signal_period)
    if not signal_series:
        return None
    value, signal = line[-1], signal_series[-1]
    return Macd(value=value, signal=signal, histogram=value - signal)
