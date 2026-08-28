"""What a structure is actually worth, sampled rather than assumed.

`pop.py` answers "how often does this finish profitable" analytically and exactly, and
that is the right tool for that question. It is not the question the desk keeps asking.
Every decline this week has been about the *shape*: "$16 max gain against ~$15
round-trip friction", "a 1:11 reward/risk that only works if SPY does nothing for 49
days". Those are claims about expectation and about the size of the tail, and the agent
was reaching them in prose because nothing computed them.

Simulation rather than more closed form because the awkward part is not the
probability, it is the average — the mean of a piecewise-linear payoff over a lognormal
minus a fixed cost is far easier to sample than to derive for each structure this agent
can build.

**What it assumes, all of which is wrong in a knowable direction.** Geometric Brownian
motion, terminal price only, expiry-held. The horizon and the drift are imported from
`blackscholes` rather than restated, because this has to agree with `pop.py` on the one
number they both compute — and a year that is 365 days here and 252 there would make
them disagree by five points of probability while both looked right. A test pins the
agreement. Realized volatility, not
implied — the same proxy `regime.py` is explicit about, and it matters more here: a
structure is *priced* on implied vol, so simulating it on realized vol prices the trade
against a different market from the one that quoted it. When realized sits below
implied, which is the usual case for index options, this flatters a short-premium
structure. `note` says so, and every figure it returns carries it.

**It also ignores how the book is actually run.** The manager takes profit at 50% and
stops out at 200%, so nothing here is held to expiry in practice. That makes these
figures conservative on the win rate and wrong in both directions on the tail. Same
caveat `pop.py` states, for the same reason, and it is stated rather than quietly
assumed.

**Deterministic on purpose.** Seeded from the caller, never from the clock, because
these numbers go in an append-only journal: a record that cannot be reproduced is not
a record, and a reader comparing two entries should be comparing the structures rather
than the weather in a random number generator.

Nothing here reaches a network, a clock, or a broker. It is arithmetic over numbers it
was handed, which is what makes it testable against `pop.py`'s exact answer.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from decimal import Decimal

from halstreet.marketdata.occ import PayoffLeg, payoff
from halstreet.strategy.blackscholes import DAYS_PER_YEAR, RISK_FREE_RATE

#: Paths per structure. Enough that the second decimal of a probability is stable
#: across seeds — the test pins that — and cheap enough to run for every candidate on
#: every menu: a few milliseconds of arithmetic beside two network calls.
PATHS = 20_000

#: A contract is a hundred shares. Every figure below is dollars per structure.
MULTIPLIER = 100

#: How close to the worst case counts as *the* worst case. Sampling lands a hair inside
#: it, and a tail probability of zero for a structure that plainly can lose everything
#: would be the most misleading number on the page.
MAX_LOSS_TOLERANCE = Decimal("0.01")

_NOTE = ("simulated to expiry on realized vol, risk-neutral drift — "
         "priced against a different volatility from the one that quoted it")


@dataclass(frozen=True)
class Scenario:
    """One structure's distribution of outcomes, in dollars per structure."""

    paths: int
    #: Fraction of paths finishing above water *after* friction.
    p_profit: float
    p_loss: float
    #: Fraction finishing at (or within a cent of) the defined maximum loss.
    p_max_loss: float
    ev_usd: Decimal
    p10_usd: Decimal
    p50_usd: Decimal
    p90_usd: Decimal
    worst_usd: Decimal
    best_usd: Decimal
    #: The volatility this was priced on, so a reader can see what it assumed.
    vol: float
    note: str = _NOTE

    def to_prompt(self) -> dict:
        """The shape handed to the model and written to the journal."""
        return {
            "paths": self.paths,
            "p_profit": round(self.p_profit, 4),
            "p_max_loss": round(self.p_max_loss, 4),
            "ev_usd": str(self.ev_usd),
            "p10_usd": str(self.p10_usd),
            "p50_usd": str(self.p50_usd),
            "p90_usd": str(self.p90_usd),
            "vol": round(self.vol, 4),
            "note": self.note,
        }


def simulate(*, legs: list[PayoffLeg], net: Decimal, spot: Decimal, dte: int,
             vol: float | None, friction_usd: Decimal, seed: int,
             paths: int = PATHS) -> Scenario | None:
    """Sample a structure's P&L at expiry, or None where it cannot honestly be sampled.

    `None` rather than a default for a missing volatility. A structure simulated at a
    made-up twenty percent is a confident number about a market nobody measured, and
    this is the place where that would do the most damage — it would arrive on the
    menu looking exactly like a measured one.
    """
    if not legs or vol is None or vol < 0 or spot <= 0:
        return None

    # Per share, and signed the way the rest of the codebase signs a structure: `net`
    # is what it costs to open, so a credit is negative and -net is money received.
    entry = -net
    # The same year and the same drift `pop.py` prices with, imported rather than
    # restated. Volatility is annualized on 252 trading days by `regime`; the horizon
    # is calendar, because a contract expires on a date rather than after a number of
    # sessions. Those two conventions are both correct and are not the same number.
    years = max(0, dte) / DAYS_PER_YEAR
    drift = (RISK_FREE_RATE - 0.5 * vol * vol) * years
    shock = vol * math.sqrt(years)
    rng = random.Random(seed)  # noqa: S311 - sampling a distribution, not a secret

    results: list[Decimal] = []
    for _ in range(paths):
        # Lognormal terminal price. `shock` is zero for a motionless tape or an expiry
        # today, and both then collapse to the one path that already exists.
        terminal = Decimal(str(float(spot) * math.exp(drift + shock * rng.gauss(0, 1))))
        # payoff() is the structure's value at expiry; opening cost is already in
        # `entry`, so what is left is the round trip.
        results.append((payoff(legs, terminal) + entry) * MULTIPLIER - friction_usd)

    results.sort()
    floor = results[0]
    wins = sum(1 for r in results if r > 0)
    at_floor = sum(1 for r in results if r - floor <= MAX_LOSS_TOLERANCE)

    return Scenario(
        paths=paths,
        p_profit=wins / paths,
        p_loss=sum(1 for r in results if r < 0) / paths,
        p_max_loss=at_floor / paths,
        ev_usd=_cents(sum(results, Decimal(0)) / paths),
        p10_usd=_cents(results[paths // 10]),
        p50_usd=_cents(results[paths // 2]),
        p90_usd=_cents(results[(paths * 9) // 10]),
        worst_usd=_cents(floor),
        best_usd=_cents(results[-1]),
        vol=vol,
    )


def _cents(value: Decimal) -> Decimal:
    """Money leaves as money. The sampling is float; what it hands back is not."""
    return value.quantize(Decimal("0.01"))
