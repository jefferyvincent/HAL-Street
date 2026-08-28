"""Directional bias from trend indicators — a vote, not a forecast.

Ported from TradeScans' `bias-derivation.ts`, with the fetching replaced by
computation (see `indicators`). The scoring is unchanged: each indicator casts a
vote, MACD gets two because it is the only one carrying both trend and momentum, and
the verdict needs a margin of two votes to be anything other than neutral.

**Neutral is the default and it is a real answer.** A two-vote margin means a book
that disagrees with itself reads neutral, and neutral is the regime in which the
structures this agent actually trades — credit spreads and iron condors — are at
their best. An indicator blend that produced a confident direction every day would be
worse for this strategy, not better.

The reasons list is the point of the output as much as the direction is. Every
proposal the model writes carries the bias that shaped its menu, and "price above
50-EMA, MACD above signal, RSI 58 in bullish zone" is an auditable sentence months
later; "bullish" alone is not.

Bias is **not** a gate. It reorders the menu handed to the model. Nothing here can
approve a trade, and being wrong about direction costs ranking quality, not risk
control — which is the correct place to put a signal this noisy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from halstreet.strategy.indicators import Macd, ema, macd, rsi, sma

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

# Votes of margin needed to call a direction. Below this it is noise.
DECISION_MARGIN = 2


@dataclass(frozen=True)
class Snapshot:
    """The indicator readings a bias is derived from. Any of them may be None."""

    symbol: str
    spot: float
    sma50: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    rsi14: float | None = None
    macd: Macd | None = None
    #: Where price last broke a confirmed swing, from `marketdata.smc`. The only
    #: reading here that is about a level rather than an average of closes.
    structure: Any = None

    @property
    def coverage(self) -> int:
        """How many of the five indicators actually resolved.

        Structure is deliberately not counted. Coverage answers "how much of the
        indicator set resolved", the set has always been five, and quietly making it
        six would move every historical coverage figure without anything having
        changed about the history.
        """
        return sum(x is not None for x in
                   (self.sma50, self.ema20, self.ema50, self.rsi14, self.macd))


@dataclass(frozen=True)
class Bias:
    direction: str
    bullish: int
    bearish: int
    reasons: list[str] = field(default_factory=list)
    # Indicators that resolved, out of five. A direction called on two indicators is
    # weaker than the same direction called on five, and the journal should show it.
    coverage: int = 0

    def describe(self) -> str:
        if not self.reasons:
            return "no directional bias (no indicators available)"
        return (f"{self.direction} ({self.bullish}-{self.bearish} on {self.coverage}/5 "
                f"indicators): " + "; ".join(self.reasons))


def snapshot(symbol: str, spot: float, closes: list[float], *,
             structure: Any = None) -> Snapshot:
    """Compute every indicator that the available history supports."""
    return Snapshot(
        symbol=symbol.upper(),
        spot=spot,
        sma50=sma(closes, 50),
        ema20=ema(closes, 20),
        ema50=ema(closes, 50),
        rsi14=rsi(closes, 14),
        macd=macd(closes),
        structure=structure,
    )


def derive(snap: Snapshot) -> Bias:
    """Tally the votes. Missing indicators abstain — they do not vote neutral."""
    reasons: list[str] = []
    bullish = 0
    bearish = 0

    if snap.ema50 is not None:
        if snap.spot > snap.ema50:
            bullish += 1
            reasons.append("price above 50-EMA")
        else:
            bearish += 1
            reasons.append("price below 50-EMA")

    if snap.ema20 is not None and snap.ema50 is not None:
        if snap.ema20 > snap.ema50:
            bullish += 1
            reasons.append("20-EMA above 50-EMA (golden cross structure)")
        else:
            bearish += 1
            reasons.append("20-EMA below 50-EMA (death cross structure)")

    if snap.sma50 is not None:
        if snap.spot > snap.sma50:
            bullish += 1
            reasons.append("price above 50-SMA")
        else:
            bearish += 1
            reasons.append("price below 50-SMA")

    if snap.rsi14 is not None:
        value = snap.rsi14
        # Overbought and oversold invert: an extreme reading is a mean-reversion
        # signal, not a continuation one, which is why 75 votes bearish while 60
        # votes bullish.
        if value >= 70:
            bearish += 1
            reasons.append(f"RSI {value:.1f} overbought")
        elif value <= 30:
            bullish += 1
            reasons.append(f"RSI {value:.1f} oversold")
        elif value > 50:
            bullish += 1
            reasons.append(f"RSI {value:.1f} in bullish zone")
        elif value < 50:
            bearish += 1
            reasons.append(f"RSI {value:.1f} in bearish zone")

    if snap.macd is not None:
        above = snap.macd.value > snap.macd.signal
        rising = snap.macd.histogram > 0
        # Two votes, and only when trend and momentum agree. A MACD line above its
        # signal with a shrinking histogram is a trend running out of fuel — that
        # genuinely is no signal, so it casts no vote rather than half of one.
        if above and rising:
            bullish += 2
            reasons.append("MACD above signal with positive histogram")
        elif not above and not rising:
            bearish += 2
            reasons.append("MACD below signal with negative histogram")
        else:
            reasons.append("MACD mixed (no signal)")

    # Market structure, when there is a read. One vote, weighted like the moving
    # averages rather than above them: it is better evidence in the sense that it is
    # about a specific level rather than an average of closes, and it is one opinion
    # among several either way. A read that found no break casts nothing — a level
    # that held is not a signal about anything.
    if snap.structure is not None and snap.structure.event is not None:
        if snap.structure.direction == BULLISH:
            bullish += 1
            reasons.append(f"structure {snap.structure.event}: {snap.structure.note}")
        elif snap.structure.direction == BEARISH:
            bearish += 1
            reasons.append(f"structure {snap.structure.event}: {snap.structure.note}")

    margin = bullish - bearish
    if margin >= DECISION_MARGIN:
        direction = BULLISH
    elif margin <= -DECISION_MARGIN:
        direction = BEARISH
    else:
        direction = NEUTRAL

    return Bias(direction=direction, bullish=bullish, bearish=bearish,
                reasons=reasons, coverage=snap.coverage)


def for_symbol(symbol: str, spot: float, closes: list[float], *,
               structure: Any = None) -> Bias:
    """The tape's direction, from the indicators and — where one was read — structure.

    `structure` is typed loosely on purpose. `strategy/` holds no I/O and imports no
    `marketdata` reader; taking the read as a value keeps that true, and keeps this
    module testable without a bar series.
    """
    return derive(snapshot(symbol, spot, closes, structure=structure))
