"""Confirmed chart patterns on an underlying's daily bars.

Ported from HAL's `charting._detect_patterns`, trimmed to what survives on a daily
index series and to what a defined-risk options book can actually use.

**Confirmation-gated, which is most of the value.** A double top is not a double
top until price breaks the neckline between the peaks; before that it is two highs
that happen to be close together, which is most of every chart. Flagging setups
that have not triggered is how a pattern read becomes noise, and a badge that is
always lit stops being read.

**What this is for, and what it is not.** These annotate positions the agent is
already holding. Nothing here closes anything and nothing here is consulted by
`gates/` or by `manager.evaluate_exit` — a test asserts the exit path never
imports this module. HAL draws the same line for the same reason: a chart
heuristic that can flatten a position is a far bigger decision than a badge, and
the exits already have owners that are arithmetic rather than opinion.

Pivots come from the day's high and low rather than its close, because a swing is
where price *reached*. `get_daily_bars` supplies both and the closes-only version
was throwing them away.
"""

from __future__ import annotations

from dataclasses import dataclass

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

#: How "equal" two swings must be to count as a pair.
EQUAL_TOLERANCE = 0.008
#: Minimum intervening move for a reversal to be worth naming.
SEPARATION = 0.015
#: Shoulder symmetry for head-and-shoulders.
SHOULDER_TOLERANCE = 0.03
#: How flat a triangle's boundary must be.
FLATNESS = 0.01
#: Bars needed before any of this means anything.
MIN_BARS = 40


@dataclass(frozen=True)
class Pattern:
    """One confirmed setup: what it is, which way it points, and where it triggered."""

    name: str
    side: str
    note: str

    def to_prompt(self) -> dict[str, str]:
        return {"name": self.name, "side": self.side, "note": self.note}


def _pivots(values: list[float], kind: str, k: int) -> list[tuple[int, float]]:
    """Fractal pivots: index i is a pivot when it is the extreme of [i-k, i+k].

    Larger k gives fewer, more prominent swings. Scaled to the series length rather
    than fixed, so a 500-day window and a 60-day one do not produce wildly different
    numbers of "swings".
    """
    raw: list[tuple[int, float]] = []
    for i in range(k, len(values) - k):
        window = values[i - k: i + k + 1]
        if (values[i] == max(window)) if kind == "high" else (values[i] == min(window)):
            raw.append((i, values[i]))

    # Merge neighbours, keeping the extreme of each run.
    #
    # A flat extreme spans more than one bar — a top that holds for two sessions, or
    # any series where the turn is not a single point — and every bar in it satisfies
    # the window test. Left as-is, the last two "pivots" are two halves of the same
    # swing, so `_double` compares a peak against itself, finds it equal, and then
    # looks for a neckline between two adjacent indices where there is nothing at all.
    # Every reversal pattern silently stopped firing.
    merged: list[tuple[int, float]] = []
    for index, value in raw:
        if merged and index - merged[-1][0] <= k:
            better = value > merged[-1][1] if kind == "high" else value < merged[-1][1]
            if better:
                merged[-1] = (index, value)
            continue
        merged.append((index, value))
    return merged


def _double(highs: list[tuple[int, float]], lows: list[tuple[int, float]],
            last: float, *, top: bool) -> Pattern | None:
    """Double top or bottom, confirmed on the neckline break."""
    peaks, mids = (highs, lows) if top else (lows, highs)
    if len(peaks) < 2 or not mids:
        return None
    (i1, a), (i2, b) = peaks[-2], peaks[-1]
    extreme = max(a, b) if top else min(a, b)
    if not extreme or abs(a - b) / max(a, b) > EQUAL_TOLERANCE:
        return None
    between = [v for idx, v in mids if i1 < idx < i2]
    if not between:
        return None
    neck = min(between) if top else max(between)
    move = (extreme - neck) / extreme if top else (neck - extreme) / neck
    if move < SEPARATION:
        return None
    if top and last < neck:
        return Pattern("double top", BEARISH, f"confirmed below {neck:.2f}")
    if not top and last > neck:
        return Pattern("double bottom", BULLISH, f"confirmed above {neck:.2f}")
    return None


