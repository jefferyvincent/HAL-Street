"""Portfolio-level gates: concentration, greek exposure, assignment proximity.

These are the gates that judge a proposal against the book rather than on its own
merits. A structure can be individually impeccable and still be the wrong thing to
add.

One design point runs through the concentration gate and is worth stating plainly,
because the live paper run on 2026-08-26 changed it. **Alpaca nets legs across
structures into one position per contract.** After a vertical and a condor both sold
the same Oct-16 770 call, the account reported a single position at qty −2 — not two
positions tagged to their parents. The broker has no concept of which structure a leg
belongs to.

So concentration cannot be measured by counting structures. Two structures sharing a
short strike are one larger short, and a gate counting structures would score that as
diversification. Everything here counts **net contracts per underlying**, which is
what the account actually holds and what actually loses money.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from halstreet.execution.structures import Side
from halstreet.gates.base import GateContext, GateResult, Proposal, allow, gate, reject
from halstreet.marketdata.occ import CONTRACT_MULTIPLIER, Right, parse
from halstreet.marketdata.occ import root as occ_root

CONCENTRATION = "underlying-concentration"
GREEK_BOUNDS = "portfolio-greek-bounds"
ASSIGNMENT = "assignment-proximity"


def _num(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def net_contracts_by_root(positions: list[dict]) -> dict[str, Decimal]:
    """Net signed contract count per underlying, from the flat position list.

    Signed and netted, because that is how the broker holds it. A long and a short of
    the same contract are not two positions; they are zero.
    """
    out: dict[str, Decimal] = {}
    for position in positions:
        symbol = str(position.get("symbol") or "")
        qty = _num(position.get("qty"))
        if not symbol or qty is None:
            continue
        out[occ_root(symbol)] = out.get(occ_root(symbol), Decimal(0)) + qty
    return out


@gate(CONCENTRATION)
def underlying_concentration(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Cap gross contract exposure to any one underlying.

    Counts contracts, not structures — see the module docstring. The proposed
    structure is counted in, via the legs it would add.
    """
    cap_positions = ctx.limits.max_positions_per_underlying
    if cap_positions <= 0:
        return allow(CONCENTRATION, "disabled")

    root = proposal.underlying.upper()
    # Gross rather than net: a long call and a short put on the same name are two
    # bets in the same direction, and netting them to zero would hide that.
    held = sum(
        abs(qty)
        for symbol_root, qty in _gross_by_root(ctx.positions).items()
        if symbol_root == root
    )
    adding = sum(leg.ratio_qty for leg in proposal.structure.legs) * proposal.structure.qty

    # One "position" is one structure's worth of legs, so the contract cap scales with
    # the structure being proposed rather than assuming everything is a 2-leg spread.
    # NOT multiplied by qty, and that is the whole point of the cap. An earlier
    # version read `cap_positions * legs * qty`, which let a proposal inflate its own
    # ceiling faster than it inflated its exposure — held contracts do not scale with
    # the order, so a 1-contract order was rejected while the same structure at 10
    # contracts passed. Backwards for a concentration limit. Legs stay in, so a
    # four-leg condor is not judged against a two-leg spread's allowance.
    cap_contracts = cap_positions * len(proposal.structure.legs)
    total = held + adding

    if total > cap_contracts:
        return reject(
            CONCENTRATION,
            f"{root} would hold {total:.0f} contracts ({held:.0f} open + {adding} new), "
            f"over the {cap_contracts} implied by max {cap_positions} position(s) per "
            "underlying. Legs net across structures at the broker, so this counts "
            "contracts, not structures.",
        )
    return allow(CONCENTRATION, f"{root} {total:.0f}/{cap_contracts} contracts")


