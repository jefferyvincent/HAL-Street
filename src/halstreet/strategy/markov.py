"""Whether direction on this name is sticky — and for how long that is even a question.

A credit structure is a bet that the tape does not do a particular thing for a number
of weeks. The desk had two reads bearing on that: a direction from the indicators, and
a volatility regime. Neither says anything about **persistence** — whether yesterday's
direction tells you anything about today's, on this name, right now. That is a
different fact, it is cheap to measure, and it is the one that separates "the trend is
up" from "the trend is up and trends on this name tend to continue".

A first-order chain over daily direction, three states: down, flat, up. The flat band
is a fraction of the name's own daily standard deviation rather than a fixed
percentage, because a quarter-percent day is nothing on a small cap and a move on an
index ETF — a fixed band would call one of them flat all year and the other never.

**The refusal is half the value.** On most tapes this chain forgets where it started
within two or three days, and past that horizon it has nothing the unconditional rate
does not already say. Asked about a forty-nine-day hold it must answer "this does not
reach that far" rather than producing a number, because a matrix that has mixed is a
coin flip wearing a transition matrix. `mixes_in_days` is that horizon and
`holds_for()` is the refusal.

`edge` is the whole read in one number: how much more often the current state repeats
than it occurs at all. Above one is sticky, below one is mean-reverting, and one is a
tape with no memory — which is the common and correct answer for most names on most
days.

Nothing here reaches a network or a clock. It is arithmetic over closes it was handed.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

DOWN, FLAT, UP = "down", "flat", "up"
STATES = (DOWN, FLAT, UP)

PERSISTENT, MEAN_REVERTING, MEMORYLESS = "persistent", "mean-reverting", "memoryless"

#: Closes needed before a transition matrix means anything. Nine cells to fill, and a
#: hundred observations is roughly eleven per cell — thin, and the floor rather than
#: the target.
MIN_CLOSES = 100

#: How far a day has to move to count as a direction, in standard deviations of this
#: name's own daily returns. A quarter of a sigma: small enough that real days are
#: directional, large enough that noise is not.
FLAT_BAND_SIGMAS = 0.25

#: How many standard errors the repeat rate must clear its base rate by before this
#: calls it a finding.
#:
#: Not a fixed edge. The first version used a flat 6% and promptly labelled a tape
#: built from a seeded random walk as `persistent` at edge 1.145 — which is a shade
#: over one and a half standard errors on that sample, i.e. exactly what noise looks
#: like. A threshold that does not scale with the sample size is a threshold that
#: reports the sample size.
EDGE_SIGMAS = 2.0

#: Total-variation distance at which the chain has forgotten where it started.
MIXED_WITHIN = 0.02

#: Days to look ahead for before giving up. Well past any horizon a daily chain
#: survives; it is a loop bound, not a claim.
MAX_HORIZON = 60


@dataclass(frozen=True)
class Persistence:
    """What the tape's own history says about whether direction continues."""

    #: Today's state, which is what everything below is conditioned on.
    current: str
    matrix: dict[str, dict[str, float]]
    #: P(current state repeats tomorrow | today is the current state).
    repeats: float
    #: How often the current state occurs at all, ignoring what came before it.
    base_rate: float
    #: repeats / base_rate. >1 sticky, <1 mean-reverting, ~1 no memory.
    edge: float
    label: str
    #: Days until the chain forgets where it started. Past this it adds nothing.
    mixes_in_days: int
    #: False when it never forgot inside the window we looked. A periodic chain — a
    #: tape that alternates exactly — never mixes at all, and `mixes_in_days` is then
    #: the edge of the search rather than a finding.
    mixed: bool
    samples: int

    def holds_for(self, days: int) -> bool:
        """Whether this read says anything at all about a hold of that length.

        The question `run_cycle` should be asking before it quotes any of this at a
        forty-nine-day structure, and the answer is usually no. That is not a failure
        of the measurement; it is the measurement.
        """
        return not self.mixed or days <= self.mixes_in_days

    def describe(self) -> str:
        return (f"{self.label} — {self.current} days repeat {self.repeats * 100:.0f}% "
                f"of the time against a {self.base_rate * 100:.0f}% base rate, "
                f"informative for {'at least ' if not self.mixed else ''}"
                f"{self.mixes_in_days} day(s), "
                f"over {self.samples} daily observations")

    def to_prompt(self) -> dict:
        return {
            "current_state": self.current,
            "repeats_pct": round(self.repeats * 100, 1),
            "base_rate_pct": round(self.base_rate * 100, 1),
            "edge": round(self.edge, 3),
            "label": self.label,
            "informative_for_days": self.mixes_in_days,
            "mixed_within_window": self.mixed,
            "samples": self.samples,
            "note": ("first-order daily chain; beyond informative_for_days it says "
                     "nothing the base rate does not"),
        }


