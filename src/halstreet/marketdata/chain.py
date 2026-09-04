"""Assembling a chain the gates can actually judge.

Alpaca splits what a liquidity gate needs across two endpoints, and neither is
sufficient alone:

  * `get_option_chain` returns quotes, bars, greeks and implied volatility, keyed by
    OCC symbol — but **no open interest**.
  * `get_option_contracts` returns contract metadata including `open_interest` — but
    no quotes and no greeks.

The liquidity gate fails closed on a missing field, which is correct and is how this
gap was found: it rejected a well-formed condor rather than quietly skipping the check
it could not perform. The fix is to merge, not to soften the gate.

One caveat travels with the data. Open interest is published daily and carries its own
`open_interest_date` — on a live chain it is routinely a day or two behind. That is
acceptable for a floor ("is anyone holding this contract at all") and wrong for
anything presented as a live measurement, so the date is carried through rather than
dropped.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _int(value: object) -> int | None:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def enrich(chain: dict[str, dict], contracts: list[dict]) -> dict[str, dict]:
    """Merge contract metadata into chain snapshots, keyed by OCC symbol.

    Returns a new mapping; the inputs are not mutated. Contracts with no matching
    snapshot are ignored — a contract nobody quotes is not tradeable anyway — and
    snapshots with no matching contract keep whatever they had, so a missing
    `openInterest` still fails the gate rather than silently becoming zero.
    """
    by_symbol = {str(c.get("symbol")): c for c in contracts if c.get("symbol")}
    out: dict[str, dict] = {}
    for symbol, snapshot in chain.items():
        merged = dict(snapshot)
        contract = by_symbol.get(symbol)
        if contract is not None:
            oi = _int(contract.get("open_interest"))
            if oi is not None:
                merged["openInterest"] = oi
            if contract.get("open_interest_date"):
                merged["openInterestDate"] = contract["open_interest_date"]
            if contract.get("tradable") is not None:
                merged["tradable"] = contract["tradable"]
        out[symbol] = merged
    return out


def daily_volume(snapshot: dict[str, Any]) -> int | None:
    """Today's traded volume for a contract, from its daily bar."""
    bar = snapshot.get("dailyBar") or {}
    return _int(bar.get("v"))