def _gross_by_root(positions: list[dict]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for position in positions:
        symbol = str(position.get("symbol") or "")
        qty = _num(position.get("qty"))
        if not symbol or qty is None:
            continue
        out[occ_root(symbol)] = out.get(occ_root(symbol), Decimal(0)) + abs(qty)
    return out


@gate(GREEK_BOUNDS)
def portfolio_greek_bounds(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Bound net delta and net vega across the book including the proposal.

    Fails closed on a missing greek. Alpaca omits greeks where inverting Black-Scholes
    for implied volatility is ill-conditioned — deep in or out of the money — and
    omits them entirely for 0DTE. A proposal whose legs carry no greeks cannot be
    risk-assessed, and a gate that skipped it would stop protecting the book at
    exactly the strikes where the model is most likely to be wrong.
    """
    limits = ctx.limits
    delta = Decimal(0)
    vega = Decimal(0)
    missing: list[str] = []

    def accumulate(symbol: str, signed_qty: Decimal) -> None:
        nonlocal delta, vega
        greeks = (ctx.chain.get(symbol) or {}).get("greeks")
        if not greeks:
            missing.append(symbol)
            return
        d, v = _num(greeks.get("delta")), _num(greeks.get("vega"))
        if d is None or v is None:
            missing.append(symbol)
            return
        delta += d * signed_qty * CONTRACT_MULTIPLIER
        vega += v * signed_qty

    for leg in proposal.structure.legs:
        sign = 1 if leg.side is Side.BUY else -1
        accumulate(leg.symbol, Decimal(sign * leg.ratio_qty * proposal.structure.qty))

    for position in ctx.positions:
        symbol = str(position.get("symbol") or "")
        qty = _num(position.get("qty"))
        if not symbol or qty is None or parse(symbol) is None:
            continue
        accumulate(symbol, qty)

    if missing:
        return reject(
            GREEK_BOUNDS,
            f"no greeks for {len(missing)} contract(s): {missing[:4]}. Cannot bound "
            "portfolio exposure, so this fails closed.",
        )

    if abs(delta) > limits.max_net_delta:
        return reject(
            GREEK_BOUNDS,
            f"net delta {delta:+,.0f} share-equivalents exceeds the "
            f"±{limits.max_net_delta:,.0f} bound",
        )
    if abs(vega) > limits.max_net_vega:
        return reject(
            GREEK_BOUNDS,
            f"net vega {vega:+,.1f} exceeds the ±{limits.max_net_vega:g} bound",
        )
    return allow(GREEK_BOUNDS, f"net delta {delta:+,.0f}, net vega {vega:+,.1f}")


@gate(ASSIGNMENT)
def assignment_proximity(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject a short leg that is near the money and near expiry.

    Early assignment on an American option is not a pricing event, it is an
    operational one: you wake up holding stock, the defined-risk structure you thought
    you had is now a directional position, and the gates never saw it happen. Distance
    from the money is the proxy, and it only matters close to expiry — a short strike
    1% away with 45 days left is ordinary, the same strike with 3 days left is not.
    """
    limits = ctx.limits
    spot = ctx.spot
    if spot is None or spot <= 0:
        return reject(
            ASSIGNMENT,
            f"no spot price for {proposal.underlying}; cannot judge assignment risk",
        )

    at_risk: list[str] = []
    for leg in proposal.structure.legs:
        if leg.side is not Side.SELL:
            continue
        contract = parse(leg.symbol)
        if contract is None:
            return reject(ASSIGNMENT, f"cannot read {leg.symbol}")
        dte = contract.dte(ctx.asof)
        if dte > limits.assignment_dte:
            continue
        distance = abs(contract.strike - spot) / spot * 100
        itm = (
            contract.strike < spot if contract.right is Right.CALL
            else contract.strike > spot
        )
        if itm or distance <= limits.assignment_moneyness_pct:
            at_risk.append(
                f"{leg.symbol} {'ITM' if itm else f'{distance:.1f}% away'} at {dte} DTE"
            )

    if at_risk:
        return reject(
            ASSIGNMENT,
            f"short leg(s) exposed to early assignment: {at_risk}. Within "
            f"{limits.assignment_dte} DTE a short strike inside "
            f"{limits.assignment_moneyness_pct:g}% of spot is an operational risk, not a "
            "pricing one.",
        )
    return allow(ASSIGNMENT, "no short leg near the money near expiry")

