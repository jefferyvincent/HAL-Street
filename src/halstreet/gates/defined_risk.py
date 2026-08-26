"""Defined-risk and position-size gates.

The first is the one the whole submission rests on: **no structure with unbounded
loss reaches an order.** It is computed from the structure's payoff at expiry rather
than matched against a list of known strategy names, because a gate that recognises
only "vertical" and "iron condor" must decide what to do with everything else — and
whatever it decides, it is guessing. Payoff analysis has no such gap: a malformed,
mislabelled or entirely novel structure is judged on what it would actually pay.

The maths is small. At expiry the payoff of an options-only structure is piecewise
linear in the underlying, with kinks only at strikes. Its minimum over any bounded
region is therefore attained at a strike, at zero, or at the far end — so evaluating
those points is exact rather than a sample. The one unbounded direction is upward:
a net short call position loses without limit as the underlying rises. Downward is
bounded because the underlying stops at zero, which is why a naked short put is not
an undefined-risk rejection here — it is a very large max loss, and the size gate
below is what refuses it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from halstreet.execution.structures import Side
from halstreet.gates.base import GateContext, GateResult, Proposal, allow, gate, reject
from halstreet.marketdata.occ import (
    CONTRACT_MULTIPLIER,
    PayoffLeg,
    Right,
    breakpoints,
    net_call_ratio,
    parse,
    payoff,
)

DEFINED_RISK = "defined-risk-only"
MAX_LOSS = "max-loss-per-position"
PORTFOLIO_RISK = "portfolio-risk-ceiling"
BUYING_POWER = "options-buying-power"


def _num(value: object) -> Decimal | None:
    """A field read off the broker's account snapshot, or None when it is unusable."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _payoff_legs(proposal: Proposal) -> list[PayoffLeg] | str:
    """Reduce a proposal's legs to payoff terms, or explain why it cannot be done."""
    legs: list[PayoffLeg] = []
    for leg in proposal.structure.legs:
        contract = parse(leg.symbol)
        if contract is None:
            return f"leg {leg.symbol} is not a parseable OCC option symbol"
        if leg.side is None:
            return f"leg {leg.symbol} carries no side, so its direction is unknown"
        legs.append(
            PayoffLeg(
                right=Right(contract.right),
                strike=contract.strike,
                ratio=leg.ratio_qty,
                long=leg.side is Side.BUY,
            )
        )
    return legs


def max_loss_per_contract(legs: list[PayoffLeg], net_premium: Decimal) -> Decimal | None:
    """Worst-case loss per contract in dollars, or None if unbounded.

    `net_premium` is the structure's net cost per share: positive for a debit paid,
    negative for a credit received. A debit adds to the loss at every price; a credit
    offsets it.
    """
    if net_call_ratio(legs) < 0:
        return None
    worst = min(payoff(legs, price) for price in breakpoints(legs))
    # Loss is negative payoff, plus whatever was paid to get in.
    return (net_premium - worst) * CONTRACT_MULTIPLIER