def _head_and_shoulders(highs: list[tuple[int, float]], lows: list[tuple[int, float]],
                        last: float, *, top: bool) -> Pattern | None:
    """Three swings with a higher (or lower) head, even shoulders, neckline broken."""
    peaks, mids = (highs, lows) if top else (lows, highs)
    if len(peaks) < 3 or len(mids) < 2:
        return None
    (_, left), (_, head), (_, right) = peaks[-3:]
    head_ok = (head > left and head > right) if top else (head < left and head < right)
    if not head_ok or abs(left - right) / max(left, right) > SHOULDER_TOLERANCE:
        return None
    neck = min(v for _, v in mids[-2:]) if top else max(v for _, v in mids[-2:])
    if top and last < neck:
        return Pattern("head and shoulders", BEARISH, f"neckline broken at {neck:.2f}")
    if not top and last > neck:
        return Pattern("inverse head and shoulders", BULLISH,
                       f"neckline broken at {neck:.2f}")
    return None


def _triangle(highs: list[tuple[int, float]], lows: list[tuple[int, float]],
              last: float, *, descending: bool) -> Pattern | None:
    """A flat boundary with the other side converging on it, broken."""
    if len(highs) < 2 or len(lows) < 2:
        return None
    (h1, h2) = highs[-2][1], highs[-1][1]
    (l1, l2) = lows[-2][1], lows[-1][1]
    if descending:
        flat = abs(l1 - l2) / max(l1, l2) <= FLATNESS
        converging = h2 < h1
        if flat and converging and last < min(l1, l2):
            return Pattern("descending triangle", BEARISH,
                           f"support at {min(l1, l2):.2f} given way")
        return None
    flat = abs(h1 - h2) / max(h1, h2) <= FLATNESS
    converging = l2 > l1
    if flat and converging and last > max(h1, h2):
        return Pattern("ascending triangle", BULLISH,
                       f"resistance at {max(h1, h2):.2f} cleared")
    return None


def detect(bars: list[dict]) -> list[Pattern]:
    """Every confirmed pattern on this series, most significant first.

    An empty list is the ordinary answer and is not a failure: most days a chart is
    doing nothing nameable, and saying so is the point of confirmation-gating.
    """
    if len(bars) < MIN_BARS:
        return []
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]
    closes = [float(b["c"]) for b in bars]
    last = closes[-1]

    k = min(12, max(3, len(closes) // 40))
    p_high = _pivots(highs, "high", k)
    p_low = _pivots(lows, "low", k)

    found: list[Pattern | None] = [
        _double(p_high, p_low, last, top=True),
        _double(p_high, p_low, last, top=False),
        _head_and_shoulders(p_high, p_low, last, top=True),
        _head_and_shoulders(p_high, p_low, last, top=False),
        _triangle(p_high, p_low, last, descending=True),
        _triangle(p_high, p_low, last, descending=False),
    ]
    out = [p for p in found if p is not None]

    # A break of the recent swing structure, which is the plainest signal there is
    # and the one most likely to matter to a position already on.
    recent_high = [v for _, v in p_high[-4:]]
    recent_low = [v for _, v in p_low[-4:]]
    if recent_high and last > max(recent_high):
        out.append(Pattern("swing breakout", BULLISH,
                           f"above the last highs at {max(recent_high):.2f}"))
    elif recent_low and last < min(recent_low):
        out.append(Pattern("swing breakdown", BEARISH,
                           f"below the last lows at {min(recent_low):.2f}"))

    # A coiling range is directionless and worth saying: it is the one read that
    # argues *for* a condor rather than against it.
    window = closes[-30:]
    if len(window) >= 15:
        mean = sum(window) / len(window)
        if mean and (max(window) - min(window)) / mean <= 0.015:
            out.append(Pattern("coiling range", NEUTRAL,
                               "under 1.5% of range over 30 sessions"))
    return out


def describe(patterns: list[Pattern]) -> str:
    """One line for the journal. Names, not prices — the levels go stale."""
    if not patterns:
        return "no confirmed patterns"
    return ", ".join(f"{p.name} ({p.side})" for p in patterns)
