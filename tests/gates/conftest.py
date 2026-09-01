"""Shared fixtures for the gate tests.

Deliberately plain data: gates are pure functions over dicts, so nothing here needs a
broker, a network, or a mock. That is the property that makes the rule in
docs/TESTING.md — every gate has a test proving it rejects — cheap enough to keep.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
from halstreet.gates.base import GateContext, Limits, Proposal
from halstreet.marketdata.occ import Right, occ

SPOT = Decimal(765)
TODAY = date(2026, 8, 26)
FAR = TODAY + timedelta(days=45)
SOON = TODAY + timedelta(days=2)


def sym(strike, right=Right.CALL, expiry=FAR):
    return occ("SPY", expiry, right, Decimal(strike))


def leg(strike, right=Right.CALL, *, long=True, expiry=FAR, ratio=1):
    return Leg(
        sym(strike, right, expiry),
        ratio,
        Side.BUY if long else Side.SELL,
        PositionIntent.BUY_TO_OPEN if long else PositionIntent.SELL_TO_OPEN,
    )


def proposal(*legs, qty=1, limit=Decimal("2.00"), name="test"):
    return Proposal(
        structure=Structure(name=name, legs=tuple(legs), qty=qty, limit_price=limit),
        underlying="SPY",
    )


def offered(ctx: GateContext, *proposals: Proposal) -> GateContext:
    """The same context, with these structures recorded as having been on the menu.

    Written out at each call site rather than folded into the `ctx` fixture. A fixture
    that quietly said "yes, everything was offered" would make `from-the-menu` pass in
    every test that never thought about it, which is the same as not having the gate —
    and it is exactly the kind of accommodating fixture that hides a real regression.
    """
    import dataclasses

    from halstreet.gates.contract import leg_signature

    return dataclasses.replace(
        ctx, menu=frozenset(leg_signature(p.structure.legs) for p in proposals))


@pytest.fixture
def limits():
    return Limits()


@pytest.fixture
def breaker():
    """An unlatched breaker with the day's baseline already set, and no entries yet.

    Supplied by default because the circuit gates fail closed without it — a test
    that forgot to pass one would otherwise look like a rejection on the merits.
    """
    state = CircuitState(baseline_equity=Decimal(100000),
                         baseline_day=TODAY.isoformat())
    return state


@pytest.fixture
def benched():
    """Nothing resting, stated rather than omitted.

    `loss_cooldown` fails closed on a missing record, so a fixture that left this out
    would reject every proposal in every chain test and look like a rejection on the
    merits — the same trap the `breaker` fixture above exists to avoid.
    """
    return {}


@pytest.fixture
def ctx(limits, breaker, benched):
    """A healthy account with nothing open and a fully-quoted chain."""
    return GateContext(
        account={"equity": "100000.00", "account_number": "PA1", "id": "acct-1",
                 # Options collateral is cash, not the levered `buying_power`. Set
                 # equal to equity here, which is what a flat account reports.
                 "options_buying_power": "100000.00", "buying_power": "400000.00"},
        positions=[],
        chain=_chain(),
        limits=limits,
        asof=TODAY,
        spot=SPOT,
        breaker=breaker,
        benched=benched,
    )


def _chain():
    """Strikes around spot, both rights, both a far and a near expiry."""
    out = {}
    for expiry in (FAR, SOON):
        for strike in range(700, 831, 5):
            for right in (Right.CALL, Right.PUT):
                out[sym(strike, right, expiry)] = {
                    "latestQuote": {"bp": 2.00, "ap": 2.10, "bs": 50, "as": 50},
                    "greeks": {
                        "delta": 0.5, "gamma": 0.01, "theta": -0.2,
                        "vega": 0.8, "rho": 0.3,
                    },
                    "impliedVolatility": 0.13,
                    "openInterest": 5000,
                    "dailyBar": {"v": 2500},
                }
    return out


# --- named structures, for readability in the tests --------------------------

@pytest.fixture
def vertical_spread():
    """Long 765 call / short 770 call — defined risk, $5 wide."""
    return proposal(leg(765), leg(770, long=False), limit=Decimal("2.00"))


@pytest.fixture
def naked_call():
    """A single short call. The canonical undefined-risk structure."""
    return proposal(leg(770, long=False), limit=Decimal("-3.00"), name="naked call")


@pytest.fixture
def condor():
    """Long 740P / short 750P / short 780C / long 790C."""
    return proposal(
        leg(740, Right.PUT), leg(750, Right.PUT, long=False),
        leg(780, long=False), leg(790),
        limit=Decimal("-2.00"), name="iron condor",
    )