@gate(DEFINED_RISK)
def defined_risk_only(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject any structure whose loss is unbounded.

    Fails closed on anything it cannot read: an unparseable symbol or a leg with no
    side is a rejection, not a pass, because an unreadable structure has not been
    shown to be safe.
    """
    legs = _payoff_legs(proposal)
    if isinstance(legs, str):
        return reject(DEFINED_RISK, f"cannot determine risk shape — {legs}")

    naked = net_call_ratio(legs)
    if naked < 0:
        return reject(
            DEFINED_RISK,
            f"net short {abs(naked)} call(s) — loss is unbounded as {proposal.underlying} "
            "rises. Defined-risk structures only.",
        )
    return allow(DEFINED_RISK, f"bounded (net call ratio {naked:+d})")


@gate(MAX_LOSS)
def max_loss_per_position(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject a structure whose worst case exceeds the per-position cap.

    Uses the proposal's limit price as the net premium when one is set. With no limit
    price the structure would go in at market, so the premium is unknown at gate time
    — and an unknown premium means an unknown max loss, which fails closed.
    """
    limits = ctx.limits
    legs = _payoff_legs(proposal)
    if isinstance(legs, str):
        return reject(MAX_LOSS, f"cannot size risk — {legs}")

    premium = proposal.structure.limit_price
    if premium is None:
        return reject(
            MAX_LOSS,
            "no limit price, so the net debit/credit — and therefore the max loss — is "
            "unknown at gate time. Price the structure before proposing it.",
        )

    per_contract = max_loss_per_contract(legs, premium)
    if per_contract is None:
        return reject(MAX_LOSS, "loss is unbounded; see the defined-risk gate")

    total = per_contract * proposal.structure.qty
    cap = limits.max_loss_per_position_usd
    if total > cap:
        return reject(
            MAX_LOSS,
            f"max loss ${total:,.2f} ({proposal.structure.qty} x ${per_contract:,.2f}) "
            f"exceeds the ${cap:,.2f} cap",
        )
    return allow(MAX_LOSS, f"max loss ${total:,.2f} of ${cap:,.2f}")


@gate(PORTFOLIO_RISK)
def portfolio_risk_ceiling(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject when this position's worst case is too large a share of equity.

    The per-position cap is a fixed dollar amount; this one scales with the account,
    so a drawdown tightens it automatically rather than leaving a fixed cap that grows
    more dangerous the more you have lost.
    """
    limits = ctx.limits
    equity = ctx.equity
    if equity is None or equity <= 0:
        return reject(
            PORTFOLIO_RISK,
            f"account equity unreadable ({ctx.account.get('equity')!r}); cannot size risk",
        )

    legs = _payoff_legs(proposal)
    if isinstance(legs, str):
        return reject(PORTFOLIO_RISK, f"cannot size risk — {legs}")
    premium = proposal.structure.limit_price
    if premium is None:
        return reject(PORTFOLIO_RISK, "no limit price, so max loss is unknown")

    per_contract = max_loss_per_contract(legs, premium)
    if per_contract is None:
        return reject(PORTFOLIO_RISK, "loss is unbounded; see the defined-risk gate")

    total = per_contract * proposal.structure.qty
    pct = total / equity * 100
    cap = limits.max_portfolio_risk_pct
    if pct > cap:
        return reject(
            PORTFOLIO_RISK,
            f"max loss ${total:,.2f} is {pct:.1f}% of ${equity:,.2f} equity, over the "
            f"{cap:g}% ceiling",
        )
    return allow(PORTFOLIO_RISK, f"{pct:.1f}% of equity (ceiling {cap:g}%)")


@gate(BUYING_POWER)
def options_buying_power(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject a structure the account cannot actually collateralise.

    Every other sizing gate measures against **equity**. The broker does not: opening
    a short spread requires collateral, and for options that collateral comes out of
    `options_buying_power`, which is a different and much smaller number than the
    headline `buying_power`. Measured on this account with a flat book:

        buying_power            $359,270      <- 4x margin, for equities
        options_buying_power     $89,817      <- cash. This is the one that binds.
        equity                   $89,817

    Those last two agree only while nothing is open. As positions accumulate, held
    collateral drains buying power while equity stays flat — so a ceiling expressed as
    a percentage of equity keeps approving trades after the broker has stopped being
    able to accept them. The failure mode is not a bad position; it is a wasted cycle
    ending in an order rejection that the journal records as an infrastructure error.

    Collateral for a defined-risk structure is its max loss, which is exactly what
    `max_loss_per_contract` already computes — so this gate reuses that rather than
    modelling margin a second time. Undefined risk is rejected here too, for the
    honest reason that its collateral requirement is not something this gate can
    compute; `defined_risk_only` will have rejected it already.

    `headroom_pct` leaves the account short of the last dollar. Running buying power
    to exactly zero leaves nothing to *close* with — some exits are debits, and being
    unable to pay one is how a defined-risk position stops being defined.
    """
    limits = ctx.limits
    if limits.min_buying_power_headroom_pct < 0:
        return allow(BUYING_POWER, "disabled")

    raw = ctx.account.get("options_buying_power")
    available = _num(raw)
    if available is None:
        return reject(
            BUYING_POWER,
            f"options_buying_power unreadable ({raw!r}); cannot tell whether this "
            "structure can be collateralised",
        )

    legs = _payoff_legs(proposal)
    if isinstance(legs, str):
        return reject(BUYING_POWER, f"cannot size collateral — {legs}")
    premium = proposal.structure.limit_price
    if premium is None:
        return reject(BUYING_POWER, "no limit price, so the collateral required is unknown")
    per_contract = max_loss_per_contract(legs, premium)
    if per_contract is None:
        return reject(BUYING_POWER, "collateral is unbounded; see the defined-risk gate")

    needed = per_contract * proposal.structure.qty
    reserve = available * limits.min_buying_power_headroom_pct / 100
    usable = available - reserve
    if needed > usable:
        return reject(
            BUYING_POWER,
            f"needs ${needed:,.2f} of collateral against ${usable:,.2f} usable "
            f"(${available:,.2f} options buying power less a "
            f"{limits.min_buying_power_headroom_pct:g}% reserve kept back to pay for "
            "exits). Note this is options buying power, not the headline figure.",
        )
    return allow(BUYING_POWER, f"${needed:,.2f} of ${usable:,.2f} usable collateral")
