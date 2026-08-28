"""Market structure: where price actually broke, and which way.

Every indicator the bias currently votes on — the moving averages, RSI, MACD — is an
average of closes. They agree with each other by construction, and none of them says
anything about a *level*: a 20-EMA above a 50-EMA is the same vote whether price has
just taken out a three-month high or is drifting in the middle of a range it has been
stuck in since June.

A break of structure is the other kind of evidence. It is a claim about one specific
price having been exceeded, which is checkable against a chart, and it disagrees with
the moving averages often enough to be worth a vote of its own.

**Confirmation-gated, which is most of the value.** A swing high is not a signal; a
close *above* it is. Flagging levels that have held would light this read permanently,
and a badge that is always on stops being read — the same argument `patterns.py` makes
and the same discipline.

**Where this may and may not go.** It votes on what gets *proposed*, through
`strategy.bias`, alongside the indicators and subject to the same margin. It may not
reach an exit. That is the line `patterns.py` draws and the reason is unchanged: exits
are the one path in this project with neither a model call nor a gate, deliberately,
because a position that cannot be closed is how defined risk stops being defined. A
chart heuristic that can flatten a position is a far bigger decision than one that can
put a candidate on a menu, and `tests/marketdata/test_smc.py` walks the imports to keep
it that way.

Pivots come from the day's high and low rather than its close, because a swing is where
price *reached* — same reason `patterns.py` gives.
"""

from __future__ import annotations

from dataclasses import dataclass

BULLISH, BEARISH, NEUTRAL = "bullish", "bearish", "neutral"

#: Break of structure: a close beyond the last confirmed swing in the same direction
#: the tape was already going. Continuation.
BOS = "break-of-structure"

#: Change of character: a close beyond the last swing *against* the prevailing
#: direction. The first crack, and the one worth telling apart from a continuation.
CHOCH = "change-of-character"

#: Bars needed before swings mean anything. Two windows plus room for a break.
MIN_BARS = 40

#: Half-width of the fractal window. A swing is the extreme of the eleven bars around
#: it — prominent enough that a two-day wiggle is not a structural level.
PIVOT_K = 5

#: How far past a level a close has to be, as a fraction, to count as through it. A
#: close a tick above a swing high is a touch, not a break, and treating it as one puts
#: the read on a hair trigger in exactly the chop it exists to see through.
BREAK_MARGIN = 0.001


@dataclass(frozen=True)
class Structure:
    """What the tape's own levels say, and which one it said it at."""

    direction: str
    #: BOS, CHOCH, or None when nothing has been broken.
    event: str | None
    #: The price that was taken out. None when nothing was.
    level: float | None
    #: Bars since the break, so a stale one can be told from a fresh one.
    bars_ago: int | None
    note: str

    def to_prompt(self) -> dict:
        return {"direction": self.direction, "event": self.event,
                "level": None if self.level is None else round(self.level, 2),
                "bars_ago": self.bars_ago, "note": self.note}


def read(bars: list[dict]) -> Structure | None:
    """The most recent structural break, or None where there is nothing to read.

    None rather than a neutral Structure: "no break" and "could not look" are
    different facts, and the caller casts a vote on one and not the other.
    """
    highs, lows, closes = _series(bars)
    if highs is None:
        return None

    swing_highs = _pivots(highs, high=True)
    swing_lows = _pivots(lows, high=False)
    if not swing_highs or not swing_lows:
        return None

    last = len(closes) - 1
    close = closes[last]

    # The most recent swing on each side that the current close could have broken.
    # Only swings confirmed *before* the breaking bar count: a pivot needs PIVOT_K bars
    # after it to exist at all, so one that includes today has not been confirmed and
    # using it would let today's bar create the level it then breaks.
    high_i, high_v = _latest(swing_highs, before=last)
    low_i, low_v = _latest(swing_lows, before=last)
    if high_v is None or low_v is None:
        return None

    broke_up = close > high_v * (1 + BREAK_MARGIN)
    broke_down = close < low_v * (1 - BREAK_MARGIN)
    if broke_up == broke_down:
        # Neither, or — impossibly — both. Either way nothing was established.
        return Structure(direction=NEUTRAL, event=None, level=None, bars_ago=None,
                         note="price is inside its last confirmed swing range")

    if broke_up:
        direction, level, index = BULLISH, high_v, high_i
    else:
        direction, level, index = BEARISH, low_v, low_i

    # Continuation or reversal, against the structure the swings had established —
    # not against whichever pivot happened to come last. In a range the last pivot is
    # noise, and reading it as the prevailing direction made a clean breakout of a
    # sideways market report as a change of character half the time depending on which
    # side wiggled most recently.
    prevailing = _prevailing(swing_highs, swing_lows)
    event = CHOCH if prevailing not in (NEUTRAL, direction) else BOS
    ago = last - index

    return Structure(
        direction=direction, event=event, level=level, bars_ago=ago,
        note=(f"closed {'above' if direction == BULLISH else 'below'} {level:.2f}, "
              f"the last confirmed swing {'high' if direction == BULLISH else 'low'} "
              f"{ago} bar(s) back"),
    )


def _prevailing(highs: list[tuple[int, float]],
                lows: list[tuple[int, float]]) -> str:
    """The structure the swings had established before this break.

    Higher highs *and* higher lows is an uptrend; lower highs and lower lows is a
    downtrend; anything else is a range, and a range has no direction to be broken
    against. That last case is why this is not simply "which pivot came last": in
    sideways price the most recent pivot alternates on noise, and reading it as the
    trend made a clean breakout report as a reversal roughly half the time.

    A break out of a range is therefore a break of structure rather than a change of
    character. Nothing was reversed; structure was established where there was none.
    """
    if len(highs) < 2 or len(lows) < 2:
        return NEUTRAL
    # Three-way, not two. Written as `>` and `not >`, a pair of equal swings — which
    # is exactly what a flat range looks like — fell into the falling branch and a
    # sideways market reported as a downtrend.
    high_step = _step(highs[-2][1], highs[-1][1])
    low_step = _step(lows[-2][1], lows[-1][1])
    if high_step > 0 and low_step > 0:
        return BULLISH
    if high_step < 0 and low_step < 0:
        return BEARISH
    return NEUTRAL


def _step(previous: float, latest: float) -> int:
    """Rising, falling, or level. Level is its own answer and not a quiet 'falling'."""
    return (latest > previous) - (latest < previous)


def _series(bars: list[dict]) -> tuple[list[float] | None, list[float], list[float]]:
    """Highs, lows and closes as floats, or (None, [], []) if they cannot be read."""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for bar in bars or []:
        try:
            highs.append(float(bar["h"]))
            lows.append(float(bar["l"]))
            closes.append(float(bar["c"]))
        except (KeyError, TypeError, ValueError):
            return None, [], []
    if len(closes) < MIN_BARS:
        return None, [], []
    return highs, lows, closes


def _pivots(values: list[float], *, high: bool) -> list[tuple[int, float]]:
    """Fractal swings: index i where it is the extreme of the window around it."""
    out: list[tuple[int, float]] = []
    for i in range(PIVOT_K, len(values) - PIVOT_K):
        window = values[i - PIVOT_K: i + PIVOT_K + 1]
        if values[i] == (max(window) if high else min(window)):
            out.append((i, values[i]))
    return out


def _latest(pivots: list[tuple[int, float]], *, before: int) -> tuple[int, float | None]:
    """The most recent swing confirmed strictly before `before`."""
    for index, value in reversed(pivots):
        if index + PIVOT_K < before:
            return index, value
    return -1, None
