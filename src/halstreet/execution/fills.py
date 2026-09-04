"""What each leg of a multi-leg order actually filled at.

Alpaca answers an `mleg` order with a parent carrying the *net* `filled_avg_price`
and a `legs` array carrying one price per contract. The net is what the ledger has
always recorded, because the net is what the exit policy acts on — a credit spread's
target is a percentage of the credit, not of either leg.

The legs are what a person looking at the position wants. A spread marked at -1.61
against a -1.51 entry is ten dollars down, and the question that follows immediately
is *which leg*. The answer is on the order and was being discarded.

Measured, from the entry of the position open while this was written:

    parent  filled_avg_price  -1.51
    leg     QQQ261016C00765000  sell  4.51
    leg     QQQ261016C00775000  buy   3.00

3.00 - 4.51 = -1.51. The legs reconstruct the net exactly, which is the property that
makes them safe to show beside it: the per-leg P&L computed from these prices sums to
the structure P&L computed from the net, to the cent. `tests/execution/test_fills.py`
pins that, because the moment the two disagree the panel is lying about one of them.

**Prices only, never quantities.** The signed size of each leg is the ledger's own
record of what was ordered; taking it from the fill would let a partial fill silently
rewrite what the structure is. Divergence against the broker is reported by
`Ledger.divergences`, and that is the only place the broker's quantities win.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def leg_fills(order: Any) -> dict[str, Decimal]:
    """Symbol -> price per contract, from a filled order's `legs` array.

    Positive on both sides, exactly as the broker reports it: a leg sold to open fills
    at 4.51, not at -4.51. Which way the structure holds it is in `OpenStructure.legs`,
    and keeping the sign in one place is what stops it being applied twice.

    Silent about everything it cannot read. An order still `pending_new` has legs with
    no fill price, a single-leg order has no `legs` at all, and a symbol that appears
    twice is a ratio the caller cannot resolve from prices alone. All three yield "no
    per-leg prices here" rather than a partial dictionary that looks complete — the
    caller asks again next cycle, and a leg table with one price missing is worse than
    one that says it has none.
    """
    if not isinstance(order, dict):
        return {}
    legs = order.get("legs")
    if not isinstance(legs, list) or not legs:
        return {}
    out: dict[str, Decimal] = {}
    for leg in legs:
        if not isinstance(leg, dict):
            return {}
        symbol = leg.get("symbol")
        price = leg.get("filled_avg_price")
        if not isinstance(symbol, str) or not symbol or price in (None, ""):
            return {}
        try:
            value = Decimal(str(price))
        except (InvalidOperation, ValueError, TypeError):
            return {}
        if symbol in out:
            # The same contract on two legs of one order. The prices are per leg and
            # the ledger keys by symbol, so there is no honest way to store both.
            return {}
        out[symbol] = value
    return out


__all__ = ["leg_fills"]
