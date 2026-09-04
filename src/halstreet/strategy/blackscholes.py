"""Black-Scholes probabilities, for ranking only.

Ported from TradeScans' `black-scholes.ts`. Everything here answers one question —
*where is the underlying likely to be at expiry?* — which is what turns a menu of
structures into a ranked menu.

**This never prices an order.** Prices come from the chain: we sell at the bid and
buy at the ask, because that is what fills. A model price is used to compare
candidates against each other and for nothing else. If a number here ever reaches a
limit price, that is a bug.

Two deliberate departures from the TypeScript:

*`math.erf` replaces the Abramowitz & Stegun polynomial.* TradeScans hand-rolled the
error function because JavaScript has none; its maximum error is ~1.5e-7. Python's
is correctly rounded, so the approximation would be strictly worse for no reason.

*The year is 365 days, and the constant says so.* The TypeScript called this
`TRADING_DAYS_PER_YEAR = 365`, which is a misnomer with a correct value — option
time-to-expiry is calendar time (an option decays over a weekend), not trading time.
The value was right; only the name was wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Calendar days, not trading days — see the module docstring.
DAYS_PER_YEAR = 365.0

# Roughly the front-end T-bill through the period this was built. It moves the
# probabilities by a fraction of a percent at 45 DTE, which is far below the noise in
# the volatility estimate it sits beside; it is here for correctness, not precision.
RISK_FREE_RATE = 0.045


def norm_cdf(x: float) -> float:
    """P(Z <= x) for a standard normal."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@dataclass(frozen=True)
class Coefficients:
    d1: float
    d2: float
    years: float


def coefficients(spot: float, strike: float, dte: float, vol: float, *,
                 rate: float = RISK_FREE_RATE, dividend: float = 0.0) -> Coefficients | None:
    """d1/d2, or None when the inputs cannot describe a real option.

    Returns None rather than raising, and rather than substituting a default
    volatility. A candidate we cannot compute a probability for should score as
    unknown and be handled by the caller — quietly assuming 30% vol would produce a
    confident-looking number with nothing behind it.
    """
    if spot <= 0 or strike <= 0 or dte <= 0 or vol <= 0:
        return None
    years = dte / DAYS_PER_YEAR
    sigma_sqrt_t = vol * math.sqrt(years)
    if sigma_sqrt_t == 0:
        return None
    d1 = (
        math.log(spot / strike) + (rate - dividend + vol * vol / 2.0) * years
    ) / sigma_sqrt_t
    return Coefficients(d1=d1, d2=d1 - sigma_sqrt_t, years=years)


def prob_above(spot: float, strike: float, dte: float, vol: float,
               *, rate: float = RISK_FREE_RATE) -> float | None:
    """Risk-neutral P(S_T > strike). None when it cannot be computed."""
    c = coefficients(spot, strike, dte, vol, rate=rate)
    return None if c is None else norm_cdf(c.d2)


def prob_below(spot: float, strike: float, dte: float, vol: float,
               *, rate: float = RISK_FREE_RATE) -> float | None:
    c = coefficients(spot, strike, dte, vol, rate=rate)
    return None if c is None else norm_cdf(-c.d2)


def prob_between(spot: float, lower: float, upper: float, dte: float, vol: float,
                 *, rate: float = RISK_FREE_RATE) -> float | None:
    """P(lower < S_T < upper) — the iron condor's whole thesis in one number."""
    if lower >= upper:
        return None
    below_upper = prob_below(spot, upper, dte, vol, rate=rate)
    below_lower = prob_below(spot, lower, dte, vol, rate=rate)
    if below_upper is None or below_lower is None:
        return None
    return max(0.0, below_upper - below_lower)
