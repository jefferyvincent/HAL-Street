"""OCC option symbols, and the expiry payoff maths the gates reason over.

Ported from HAL's `sensory/alpaca_data.py` (occ_root, parse_occ), which had already
been beaten into shape against real Alpaca symbols, plus the payoff arithmetic the
defined-risk gate needs.

An OCC symbol is fixed-width: root, then YYMMDD, then C or P, then the strike in
thousandths on 8 digits. `SPY261016C00765000` is a SPY 16-Oct-2026 765 call. The root
is whatever precedes those 15 characters, so it varies in length and cannot be found
by counting from the left.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from halstreet import clock

_OCC_TAIL = re.compile(r"^(\d{6})([CP])(\d{8})$")
_TAIL_LEN = 15
CONTRACT_MULTIPLIER = 100


class Right(str, Enum):
    CALL = "C"
    PUT = "P"


@dataclass(frozen=True)
class Contract:
    """One option contract, parsed from its OCC symbol."""

    symbol: str
    root: str
    expiry: date
    right: Right
    strike: Decimal

    def dte(self, asof: date | None = None) -> int:
        """Calendar days to expiry. Negative once expired."""
        return (self.expiry - (asof or clock.today())).days


def parse(symbol: str) -> Contract | None:
    """Parse an OCC symbol, or None if it is not one.

    Returns None rather than raising: callers routinely pass a mix of option and
    equity symbols, and "this is not an option" is an ordinary answer, not an error.
    """
    s = (symbol or "").strip().upper()
    if len(s) <= _TAIL_LEN:
        return None
    root, tail = s[:-_TAIL_LEN], s[-_TAIL_LEN:]
    m = _OCC_TAIL.match(tail)
    if not root or not m:
        return None
    ymd, right, strike = m.groups()
    try:
        expiry = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return Contract(s, root, expiry, Right(right), Decimal(strike) / 1000)


def root(symbol: str) -> str:
    """Underlying root for a holding.

    Option positions are OCC symbols; equity positions are already the ticker. A
    plain ticker comes back unchanged so callers can pass either — concentration
    gates depend on this, because five strikes on one name must bucket as one name.
    """
    parsed = parse(symbol)
    return parsed.root if parsed else (symbol or "").strip().upper()


def occ(root_: str, expiry: date, right: Right | str, strike: Decimal) -> str:
    """Build an OCC symbol. Inverse of `parse`."""
    r = right.value if isinstance(right, Right) else str(right).upper()[:1]
    return f"{root_.upper()}{expiry:%y%m%d}{r}{int(Decimal(strike) * 1000):08d}"


# --- expiry payoff ------------------------------------------------------------
#
# Everything the defined-risk gate concludes comes from the payoff of the structure
# at expiry as a function of the underlying price. Working from payoff rather than
# from a list of recognised strategy names means an unnamed or malformed structure
# is still judged correctly — a gate that only knows "iron condor" and "vertical"
# would wave through anything it could not classify, which is precisely backwards.


@dataclass(frozen=True)
class PayoffLeg:
    """A leg reduced to what expiry payoff depends on."""

    right: Right
    strike: Decimal
    ratio: int
    long: bool


def intrinsic(leg: PayoffLeg, spot: Decimal) -> Decimal:
    """Value of one contract's worth of this leg at expiry, per share, signed."""
    if leg.right is Right.CALL:
        value = max(spot - leg.strike, Decimal(0))
    else:
        value = max(leg.strike - spot, Decimal(0))
    return value * leg.ratio * (1 if leg.long else -1)


def payoff(legs: list[PayoffLeg], spot: Decimal) -> Decimal:
    """Structure value at expiry, per share, before premium."""
    return sum((intrinsic(leg, spot) for leg in legs), Decimal(0))


def net_call_ratio(legs: list[PayoffLeg]) -> int:
    """Long minus short call ratio.

    Negative means net short calls, which is the one genuinely unbounded exposure in
    an options-only structure: as the underlying rises without limit so does the
    loss. Short puts are bounded — the underlying stops at zero — so a naked put is
    a max-loss problem, not a defined-risk one, and is judged by the size gate
    instead of this one.
    """
    return sum(leg.ratio * (1 if leg.long else -1) for leg in legs if leg.right is Right.CALL)


def breakpoints(legs: list[PayoffLeg]) -> list[Decimal]:
    """Prices worth evaluating: zero, every strike, and one beyond the highest.

    The expiry payoff is piecewise linear with kinks only at strikes, so its minimum
    over any bounded region is attained at one of these points. Checking them is
    exact, not a sample.
    """
    strikes = sorted({leg.strike for leg in legs})
    if not strikes:
        return [Decimal(0)]
    return [Decimal(0), *strikes, strikes[-1] * 2]