def build(closes: list[float]) -> Persistence | None:
    """Read persistence off a series of closes, or None where there is nothing to read.

    None rather than a neutral-looking default: a `memoryless` label is a measured
    finding and must not be confused with not having measured.
    """
    states = classify(closes)
    if states is None:
        return None

    matrix = transitions(states)
    current = states[-1]
    row = matrix.get(current, {})
    repeats = row.get(current, 0.0)
    base_rate = states.count(current) / len(states)
    if base_rate <= 0:
        return None

    edge = repeats / base_rate
    # Measured against the noise floor for *this* sample rather than a fixed gap.
    # `from_current` is how many days the chain was actually in this state, which is
    # the n behind the repeat rate.
    from_current = max(1, states.count(current) - 1)
    noise = math.sqrt(max(base_rate * (1 - base_rate), 0.0) / from_current)
    threshold = EDGE_SIGMAS * noise
    label = (PERSISTENT if repeats - base_rate > threshold
             else MEAN_REVERTING if base_rate - repeats > threshold
             else MEMORYLESS)

    mixes, mixed = mixing_days(matrix, current)
    return Persistence(current=current, matrix=matrix, repeats=repeats,
                       base_rate=base_rate, edge=edge, label=label,
                       mixes_in_days=mixes, mixed=mixed, samples=len(states))


def classify(closes: list[float]) -> list[str] | None:
    """One state per day, or None when the series cannot carry states.

    A tape that never moves has no directional state to be sticky in, and inventing
    one would put a lean on a chart that did nothing.
    """
    if not closes or len(closes) < MIN_CLOSES:
        return None
    returns = [math.log(b / a) for a, b in itertools.pairwise(closes)
               if a > 0 and b > 0]
    if len(returns) < MIN_CLOSES - 1:
        return None

    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    band = math.sqrt(variance) * FLAT_BAND_SIGMAS
    if band <= 0:
        return None

    states = [UP if r > band else DOWN if r < -band else FLAT for r in returns]
    return states if len({*states}) > 1 else None


def transitions(states: list[str]) -> dict[str, dict[str, float]]:
    """The chain, as row-stochastic probabilities.

    A state never observed gets the uniform row rather than an empty one. It is the
    honest stand-in — nothing was learned about it — and it keeps every row summing to
    one so the powers below stay probabilities.
    """
    counts = {a: dict.fromkeys(STATES, 0) for a in STATES}
    for a, b in itertools.pairwise(states):
        counts[a][b] += 1

    matrix: dict[str, dict[str, float]] = {}
    for state, row in counts.items():
        total = sum(row.values())
        matrix[state] = ({k: v / total for k, v in row.items()} if total
                         else dict.fromkeys(STATES, 1 / len(STATES)))
    return matrix


def mixing_days(matrix: dict[str, dict[str, float]], start: str) -> tuple[int, bool]:
    """Days until knowing today's state stops changing the answer.

    Walked forward one step at a time rather than solved for, because the thing being
    compared against — the chain's own stationary distribution — is easiest to get by
    walking it far enough that it stops moving. Both walks use the same matrix, so an
    error in it cancels rather than accumulating.
    """
    stationary = _walk({s: 1 / len(STATES) for s in STATES}, matrix, MAX_HORIZON)
    here = {s: 1.0 if s == start else 0.0 for s in STATES}
    for day in range(1, MAX_HORIZON + 1):
        here = _step(here, matrix)
        if _distance(here, stationary) < MIXED_WITHIN:
            return day, True
    # Never forgot inside the window. A chain that alternates exactly is periodic and
    # never mixes at all — today's state predicts every day after it, forever — so the
    # honest answer is "at least this long", not "this long".
    return MAX_HORIZON, False


def _step(distribution: dict[str, float],
          matrix: dict[str, dict[str, float]]) -> dict[str, float]:
    return {b: sum(distribution[a] * matrix[a][b] for a in STATES) for b in STATES}


def _walk(distribution: dict[str, float], matrix: dict[str, dict[str, float]],
          steps: int) -> dict[str, float]:
    for _ in range(steps):
        distribution = _step(distribution, matrix)
    return distribution


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Total variation: half the sum of absolute differences."""
    return sum(abs(a[s] - b[s]) for s in STATES) / 2
