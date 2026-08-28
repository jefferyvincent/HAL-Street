"""Market structure: where price actually broke, and which way.

The indicators the bias votes on — moving averages, RSI, MACD — are all averages of
closes. They agree with each other by construction and they say nothing about *levels*:
a 20-EMA above a 50-EMA is the same vote whether price just took out a three-month high
or is drifting in the middle of a range.

Break of structure is the other kind of evidence. It is a fact about a specific price
being exceeded, it is confirmation-gated the same way `patterns.py` is — an unbroken
level is not a break — and it disagrees with the moving averages often enough to be
worth a vote.

What it must never do is reach an exit. That line is `test_smc_cannot_reach_an_exit`
and it is the same line `patterns.py` draws, for the same reason.
"""

from __future__ import annotations

import pytest

from halstreet.marketdata import smc


def bars(highs, lows, closes=None):
    if closes is None:
        closes = [(h + low) / 2 for h, low in zip(highs, lows, strict=True)]
    return [{"h": h, "l": low, "c": c, "o": c}
            for h, low, c in zip(highs, lows, closes, strict=True)]


def rising_then_break(n: int = 60):
    """A range, then a close above its high. The textbook bullish break."""
    highs = [100.0 + (i % 5) for i in range(n)]
    lows = [95.0 + (i % 5) for i in range(n)]
    closes = [98.0] * n
    highs[-1], closes[-1] = 120.0, 119.0      # decisively through the range top
    return bars(highs, lows, closes)


def falling_then_break(n: int = 60):
    highs = [100.0 + (i % 5) for i in range(n)]
    lows = [95.0 + (i % 5) for i in range(n)]
    closes = [98.0] * n
    lows[-1], closes[-1] = 80.0, 81.0
    return bars(highs, lows, closes)


def flat(n: int = 60):
    return bars([100.0] * n, [99.0] * n, [99.5] * n)


# --- the read ------------------------------------------------------------------------

def test_a_close_above_the_last_swing_high_is_a_bullish_break():
    read = smc.read(rising_then_break())
    assert read is not None
    assert read.direction == smc.BULLISH
    assert read.event == smc.BOS


def test_a_close_below_the_last_swing_low_is_a_bearish_break():
    read = smc.read(falling_then_break())
    assert read is not None
    assert read.direction == smc.BEARISH


def test_a_range_that_never_broke_is_not_a_break():
    """The confirmation gate, and most of the value. A level that has held is not a
    signal about anything; flagging it would make the read always lit."""
    read = smc.read(flat())
    assert read is None or read.event is None


def test_the_level_that_broke_is_named():
    """"Bullish" is an opinion. "Closed above 104, the range high since June" is a
    fact somebody can check against a chart."""
    read = smc.read(rising_then_break())
    assert read.level is not None
    assert 100.0 <= read.level <= 110.0


def test_too_little_history_is_no_read():
    assert smc.read(bars([100.0] * 5, [99.0] * 5)) is None


@pytest.mark.parametrize("junk", [[], [{}], [{"h": None, "l": None, "c": None}] * 60])
def test_a_bar_series_it_cannot_read_is_no_read_rather_than_a_crash(junk):
    """This runs once per underlying per cycle, inside the read that feeds the model."""
    assert smc.read(junk) is None


# --- the vote ---------------------------------------------------------------------------

def test_a_break_votes_with_the_other_indicators():
    """One vote among several, weighted like the rest. Not an override: structure and
    the moving averages disagree often, and the margin is what resolves that."""
    from halstreet.strategy import bias as bias_mod

    closes = [100.0] * 200
    plain = bias_mod.for_symbol("X", 100.0, closes)
    with_break = bias_mod.for_symbol("X", 100.0, closes,
                                     structure=smc.read(rising_then_break()))
    assert with_break.bullish == plain.bullish + 1
    assert any("structure" in r.lower() for r in with_break.reasons)


def test_no_structure_read_changes_no_vote():
    """Absent evidence is not evidence. A symbol whose bars would not parse must score
    exactly as it did before this existed."""
    from halstreet.strategy import bias as bias_mod

    closes = [100.0 + i * 0.1 for i in range(200)]
    assert (bias_mod.for_symbol("X", 120.0, closes).direction
            == bias_mod.for_symbol("X", 120.0, closes, structure=None).direction)


# --- the line it must not cross -----------------------------------------------------

def test_smc_cannot_reach_an_exit():
    """The same rule `patterns.py` lives under, and the reason is unchanged: exits are
    the one path with neither a model call nor a gate, deliberately, because a position
    that cannot be closed is how defined risk stops being defined.

    Structure may vote on what gets *proposed*. It may not decide what gets *closed*.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "halstreet"
    for module in (src / "agent" / "cerebellum" / "manager.py",
                   src / "gates" / "base.py",
                   src / "gates" / "portfolio.py",
                   src / "gates" / "circuit.py",
                   src / "gates" / "defined_risk.py"):
        tree = ast.parse(module.read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
        assert not any("smc" in n for n in names), f"{module.name} imports smc"
