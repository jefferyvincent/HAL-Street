"""Circuit breakers: the gates that judge the *situation* rather than the proposal.

Every other gate asks whether a structure is sound. These four ask whether we should
be opening anything at all right now, and none of them cares what the structure is.
They are the guard against the failure mode an autonomous agent actually has — not a
bad trade, but a runaway: a loop machine-gunning the broker, or a string of losers
that should have stopped trading hours ago.

Borrowed in spirit from HAL's `sensory/risk.py`, which had six of these. Four survive
the crossing; gross-exposure and per-symbol caps are already covered here by
`portfolio_risk_ceiling` and `underlying_concentration`, which measure defined risk
directly rather than through market value.

**The correlated-group cap is the one with teeth**, and it exists because of a scan
on 2026-08-26 that this project's own default universe walked straight into. The
agent approved put credit spreads on SPY, QQQ *and* IWM in a single cycle. That is
one bullish bet at triple size, and every existing gate waved it through:
`underlying_concentration` filters on an exact root match, so three different roots
are three separate names to it, and `portfolio_greek_bounds` only bites above 5,000
share-equivalents, which three small spreads never approach. Diversification across
tickers that move together is not diversification. It is leverage with better
paperwork.

**State comes from `agent.breaker`, not from here.** These gates read history off
`GateContext.breaker`; they never load it. The layer stays pure and testable without
a broker, a clock, or a filesystem.

**Entries only**, like every gate. `agent.manager` closes positions without consulting
any of this — a latched halt is a reason to be more able to de-risk, not less.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from halstreet.gates.base import GateContext, GateResult, Proposal, allow, gate, reject
from halstreet.marketdata.occ import root as occ_root

CORRELATED = "correlated-exposure"
DAILY_LOSS = "daily-loss-halt"
ENTRY_RATE = "entry-rate-throttle"
OPEN_POSITIONS = "open-position-count"

# Names that move together closely enough that holding several is one position rather
# than a diversified book. Deliberately a small static map rather than a live
# correlation matrix: it needs no data, cannot go stale mid-session, is auditable by
# eye, and a correlation matrix would need return history for every holding to say
# something everyone already knows.
#
# A symbol may appear in more than one group, and every group it belongs to is checked.
CORRELATED_GROUPS: dict[str, frozenset[str]] = {
    "us-broad-market": frozenset({
        "SPY", "VOO", "IVV", "QQQ", "QQQM", "IWM", "DIA", "VTI", "MDY", "RSP",
        "SPXL", "TQQQ", "QLD", "SSO", "UPRO", "SPXU", "SQQQ", "SDS",
    }),
    "semiconductors": frozenset({
        "NVDA", "AMD", "AVGO", "SMH", "SOXX", "SOXL", "INTC", "MU", "TSM",
        "ARM", "QCOM", "TXN", "LRCX", "AMAT",
    }),
    "megacap-tech": frozenset({
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NFLX", "TSLA", "XLK", "VGT",
    }),
    "long-duration-rates": frozenset({"TLT", "IEF", "ZROZ", "EDV", "TMF", "TBT", "TMV"}),
    "precious-metals": frozenset({"GLD", "IAU", "SLV", "GDX", "GDXJ", "NUGT"}),
}


#: The bucket every root that is in no group above falls into.
#:
#: Not a correlated group and deliberately not in `CORRELATED_GROUPS` — its members
#: are defined by absence rather than by a claim that they move together, and putting
#: it in that map would make `groups_for` report a correlation nobody has verified.
UNCLASSIFIED = "unclassified"


def groups_for(root: str) -> list[str]:
    """Every correlated group this underlying belongs to.

    Never empty. A root in none of the maps above comes back as `[UNCLASSIFIED]`,
    which is the honest answer — "nobody has classified this name" — rather than the
    old one, which was silence and read downstream as "unconstrained".
    """
    upper = root.upper()
    known = sorted(name for name, members in CORRELATED_GROUPS.items() if upper in members)
    return known or [UNCLASSIFIED]


def _unclassified(roots) -> set[str]:
    """The held roots that are in no correlated group.

    Computed from what is actually held rather than from a member list, because the
    bucket has no member list — it is the complement of every group, over an unbounded
    universe of names the news might surface.
    """
    mapped = frozenset().union(*CORRELATED_GROUPS.values()) if CORRELATED_GROUPS else frozenset()
    return {r for r in roots if r not in mapped}


def _num(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _gross_by_root(positions: list[dict]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for position in positions:
        symbol = str(position.get("symbol") or "")
        qty = _num(position.get("qty"))
        if not symbol or qty is None:
            continue
        root = occ_root(symbol)
        out[root] = out.get(root, Decimal(0)) + abs(qty)
    return out


@gate(CORRELATED)
def correlated_exposure(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Cap gross contract exposure across a basket of names that move together.

    Counts gross contracts, matching `underlying_concentration`, so the two gates
    measure the same quantity at two scopes and the broker's leg-netting across
    structures cannot hide anything from either.

    Gross rather than net is the deliberate, conservative choice, and it is worth
    being honest about what it costs: a genuinely hedged pair — long SPY puts against
    short QQQ puts — is counted as two bets when it is arguably closer to none. The
    cap therefore constrains some positions it need not. That is the correct direction
    to be wrong in for a ceiling, and the alternative is netting exposure across
    different underlyings whose deltas are not commensurable without beta-weighting
    every leg to a common index.

    An underlying in no group is not waved through. It joins the `UNCLASSIFIED`
    bucket and is bounded by `max_unclassified_positions` — a separate, looser cap
    that says how much of the book may sit in names whose correlation nobody has
    checked. That used to be a wave-through, which was defensible while a human chose
    every name and every name was in the map; news discovery made "in no group" the
    common case rather than a deliberate one.
    """
    root = proposal.underlying.upper()
    groups = groups_for(root)
    # Two caps, because there are two claims. A named group is a verified statement
    # that these names move together; the unclassified bucket is a statement about the
    # map's coverage. Sharing one number would mean loosening the checked claim to
    # make room for the unchecked one.
    unmapped = groups == [UNCLASSIFIED]
    cap_positions = (ctx.limits.max_unclassified_positions if unmapped
                     else ctx.limits.max_correlated_positions)
    if cap_positions <= 0:
        return allow(CORRELATED, "disabled" if not unmapped else "unclassified cap disabled")

    # Booked and ordered together, for the same reason the per-name cap counts both:
    # a resting order is a commitment the basket can end up carrying, and a gate that
    # sees only fills lets the size problem relocate to the group.
    held = _gross_by_root(ctx.positions)
    for root_, qty in _gross_by_root(ctx.pending).items():
        held[root_] = held.get(root_, Decimal(0)) + qty
    adding = sum(leg.ratio_qty for leg in proposal.structure.legs) * proposal.structure.qty
    # One "position" is one structure's worth of legs, so the contract cap scales with
    # the structure proposed rather than assuming everything is a two-leg spread.
    # NOT multiplied by qty, and that is the whole point of the cap. An earlier
    # version read `cap_positions * legs * qty`, which let a proposal inflate its own
    # ceiling faster than it inflated its exposure — held contracts do not scale with
    # the order, so a 1-contract order was rejected while the same structure at 10
    # contracts passed. Backwards for a concentration limit. Legs stay in, so a
    # four-leg condor is not judged against a two-leg spread's allowance.
    cap_contracts = cap_positions * len(proposal.structure.legs)

    for group in groups:
        # The unclassified bucket is the complement of every group rather than a
        # member list, so its membership is decided against what is held.
        in_bucket = (_unclassified(held) if group == UNCLASSIFIED
                     else CORRELATED_GROUPS[group])
        in_group = {r: q for r, q in held.items() if r in in_bucket and q}
        total = sum(in_group.values()) + adding
        if total > cap_contracts:
            names = ", ".join(f"{r} {q:.0f}" for r, q in sorted(in_group.items()))
            return reject(
                CORRELATED,
                f"'{group}' would hold {total:.0f} contracts ({names or 'nothing'} open "
                f"+ {adding} new on {root}), over the {cap_contracts} implied by max "
                f"{cap_positions} position(s). "
                + ("No correlation map covers these names, so the book cannot show "
                   "they are independent. An unverified claim is bounded, not trusted."
                   if group == UNCLASSIFIED else
                   "These names move together — holding several is one bet at several "
                   "times the size, not a diversified book."),
            )

    reported = groups[0]
    members = (_unclassified(held) if reported == UNCLASSIFIED
               else CORRELATED_GROUPS[reported])
    total = sum(q for r, q in held.items() if r in members) + adding
    return allow(CORRELATED, f"'{reported}' {total:.0f}/{cap_contracts} contracts")


