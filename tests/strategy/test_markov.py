"""Whether direction on this name is sticky, and for how long that is even a question.

A credit spread is a bet that the tape does not do a particular thing for a number of
weeks. The desk had two reads bearing on that — a direction from the indicators and a
volatility regime — and neither says anything about *persistence*: whether yesterday's
direction tells you anything about today's on this name, right now.

The interesting half is the refusal. A first-order chain over daily direction forgets
the current state within a few days on most tapes, and beyond that horizon it has
nothing to add that the base rate does not already say. A module that answered anyway
would be dressing a coin flip in a transition matrix.
"""

from __future__ import annotations

import pytest

from halstreet.strategy import markov


#: Long enough to clear the minimum. The shapes matter, not the levels.
def alternating(n: int = 200) -> list[float]:
    """Up, down, up, down. Perfect mean reversion."""
    out, price = [100.0], 100.0
    for i in range(n):
        price *= 1.02 if i % 2 == 0 else (1 / 1.02)
        out.append(price)
    return out


def sticky(n: int = 400) -> list[float]:
    """A tape where today's move follows yesterday's.

    Autocorrelation, not drift. A series that simply rises every day has a high base
    rate for `up` and repeats it at exactly that rate — which is bias, not
    persistence, and the module is right to call it memoryless. Persistence is the
    *conditional* rate beating the unconditional one, so the process has to carry a
    memory: r(t) = 0.6 r(t-1) + noise.
    """
    import random
    rng = random.Random(3)  # noqa: S311 - a fixture, not a secret
    out, price, last = [100.0], 100.0, 0.0
    for _ in range(n):
        last = 0.6 * last + rng.gauss(0, 0.008)
        price *= 1 + last
        out.append(price)
    return out


def coin(n: int = 400) -> list[float]:
    """A tape with no memory, from a fixed seed so the assertion is stable."""
    import random
    rng = random.Random(11)  # noqa: S311 - a fixture, not a secret
    out, price = [100.0], 100.0
    for _ in range(n):
        price *= 1 + rng.gauss(0, 0.012)
        out.append(price)
    return out


# --- the two shapes it has to tell apart ----------------------------------------------

def test_a_tape_that_alternates_reads_as_mean_reverting():
    read = markov.build(alternating())
    assert read is not None
    assert read.label == markov.MEAN_REVERTING
    assert read.edge < 1


def test_a_tape_whose_moves_follow_yesterdays_reads_as_persistent():
    read = markov.build(sticky())
    assert read is not None
    assert read.label == markov.PERSISTENT
    assert read.edge > 1


def test_a_tape_with_no_memory_reads_as_neither():
    """The common and correct answer. Most days on most names tell you nothing."""
    read = markov.build(coin())
    assert read is not None
    assert read.label == markov.MEMORYLESS


# --- the refusal ------------------------------------------------------------------------

def test_a_memoryless_tape_stops_being_informative_within_days():
    """A chain that has forgotten where it started is a base rate wearing a matrix."""
    read = markov.build(coin())
    assert read.mixed is True
    assert read.mixes_in_days <= 5


def test_a_tape_that_alternates_exactly_never_forgets_and_says_so():
    """A periodic chain does not mix at all — today's state predicts every day after
    it, forever. Reporting the edge of the search as if it were a finding would be a
    number about our loop bound rather than about the tape."""
    read = markov.build(alternating())
    assert read.mixed is False
    assert read.holds_for(49) is True


def test_noise_is_not_reported_as_a_finding():
    """The bug the first version shipped with: a flat 6% edge threshold labelled a
    seeded random walk `persistent` at 1.145, which is a shade over one and a half
    standard errors on that sample. A threshold that does not scale with the sample
    size is a threshold that reports the sample size."""
    assert markov.build(coin()).label == markov.MEMORYLESS


def test_it_will_not_answer_past_the_horizon_it_just_named():
    """The point of computing the horizon at all. Asked about a 49-day hold, a daily
    chain has nothing the unconditional rate does not already say, and saying so is
    the whole contribution."""
    read = markov.build(coin())
    assert read.holds_for(49) is False
    assert read.holds_for(1) is True


def test_too_little_history_is_no_read_rather_than_a_confident_one():
    assert markov.build([100.0, 101.0, 102.0]) is None


def test_a_flat_tape_is_not_a_direction():
    """Every return inside the band. There is no directional state to be sticky in,
    and inventing one would put a lean on a chart that never moved."""
    assert markov.build([100.0] * 200) is None


# --- the arithmetic ---------------------------------------------------------------------

def test_the_rows_of_the_matrix_are_probabilities():
    read = markov.build(coin())
    for row in read.matrix.values():
        assert abs(sum(row.values()) - 1.0) < 1e-9


def test_the_band_scales_with_the_name_rather_than_being_a_fixed_percentage():
    """A quarter-percent day is nothing on a meme stock and a move on an index ETF.
    A fixed band would call one of them flat all year and the other never."""
    calm = markov.build([100.0 * (1 + 0.001 * (1 if i % 2 else -1)) ** i
                         for i in range(200)])
    assert calm is not None, "a quiet tape still has states, measured against itself"


def test_the_same_history_always_reads_the_same():
    """It is journalled. A read nobody can reproduce is not a read."""
    assert markov.build(coin()).edge == markov.build(coin()).edge


def test_it_says_what_it_measured_over():
    read = markov.build(coin())
    assert read.samples > 100
    assert "day" in read.describe().lower()


@pytest.mark.parametrize("bad", [[], [100.0], None])
def test_rubbish_in_is_no_read_rather_than_a_crash(bad):
    """This runs once per underlying per cycle, inside the read that feeds the model."""
    assert markov.build(bad or []) is None


# --- reaching the cycle ---------------------------------------------------------------

def test_the_cycle_reads_persistence_off_the_bars_it_already_fetched():
    """Free: the closes were fetched for the bias and the regime. A second call to the
    broker for the same series would be a network round trip to learn nothing new."""
    import inspect

    from halstreet.agent.cerebellum import loop
    source = inspect.getsource(loop.Agent.snapshot)
    assert "markov_mod.build(closes)" in source
    assert source.count("get_daily_bars") == 1, "one fetch, three reads off it"


def test_the_committee_is_told_what_the_chain_found():
    """The read exists to qualify a direction, and the catalyst is where a direction
    gets argued about. Computed and not shown is computed and not used."""
    import inspect

    from halstreet.agent.cerebellum import loop
    assert "persistence" in inspect.getsource(loop.Agent._committee_proposal)


def test_a_read_that_does_not_reach_the_holding_period_is_not_quoted_as_if_it_did():
    """The refusal, at the one place it matters. A 49-day structure cannot be argued
    on a chain that forgot where it started on day three."""
    read = markov.build(coin())
    assert read.holds_for(49) is False
