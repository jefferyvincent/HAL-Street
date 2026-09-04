"""Reading an option chain response, and picking strikes out of it.

Split out of `scripts/verify_multileg.py`, which is where these started and where they
could not be tested — the script was not importable, so the one part of it that is
pure arithmetic over a payload had no test at all.

That script also carried its own `parse_occ`, under a comment saying the real one
"should be ported into `marketdata/`". The port landed as `marketdata/occ.py` and the
copy stayed, quietly parsing symbols its own way. Everything here goes through
`occ.parse`; there is one OCC parser in this codebase and this is not it.

`contracts_from_chain` is written defensively on purpose. Confirming what Alpaca's
OptionChain actually returns is a reason the verification script exists, so it has to
survive being wrong about the shape and report what it saw rather than an empty list
that reads as "no contracts listed".
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from halstreet import clock
from halstreet.marketdata import occ as occ_mod

#: Never trade the front week in a verification run: a contract inside a week has a
#: fill profile that says nothing about the structures the agent actually opens.
EXPIRY_FLOOR_DAYS = 7


def contracts_from_chain(chain: Any) -> list[str]:
    """Pull option symbols out of whatever shape OptionChain returned."""
    if isinstance(chain, dict):
        for key in ("snapshots", "option_chain", "chain", "data", "results"):
            inner = chain.get(key)
            if isinstance(inner, dict):
                return sorted(inner.keys())
            if isinstance(inner, list):
                return sorted(
                    str(c.get("symbol")) for c in inner if isinstance(c, dict) and c.get("symbol")
                )
        # A bare map of symbol -> quote. Confirmed by parsing, not by assuming: a dict
        # of five keys that are not OCC symbols is some other response entirely.
        keys = [k for k in chain if isinstance(k, str)]
        if keys and all(occ_mod.parse(k) for k in keys[:5]):
            return sorted(keys)
    if isinstance(chain, list):
        return sorted(
            str(c.get("symbol")) for c in chain if isinstance(c, dict) and c.get("symbol")
        )
    return []


def pick_expiry(symbols: list[str], target_dte: int) -> date | None:
    """The listed expiry closest to the requested DTE, never nearer than a week."""
    today = clock.today()
    floor = today + timedelta(days=EXPIRY_FLOOR_DAYS)
    expiries = {c.expiry for s in symbols if (c := occ_mod.parse(s)) and c.expiry >= floor}
    if not expiries:
        return None
    target = today + timedelta(days=target_dte)
    return min(expiries, key=lambda e: abs((e - target).days))


def expiries_after(symbols: list[str], expiry: date) -> list[str]:
    """The symbols listed later than `expiry` — the roll candidates."""
    return [s for s in symbols if (c := occ_mod.parse(s)) and c.expiry > expiry]


def strikes_for(symbols: list[str], expiry: date, right: str) -> list[Decimal]:
    out = {
        c.strike for s in symbols
        if (c := occ_mod.parse(s)) and c.expiry == expiry and c.right.value == right
    }
    return sorted(out)


def nearest(strikes: list[Decimal], target: Decimal) -> Decimal:
    """The listed strike closest to `target`. Ties go to the lower strike."""
    return min(strikes, key=lambda s: (abs(s - target), s))
