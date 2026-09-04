"""Liquidity floor — open interest, volume and quoted width, per leg.

Adapted from TradeScans' `liquidity-gate.ts`, which lived in the strategy engine
there. It belongs here instead: it is a rejection rule, and rejection rules belong on
the auditable side of the proposal boundary where the model cannot reach them.

Judged per leg, and the worst leg decides. A four-leg condor is only as tradeable as
its thinnest strike — a structure with three liquid legs and one that quotes 40% wide
is not 75% fine, it is a position you cannot exit at a price you would accept, which
matters far more on the way out than on the way in.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from halstreet.gates.base import GateContext, GateResult, Proposal, allow, gate, reject
from halstreet.marketdata.chain import daily_volume

LIQUIDITY = "liquidity-floor"
SPREAD_WIDTH = "quoted-spread-width"


def _num(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@gate(LIQUIDITY)
def liquidity_floor(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject when any leg is too thinly held or traded."""
    floor = ctx.limits.min_open_interest
    thin: list[str] = []
    quiet: list[str] = []
    unreadable: list[str] = []

    for leg in proposal.structure.legs:
        snap = ctx.chain.get(leg.symbol)
        if snap is None:
            unreadable.append(f"{leg.symbol} (not in chain)")
            continue
        oi = _num(snap.get("openInterest"))
        if oi is None:
            # Open interest is not in the chain snapshot — it comes from
            # get_option_contracts. If it is missing here the caller forgot to merge
            # the two (marketdata.chain.enrich), and an unmeasured leg is not a
            # liquid one.
            unreadable.append(f"{leg.symbol} (no openInterest — chain not enriched?)")
            continue
        if oi < floor:
            thin.append(f"{leg.symbol} OI={oi:.0f}")
            continue

        volume = daily_volume(snap)
        if volume is None:
            unreadable.append(f"{leg.symbol} (no daily volume)")
        elif volume < ctx.limits.min_daily_volume:
            quiet.append(f"{leg.symbol} vol={volume}")

    if unreadable:
        return reject(
            LIQUIDITY,
            f"cannot read liquidity for {len(unreadable)} leg(s): {unreadable}. "
            "An unmeasurable leg is not a liquid one.",
        )
    if thin:
        return reject(LIQUIDITY, f"below the {floor} OI floor: {thin}")
    if quiet:
        return reject(
            LIQUIDITY,
            f"traded fewer than {ctx.limits.min_daily_volume} contracts today: {quiet}. "
            "Open interest is a day stale; volume is the live half of the check.",
        )
    return allow(
        LIQUIDITY,
        f"all {len(proposal.structure.legs)} legs above {floor} OI and "
        f"{ctx.limits.min_daily_volume} daily volume",
    )


@gate(SPREAD_WIDTH)
def spread_width(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Reject when any leg's bid/ask is wider than the cap, as a percent of mid.

    Width is measured against the mid rather than in absolute cents so the rule means
    the same thing on a $0.40 wing and a $24 in-the-money leg.
    """
    cap = ctx.limits.max_bid_ask_width_pct
    wide: list[str] = []
    unreadable: list[str] = []

    for leg in proposal.structure.legs:
        snap = ctx.chain.get(leg.symbol)
        quote = (snap or {}).get("latestQuote") or {}
        bid, ask = _num(quote.get("bp")), _num(quote.get("ap"))
        if bid is None or ask is None:
            unreadable.append(f"{leg.symbol} (no quote)")
            continue
        if ask <= 0 or bid < 0 or ask < bid:
            unreadable.append(f"{leg.symbol} (nonsense quote {bid}/{ask})")
            continue
        mid = (bid + ask) / 2
        if mid <= 0:
            unreadable.append(f"{leg.symbol} (zero mid)")
            continue
        width = (ask - bid) / mid * 100
        if width > cap:
            wide.append(f"{leg.symbol} {width:.1f}% ({bid}/{ask})")

    if unreadable:
        return reject(
            SPREAD_WIDTH,
            f"cannot read a quote for {len(unreadable)} leg(s): {unreadable}",
        )
    if wide:
        return reject(
            SPREAD_WIDTH,
            f"quoted wider than {cap:g}% of mid: {wide}. The worst leg decides — you "
            "have to exit through it too.",
        )
    return allow(SPREAD_WIDTH, f"all legs within {cap:g}% of mid")