@gate(DAILY_LOSS)
def daily_loss_halt(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Refuse every entry once the day's loss floor has been breached.

    Latched, not instantaneous: it stays refused for the rest of the session even if
    equity recovers. A breaker that resets the moment the tape bounces is not a
    breaker, it is a delay — and the whole point is to stop a bad day from being
    compounded by an agent that has no memory of it.

    Reads the latch; never sets it. `agent.breaker.CircuitState.observe` does that,
    once per cycle, from the equity snapshot the loop already fetched.
    """
    if ctx.limits.daily_loss_limit_pct <= 0:
        return allow(DAILY_LOSS, "disabled")
    breaker = ctx.breaker
    if breaker is None:
        # Fails closed, like every other gate on missing data. A loop that forgot to
        # wire the breaker in must not read as a loop with a healthy one.
        return reject(
            DAILY_LOSS,
            "no circuit state available; cannot tell whether trading is halted",
        )
    if breaker.halted:
        return reject(DAILY_LOSS, f"trading halted — {breaker.halt_reason}")
    if breaker.baseline_equity is None:
        return allow(DAILY_LOSS, "no baseline yet (first cycle of the day)")
    return allow(
        DAILY_LOSS,
        f"within the {ctx.limits.daily_loss_limit_pct:g}% floor of "
        f"${breaker.baseline_equity:,.0f}",
    )


@gate(ENTRY_RATE)
def entry_rate_throttle(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Cap entries submitted per rolling hour.

    Not a risk limit — a runaway limit. The scan loop opens at most one position per
    underlying per cycle on a 30-minute cadence, so this should never fire in normal
    operation. It fires when something is wrong: a scheduler that lost its spacing, a
    crash loop restarting the agent every few seconds, a retry that submits before it
    reads. Those are the cases where the damage is done in minutes.
    """
    cap = ctx.limits.max_entries_per_hour
    if cap <= 0:
        return allow(ENTRY_RATE, "disabled")
    breaker = ctx.breaker
    if breaker is None:
        return reject(ENTRY_RATE, "no circuit state available; cannot count recent entries")

    recent = len(breaker.entry_times)
    if recent >= cap:
        return reject(
            ENTRY_RATE,
            f"{recent} entries in the last hour reaches the cap of {cap}. The loop "
            "opens at most one position per underlying per cycle, so this firing "
            "means something is submitting outside the schedule.",
        )
    return allow(ENTRY_RATE, f"{recent}/{cap} entries this hour")


@gate(OPEN_POSITIONS)
def open_position_count(proposal: Proposal, ctx: GateContext) -> GateResult:
    """Cap how many broker positions the book may hold at once.

    Counts the broker's positions — one per contract after leg-netting — rather than
    structures, because that is what has to be monitored, marked and closed. A book
    with more open contracts than the exit path can work through in a session is a
    book that will carry something into expiry.
    """
    cap = ctx.limits.max_open_positions
    if cap <= 0:
        return allow(OPEN_POSITIONS, "disabled")

    open_now = len(ctx.positions)
    adding = len({leg.symbol for leg in proposal.structure.legs}
                 - {str(p.get("symbol") or "") for p in ctx.positions})
    total = open_now + adding
    if total > cap:
        return reject(
            OPEN_POSITIONS,
            f"{total} open positions ({open_now} held + {adding} new contract(s)) "
            f"would exceed the cap of {cap}",
        )
    return allow(OPEN_POSITIONS, f"{total}/{cap} open positions")
