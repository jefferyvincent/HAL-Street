"""Contract validation and the DTE floor.

These two catch different failure modes and both matter more than their size suggests.

**Contract validation** is the anti-hallucination gate. A model asked for a 765 strike
will cheerfully emit a 762.50 that was never listed, or an expiry that falls on a
Sunday, and the resulting order dies at the broker with an opaque error after the
proposal has already been journalled as approved. Every leg must appear in the chain
that was actually fetched — not merely parse as an OCC symbol, but exist.

**The DTE floor** does two jobs. It is a risk rule in its own right: holding short
gamma into expiry week is how a defined-risk position becomes an assignment problem
overnight. It is also, less obviously, what guarantees the greeks the delta and vega
gates depend on exist at all — Alpaca returns no greeks for 0DTE contracts, because
Black-Scholes carries time-to-expiry in its denominator and the values are
indeterminate rather than merely absent. Two gates that look independent are
load-bearing for each other, and that is worth saying out loud in the write-up.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from halstreet.gates.base import GateContext, GateResult, Proposal, allow, gate, reject
from halstreet.marketdata.occ import parse

CONTRACT_EXISTS = "contract-validation"
DTE_FLOOR = "dte-floor"


@gate(CONTRACT_EXISTS)
def contract_exists(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Every leg must be a real, listed contract present in the fetched chain."""
    if not ctx.chain:
        return reject(
            CONTRACT_EXISTS,
            "no chain supplied, so no leg can be verified as a listed contract",
        )

    unparseable = [leg.symbol for leg in proposal.structure.legs if parse(leg.symbol) is None]
    if unparseable:
        return reject(CONTRACT_EXISTS, f"not valid OCC symbols: {unparseable}")

    missing = [leg.symbol for leg in proposal.structure.legs if leg.symbol not in ctx.chain]
    if missing:
        return reject(
            CONTRACT_EXISTS,
            f"{len(missing)} leg(s) not in the {proposal.underlying} chain: {missing}. "
            "A strike that was never listed is a hallucinated strike.",
        )

    wrong_root = [
        leg.symbol
        for leg in proposal.structure.legs
        if (c := parse(leg.symbol)) and c.root != proposal.underlying.upper()
    ]
    if wrong_root:
        return reject(
            CONTRACT_EXISTS,
            f"leg(s) on the wrong underlying (expected {proposal.underlying}): {wrong_root}",
        )

    return allow(CONTRACT_EXISTS, f"all {len(proposal.structure.legs)} legs listed")


@gate(DTE_FLOOR)
def dte_floor(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject any structure with a leg expiring inside the floor.

    Judged on the nearest expiry across all legs — a calendar spread whose front leg
    expires in two days is a two-day problem regardless of how far out the back leg
    sits.
    """
    floor = ctx.limits.min_dte
    dtes: list[tuple[str, int]] = []
    for leg in proposal.structure.legs:
        contract = parse(leg.symbol)
        if contract is None:
            return reject(DTE_FLOOR, f"cannot read expiry from {leg.symbol}")
        dtes.append((leg.symbol, contract.dte(ctx.asof)))

    symbol, nearest = min(dtes, key=lambda pair: pair[1])
    if nearest < floor:
        detail = (
            "already expired" if nearest < 0 else
            "expires today — Alpaca returns no greeks for 0DTE, so this cannot be "
            "risk-assessed either" if nearest == 0 else
            f"{nearest} days to expiry"
        )
        return reject(
            DTE_FLOOR,
            f"{symbol} {detail}, under the {floor}-day floor. No short gamma into expiry week.",
        )
    return allow(DTE_FLOOR, f"nearest leg {nearest} DTE (floor {floor})")


ON_THE_MENU = "from-the-menu"


def leg_signature(legs: Iterable[Any]) -> frozenset[tuple[str, int]]:
    """A structure reduced to what it actually is: signed contracts per symbol.

    Order-insensitive and name-insensitive on purpose. The same iron condor built by
    the strategy engine and re-emitted by the model with its legs in a different order,
    or called something else, is the same trade — and a gate comparing anything more
    superficial than this would be defeatable by reordering a list.

    Takes either shape of leg: the strategy engine's candidates carry plain dicts,
    the parsed proposal carries `Leg` objects, and both have to reduce to the same
    signature or the comparison is meaningless.
    """
    out: dict[str, int] = {}
    for leg in legs:
        if isinstance(leg, dict):
            symbol, side, qty = leg.get("symbol"), leg.get("side"), leg.get("ratio_qty", 1)
        else:
            symbol, side, qty = leg.symbol, leg.side, getattr(leg, "ratio_qty", 1)
        if not symbol:
            continue
        sign = 1 if str(getattr(side, "value", side)).lower() == "buy" else -1
        out[str(symbol)] = out.get(str(symbol), 0) + sign * int(qty or 1)
    return frozenset((symbol, n) for symbol, n in out.items() if n)


@gate(ON_THE_MENU)
def on_the_menu(proposal: Proposal, ctx: GateContext) -> GateResult:
    """The proposed structure must be one the strategy engine actually built.

    This gate exists because the rule was, for a long time, only a sentence in the
    system prompt: *"Legs come from the candidates given to you. Do not invent strikes
    or expiries."* The model complied. Nothing made it.

    `contract-validation` above is not the same check and does not cover this. It
    asks whether each leg exists in the chain — so a model that assembled real, listed
    strikes into a structure the ranking never scored would pass it cleanly. That
    trade would carry no score breakdown, no liquidity screen, no viability check
    against friction, and no reason in the journal beyond the model's own sentence
    about it. It would be the one trade in the run that nothing deterministic ever
    looked at, which is precisely the case this project exists to make impossible.

    Comparing signatures rather than names also catches the subtler version: legs
    borrowed from two different candidates and recombined into a third structure that
    was never on the menu and never scored.

    Fails closed. An empty menu means the caller did not wire one, and a gate that
    cannot see what was offered must not certify that the answer came from it.
    """
    if not ctx.menu:
        return reject(ON_THE_MENU, "no candidate menu was recorded for this proposal; "
                                   "cannot confirm the structure was one that was offered")
    signature = leg_signature(proposal.structure.legs)
    if signature in ctx.menu:
        return allow(ON_THE_MENU, f"matches a candidate on the {len(ctx.menu)}-structure menu")
    legs = ", ".join(f"{n:+d} {symbol}" for symbol, n in sorted(signature))
    return reject(
        ON_THE_MENU,
        f"structure was not on the menu the strategy engine built ({legs}); "
        f"{len(ctx.menu)} candidate(s) were offered and none matches these legs",
    )
