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

from halstreet.marketdata.occ import CONTRACT_MULTIPLIER, PayoffLeg, payoff
from halstreet.strategy.blackscholes import DAYS_PER_YEAR, RISK_FREE_RATE

#: Paths per structure. Enough that the second decimal of a probability is stable
#: across seeds — the test pins that — and cheap enough to run for every candidate on
#: every menu: a few milliseconds of arithmetic beside two network calls.
PATHS = 20_000

#: How close to the worst case counts as *the* worst case. Sampling lands a hair inside
#: it, and a tail probability of zero for a structure that plainly can lose everything
#: would be the most misleading number on the page.
MAX_LOSS_TOLERANCE = Decimal("0.01")

_NOTE = ("simulated to expiry, risk-neutral drift; friction_usd is already deducted "
         "from every figure here — do not subtract it again")


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
    #: Round-trip cost already deducted from every figure above. Carried because a
    #: reader who cannot see it deducts it again — a live judge did exactly that,
    #: taking an EV of $13.80 down to "roughly $2" with a cost already inside it.
    friction_usd: Decimal = Decimal(0)
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
            "friction_usd": str(self.friction_usd),
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
        results.append((payoff(legs, terminal) + entry) * CONTRACT_MULTIPLIER - friction_usd)

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
        friction_usd=friction_usd,
    )


def _cents(value: Decimal) -> Decimal:
    """Money leaves as money. The sampling is float; what it hands back is not."""
    return value.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class Outlook:
    """One structure, priced at the market's volatility and at the tape's.

    The distinction became load-bearing the moment a judge reasoned from it. On a live
    NVDA menu every structure printed negative EV and the judge concluded that realized
    vol was running above the implied vol that quoted the credits, so short premium was
    the wrong side of that gap whatever the strikes. Sound reasoning — resting on a
    number that had only ever seen one of the two volatilities.

    A structure is *priced* at implied and *simulated* at realized. One EV silently
    asserts that the tape's trailing behaviour is the better forecast of the next seven
    weeks. Sometimes it is. When the two disagree, that disagreement is not noise to be
    resolved by picking a side — it is the trade thesis, and it belongs on the page
    where the judge can argue about it.
    """

    #: Priced at the short leg's own implied volatility — what the market charged.
    at_implied: Scenario | None
    #: Priced at trailing realized volatility — what the tape has actually done.
    at_realized: Scenario | None

    @property
    def agree(self) -> bool | None:
        """Whether both volatilities reach the same verdict. None with only one read.

        Agreement is a conclusion a reader can stop at. Disagreement is the question.
        """
        if self.at_implied is None or self.at_realized is None:
            return None
        return (self.at_implied.ev_usd >= 0) == (self.at_realized.ev_usd >= 0)

    def to_prompt(self) -> dict:
        return {
            "at_implied": None if self.at_implied is None else self.at_implied.to_prompt(),
            "at_realized": None if self.at_realized is None else self.at_realized.to_prompt(),
            "agree": self.agree,
            "note": ("the same structure at the volatility the market charged and at "
                     "the one the tape has run; where they disagree, the trade is a "
                     "bet on which is the better forecast"),
        }


def outlook(*, legs: list[PayoffLeg], net: Decimal, spot: Decimal, dte: int,
            vol_realized: float | None, vol_implied: float | None,
            friction_usd: Decimal, seed: int, paths: int = PATHS) -> Outlook:
    """The same structure sampled at both volatilities. Either may be missing.

    A chain without IV is common enough that losing the realized read alongside it
    would trade a partial answer for none.
    """
    def at(vol: float | None) -> Scenario | None:
        return simulate(legs=legs, net=net, spot=spot, dte=dte, vol=vol,
                        friction_usd=friction_usd, seed=seed, paths=paths)

    return Outlook(at_implied=at(vol_implied), at_realized=at(vol_realized))
