"""Chart patterns on daily bars, and the exposure they are read against.

Live SPY, QQQ and IWM all returned "no confirmed patterns" on the day this was
written, which is the ordinary answer — confirmation-gating means most charts are
doing nothing nameable — and is also exactly what a detector that never fires
looks like. So every pattern here is built from a series that plainly contains it,
and every one is also shown *not* to fire before its confirmation arrives.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from halstreet.marketdata import patterns as P
from halstreet.marketdata.occ import Right, occ
from halstreet.strategy import exposure as E

EXPIRY = date(2026, 10, 16)
P760 = occ("SPY", EXPIRY, Right.PUT, Decimal(760))
P755 = occ("SPY", EXPIRY, Right.PUT, Decimal(755))
C780 = occ("SPY", EXPIRY, Right.CALL, Decimal(780))
C785 = occ("SPY", EXPIRY, Right.CALL, Decimal(785))


def bars(values: list[float]) -> list[dict]:
    """Daily bars whose high and low straddle each close by a hair.

    Tight, so a constructed shape is not accidentally widened into a different one
    by the synthetic range.
    """
    return [{"t": f"2026-01-{i:02d}", "o": v, "h": v * 1.001, "l": v * 0.999, "c": v}
            for i, v in enumerate(values, start=1)]


def ramp(a: float, b: float, n: int) -> list[float]:
    return [a + (b - a) * i / max(1, n - 1) for i in range(n)]


def flat(v: float, n: float) -> list[float]:
    # A hair of jitter, so pivot detection is not working on a perfectly equal run.
    return [v + (0.01 if i % 2 else -0.01) for i in range(int(n))]


# --- it fires ---------------------------------------------------------------------

def test_a_double_top_is_named_once_the_neckline_breaks():
    series = (flat(100, 30) + ramp(100, 120, 12) + ramp(120, 104, 12)
              + ramp(104, 119.5, 12) + ramp(119.5, 98, 14))
    found = {p.name: p for p in P.detect(bars(series))}
    assert "double top" in found
    assert found["double top"].side == P.BEARISH
    assert "confirmed below" in found["double top"].note


def test_a_double_top_is_not_named_before_the_neckline_breaks():
    """The gate that keeps this from being noise.

    Two highs close together is most of every chart. Until price breaks the low
    between them it is not a reversal, it is a shape.
    """
    series = (flat(100, 30) + ramp(100, 120, 12) + ramp(120, 104, 12)
              + ramp(104, 119.5, 12) + ramp(119.5, 112, 10))   # stops above the neck
    assert "double top" not in {p.name for p in P.detect(bars(series))}


def test_a_double_bottom_is_named_once_price_clears_the_neckline():
    series = (flat(100, 30) + ramp(100, 80, 12) + ramp(80, 96, 12)
              + ramp(96, 80.4, 12) + ramp(80.4, 103, 14))
    found = {p.name: p for p in P.detect(bars(series))}
    assert "double bottom" in found and found["double bottom"].side == P.BULLISH


def test_head_and_shoulders_needs_a_higher_head_and_even_shoulders():
    series = (flat(100, 30) + ramp(100, 112, 10) + ramp(112, 100, 10)
              + ramp(100, 126, 12) + ramp(126, 100, 12)
              + ramp(100, 112.5, 10) + ramp(112.5, 92, 12))
    found = {p.name for p in P.detect(bars(series))}
    assert "head and shoulders" in found


def test_uneven_shoulders_are_not_head_and_shoulders():
    """The head is still the highest point — only the shoulders are lopsided.

    An earlier version of this test put the right shoulder *above* the head, which
    fails the head check first and so never exercised symmetry at all: removing the
    tolerance entirely left the test green. Without it, any three swings that happen
    to peak in the middle get named, which is how a read becomes wallpaper.
    """
    # A real right shoulder — it has to be a swing, or the head check rejects the
    # series first and symmetry is never reached. This one is 7% below the left,
    # against a 3% tolerance.
    series = (flat(100, 30) + ramp(100, 112, 10) + ramp(112, 100, 10)
              + ramp(100, 140, 12) + ramp(140, 100, 12)
              + ramp(100, 104, 10) + ramp(104, 85, 14))
    found = P.detect(bars(series))
    assert "head and shoulders" not in {p.name for p in found}


def test_even_shoulders_with_a_higher_head_are_head_and_shoulders():
    # The positive half of the pair above, so the tolerance is shown to admit as
    # well as reject — a check that only ever rejects is indistinguishable from off.
    series = (flat(100, 30) + ramp(100, 112, 10) + ramp(112, 100, 10)
              + ramp(100, 140, 12) + ramp(140, 100, 12)
              + ramp(100, 113, 10) + ramp(113, 92, 12))
    assert "head and shoulders" in {p.name for p in P.detect(bars(series))}


def test_a_swing_breakout_is_named_when_price_clears_the_recent_highs():
    series = flat(100, 60) + ramp(100, 108, 20) + ramp(108, 101, 15) + ramp(101, 130, 20)
    found = {p.name: p for p in P.detect(bars(series))}
    assert "swing breakout" in found and found["swing breakout"].side == P.BULLISH


def test_a_coiling_range_is_neutral_and_says_so():
    """The one read that argues *for* a condor rather than against it."""
    found = {p.name: p for p in P.detect(bars(flat(100, 90)))}
    assert "coiling range" in found
    assert found["coiling range"].side == P.NEUTRAL


# --- it stays quiet ----------------------------------------------------------------

def test_a_short_series_says_nothing():
    # Forty bars is the floor. Pivots on a handful of points are arithmetic, not
    # structure.
    assert P.detect(bars(ramp(100, 130, 20))) == []
    assert P.detect([]) == []


def test_a_plain_uptrend_produces_no_reversal_pattern():
    found = {p.name for p in P.detect(bars(ramp(100, 160, 120)))}
    assert not found & {"double top", "double bottom", "head and shoulders",
                        "inverse head and shoulders"}


def test_nothing_is_named_twice():
    series = (flat(100, 30) + ramp(100, 120, 12) + ramp(120, 104, 12)
              + ramp(104, 119.5, 12) + ramp(119.5, 98, 14))
    names = [p.name for p in P.detect(bars(series))]
    assert len(names) == len(set(names))


def test_the_journal_line_names_patterns_without_prices():
    # Levels go stale the moment the tape moves; the names do not.
    line = P.describe([P.Pattern("double top", P.BEARISH, "confirmed below 104.00")])
    assert "double top (bearish)" in line and "104" not in line
    assert P.describe([]) == "no confirmed patterns"


# --- which way the position leans --------------------------------------------------

@pytest.mark.parametrize(("name", "legs", "want"), [
    ("put credit spread", {P760: -1, P755: 1}, E.BULLISH),
    ("call credit spread", {C780: -1, C785: 1}, E.BEARISH),
    ("iron condor", {P760: -1, P755: 1, C780: -1, C785: 1}, E.NEUTRAL),
    ("long call", {C780: 1}, E.BULLISH),
    ("long put", {P760: 1}, E.BEARISH),
    ("long straddle", {C780: 1, P760: 1}, E.NEUTRAL),
    ("nothing parseable", {"NOT-AN-OCC-SYMBOL": 1}, E.UNKNOWN),
    # The long verticals, added 2026-09-02. The short-leg rule got both backwards: a
    # call debit spread is short a call and is bullish, and the panel would have put
    # "WANTS SPY DOWN" on a position wanting exactly the opposite.
    ("call debit spread", {C780: 1, C785: -1}, E.BULLISH),
    ("put debit spread", {P760: 1, P755: -1}, E.BEARISH),
])
def test_exposure_is_a_property_of_the_structure_not_of_a_leg(name, legs, want):
    """HAL's version reads one leg, because HAL holds one instrument.

    Every structure here is a spread, and the per-leg reading gets all three wrong:
    a put credit spread is short a put and long a further put, which reads "bearish
    and bearish" leg by leg and is a bullish position. A condor is directionally
    neutral, which is not an answer any per-leg rule can produce at all.
    """
    assert E.exposure_of(legs) == want, name


def test_netting_the_legs_is_the_trap():
    """A put credit spread has *net zero* puts: short one, long another.

    The first version of `exposure_of` summed signed quantities per right and
    called every credit spread `unknown`. The direction lives in the short leg,
    which is also where the risk lives.
    """
    spread = {P760: -1, P755: 1}
    assert sum(spread.values()) == 0
    assert E.exposure_of(spread) == E.BULLISH


@pytest.mark.parametrize(("exposure", "side", "want"), [
    (E.BULLISH, P.BULLISH, True),
    (E.BULLISH, P.BEARISH, False),
    (E.BEARISH, P.BEARISH, True),
    (E.NEUTRAL, P.BEARISH, None),
    (E.BULLISH, P.NEUTRAL, None),
    (E.UNKNOWN, P.BULLISH, None),
])
def test_agreement_is_three_valued(exposure, side, want):
    # "No opinion" and "disagrees" are different facts and the badge shows them
    # differently. A directional pattern against a condor is not a warning.
    assert E.agrees(exposure, side) is want
