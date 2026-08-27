"""Position management: deciding when to get out.

The competition scores P&L over a window, which means exits matter more than entries.
An entry can be wrong and survive; an exit that never happens turns a defined-risk
position into a max-loss position on expiry day.

The governing rule here is inherited from HAL's risk engine and is deliberate: **exits
are never blocked.** Nothing in `gates/` applies on the way out — not the latched
daily-loss halt in `gates.circuit`, not the correlated-exposure cap, not the
concentration cap. Every one of those is a reason to be *more* able to close, not
less. The gates guard entries only; this module has no gate at all, and
`agent.breaker` is never consulted here.

Three exit conditions, in the order they are checked:

1. **Expiry.** Non-negotiable, and it fires first. A short leg carried into expiry
   week is an assignment problem rather than a pricing one, and Alpaca returns no
   greeks at 0DTE, so a position held that long cannot be risk-assessed even in
   principle. This closes regardless of P&L.
2. **Stop.** A defined-risk structure cannot lose more than its max loss, but waiting
   for that is not a strategy — the last of a max loss is the most expensive and
   least recoverable part of it.
3. **Profit target.** Taking most of the move beats waiting for all of it, because
   the last portion of max gain is bought with the most time and the most risk.

Every threshold is a percentage of the structure's own max gain or max loss, not a
dollar figure — a $41-risk condor and an $820-risk condor should be managed the same
way.

**Round-trip friction bounds all of this.** Measured on this account on 2026-08-26 and
stated per leg per contract, because that is the unit it actually scales in — see
`FRICTION_PER_LEG_USD`. A profit target smaller than the cost of collecting it is
noise, not edge, and `ExitPolicy.sanity_check` says so out loud.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum

from halstreet import clock
from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.execution.structures import (
    Leg,
    PositionIntent,
    Side,
    Structure,
    StructureError,
)
from halstreet.marketdata.occ import CONTRACT_MULTIPLIER, parse

# Round-trip friction, **per leg, per contract**. Used only to warn about profit
# targets smaller than the cost of collecting them.
#
# The unit matters, and getting it wrong here is expensive in a direction that does
# not announce itself. The original figure was $73.40, which is what the 2026-08-26
# verification run cost in total — but that run opened, rolled and closed **three
# separate structures** across 5 orders and 16 leg-fills. Comparing that lump sum
# against one structure's per-contract max gain overstated friction by roughly 4x on
# a four-leg condor, and it was quoted to the model in the system prompt too. The
# agent was declining trades it should have taken, citing arithmetic that was wrong.
#
# Decomposed into the three round trips it actually was, at qty 1:
#
#   Oct-16 765/770 call spread   2 legs   -$15.00   $7.50/leg
#   Oct-16 755/760/770/775 condor 4 legs  -$23.00   $5.75/leg
#   Nov-20 765/770 call spread   2 legs   -$35.00  $17.50/leg
#
# The Nov-20 spread is the outlier and is excluded from the estimate: it is 87 DTE,
# where the market is materially wider than the 21-60 day band this agent trades in.
#
# Confirmed since by the agent's own first live round trip — a QQQ Oct-16 755/765 call
# credit spread opened at -1.60 and closed at +1.69, so $9.00 across 2 legs, or
# $4.50/leg. That is the cheapest of the three in-band observations, which leaves
# $7.50 the conservative choice rather than the central one. Deliberately not lowered
# on a single sample: understating friction talks the agent into marginal trades, and
# that is the expensive direction to be wrong in.
FRICTION_PER_LEG_USD = Decimal("7.50")


def round_trip_cost(legs: int, qty: int = 1) -> Decimal:
    """What opening and closing this structure is expected to cost in slippage.

    Scales with both legs and quantity, because slippage is a spread paid on every
    contract of every leg — there is no fixed per-order component to amortise, and
    trading larger does not make the friction cheaper per contract.
    """
    return FRICTION_PER_LEG_USD * max(legs, 0) * max(qty, 0)


def _dec(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


class Action(str, Enum):
    HOLD = "hold"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    CLOSE_BEFORE_EXPIRY = "close_before_expiry"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExitPolicy:
    """When to close. Separate from `Limits` because these are not entry rules."""

    take_profit_pct: Decimal = Decimal(50)   # of max gain
    stop_loss_pct: Decimal = Decimal(200)    # of credit received / premium paid
    force_close_dte: int = 5

    @classmethod
    def from_env(cls, source: dict[str, str] | None = None) -> ExitPolicy:
        src = os.environ if source is None else source

        def dec(key: str, default: Decimal) -> Decimal:
            raw = (src.get(key) or "").strip()
            return Decimal(raw) if raw else default

        def integer(key: str, default: int) -> int:
            raw = (src.get(key) or "").strip()
            return int(raw) if raw else default

        return cls(
            take_profit_pct=dec("TAKE_PROFIT_PCT", cls.take_profit_pct),
            stop_loss_pct=dec("STOP_LOSS_PCT", cls.stop_loss_pct),
            force_close_dte=integer("FORCE_CLOSE_DTE", cls.force_close_dte),
        )

    def sanity_check(self, max_gain_usd: Decimal | None, *, legs: int = 4,
                     qty: int = 1) -> str | None:
        """Warn when the profit target is smaller than the cost of taking it.

        Both sides scale with quantity, so the warning is size-invariant — which is
        the point. A structure whose edge does not cover its own friction is not
        rescued by trading more of it.
        """
        if max_gain_usd is None or max_gain_usd <= 0:
            return None
        target = max_gain_usd * self.take_profit_pct / 100 * qty
        cost = round_trip_cost(legs, qty)
        if target < cost:
            return (
                f"profit target ${target:,.2f} is below the ${cost:,.2f} round-trip "
                f"cost of {legs} legs x {qty} at ${FRICTION_PER_LEG_USD}/leg measured "
                "on this account — closing here is noise, not edge"
            )
        return None


@dataclass(frozen=True)
class Mark:
    """What a structure is worth right now, net, per share."""

    value: Decimal
    complete: bool
    missing: list[str]


@dataclass(frozen=True)
class Levels:
    """Where the exit policy fires, expressed as marks rather than as P&L.

    `evaluate_exit` reasons in dollars — unrealized against the credit taken. A chart
    plots the *mark*, so drawing the policy on one means converting the thresholds back
    into the space the line is in.

    Doing that conversion anywhere else would be the usual way a chart starts lying:
    two derivations of the same rule that drift apart, with the picture staying
    confident. `test_levels_agree_with_the_policy_that_acts_on_them` pins them
    together by walking a structure across each boundary and checking the action flips
    exactly where this says it will.
    """

    entry: Decimal
    target: Decimal          # mark at which take-profit fires
    stop: Decimal            # mark at which the stop fires
    #: True for a credit structure, where a *rising* mark is a loss.
    credit: bool
    #: False when the policy's stop sits at a price the market cannot print — a long
    #: structure with a stop above 100% of the premium, which is unreachable because
    #: the mark stops at zero. The level is clamped to zero when this is False, so it
    #: is drawable and true; this flag is what stops it being read as a threshold the
    #: policy would act on.
    stop_reachable: bool = True

    def to_prompt(self) -> dict[str, str | bool]:
        return {"entry": str(self.entry), "target": str(self.target),
                "stop": str(self.stop), "credit": self.credit,
                "stop_reachable": self.stop_reachable}


def exit_levels(entry_price: Decimal, policy: ExitPolicy) -> Levels:
    """The marks at which this policy would close a structure opened at `entry_price`.

    Derived from the same inequalities `evaluate_exit` applies:

        credit:  unrealized >= credit * tp%      ->  mark >= entry * (1 - tp/100)
                 unrealized <= -credit * sl%     ->  mark <= entry * (1 + sl/100)
        debit:   unrealized >= paid * tp%        ->  mark >= entry * (1 + tp/100)
                 unrealized <= -paid * sl%       ->  mark <= entry * (1 - sl/100)

    The multiplier and quantity cancel on both sides, which is why they do not appear:
    a target is a price, not a P&L, and it does not move when you trade ten instead of
    one.

    **A debit's stop is clamped at zero, and `reachable` says whether it can print.**
    The arithmetic above is happy to put a long structure's stop below zero — at a 200%
    stop that is where it lands, because you cannot lose 200% of a premium you have
    already paid. `evaluate_exit` has the same ceiling and it is documented there, but
    the chart is the half that would have been visibly wrong: a stop line drawn at
    -2.99 sits off the bottom of a price axis whose series never goes below zero, and
    a line the market cannot reach is worse than no line, because it looks like
    protection. Clamped to zero it is at least a true statement — a long structure
    expiring worthless is the whole loss — and `reachable` lets the chart say so
    rather than implying the policy would act there.

    This project trades net-credit structures only, so nothing currently opens a debit.
    That is a fact about today's profiles, not about this function.
    """
    tp = policy.take_profit_pct / 100
    sl = policy.stop_loss_pct / 100
    credit = entry_price < 0
    if credit:
        # A rising mark is the loss here, and it has no ceiling: the short leg can be
        # bought back for any price. Every level is reachable.
        return Levels(entry=entry_price, target=entry_price * (1 - tp),
                      stop=entry_price * (1 + sl), credit=True)
    stop = entry_price * (1 - sl)
    return Levels(entry=entry_price, target=entry_price * (1 + tp),
                  stop=max(stop, Decimal(0)), credit=False,
                  stop_reachable=stop >= 0)


def mark_structure(structure: OpenStructure, chain: dict[str, dict]) -> Mark:
    """Current net mark for an open structure, using leg mids.

    Signed the same way entry prices are: positive means it would cost you to be in
    this position (a debit), negative means you hold it for a credit. Incomplete data
    is reported rather than guessed — a mark computed from three of four legs is not a
    mark, and acting on one would be worse than holding.
    """
    total = Decimal(0)
    missing: list[str] = []
    for symbol, signed in structure.legs.items():
        quote = (chain.get(symbol) or {}).get("latestQuote") or {}
        bid, ask = _dec(quote.get("bp")), _dec(quote.get("ap"))
        if bid is None or ask is None or ask <= 0:
            missing.append(symbol)
            continue
        total += (bid + ask) / 2 * signed
    return Mark(value=total, complete=not missing, missing=missing)


@dataclass(frozen=True)
class ExitDecision:
    """Why a position should or should not be closed."""

    structure: OpenStructure
    action: Action
    reason: str
    unrealized_usd: Decimal | None = None
    mark: Decimal | None = None

    @property
    def should_close(self) -> bool:
        return self.action in (
            Action.TAKE_PROFIT, Action.STOP_LOSS, Action.CLOSE_BEFORE_EXPIRY
        )

    def __str__(self) -> str:
        pnl = "" if self.unrealized_usd is None else f" (${self.unrealized_usd:+,.2f})"
        return f"{self.structure.name}: {self.action.value}{pnl} — {self.reason}"


def evaluate_exit(structure: OpenStructure, chain: dict[str, dict], policy: ExitPolicy,
                  *, asof: date | None = None) -> ExitDecision:
    """Decide what to do with one open structure."""
    today = asof or clock.today()
    dte = structure.dte(today)

    # 1. Expiry first, and before anything that needs a mark. A position we cannot
    #    price is still a position we must not carry into expiry.
    if dte is not None and dte <= policy.force_close_dte:
        return ExitDecision(
            structure, Action.CLOSE_BEFORE_EXPIRY,
            f"{dte} DTE, at or inside the {policy.force_close_dte}-day forced-close "
            "window — short gamma and assignment risk, and no greeks at 0DTE",
        )

    if structure.entry_price is None:
        return ExitDecision(
            structure, Action.UNKNOWN,
            "no entry price recorded, so P&L cannot be computed. Close manually or "
            "repair the ledger.",
        )

    mark = mark_structure(structure, chain)
    if not mark.complete:
        return ExitDecision(
            structure, Action.UNKNOWN,
            f"cannot mark {len(mark.missing)} leg(s): {mark.missing[:3]}. Holding "
            "rather than acting on a partial mark.",
        )

    # `mark` and `entry_price` share one sign convention: the value of the position,
    # negative when you hold it for a credit. At the moment of entry they are equal, so
    # P&L is simply how far the mark has moved since.
    #
    # (An earlier version negated the mark here, on the theory that closing "realises
    # -mark". That double-counted the sign and reported a profitable debit spread as a
    # 254% loss. The exit price recorded in the ledger *is* negated, because that is an
    # order price rather than a position value — the two conventions look alike and are
    # not the same thing.)
    unrealized = (mark.value - structure.entry_price) * CONTRACT_MULTIPLIER * structure.qty
    entry_credit = -structure.entry_price * CONTRACT_MULTIPLIER * structure.qty

    if entry_credit > 0:
        # Credit structure: max gain is the credit taken.
        target = entry_credit * policy.take_profit_pct / 100
        stop = entry_credit * policy.stop_loss_pct / 100
        if unrealized >= target:
            return ExitDecision(
                structure, Action.TAKE_PROFIT,
                f"captured ${unrealized:,.2f} of the ${entry_credit:,.2f} credit "
                f"({unrealized / entry_credit * 100:.0f}%, target "
                f"{policy.take_profit_pct:g}%)",
                unrealized, mark.value,
            )
        if unrealized <= -stop:
            return ExitDecision(
                structure, Action.STOP_LOSS,
                f"loss ${-unrealized:,.2f} is {-unrealized / entry_credit * 100:.0f}% of "
                f"the credit taken (stop {policy.stop_loss_pct:g}%)",
                unrealized, mark.value,
            )
    else:
        # Debit structure: the premium paid is the whole risk.
        paid = structure.entry_price * CONTRACT_MULTIPLIER * structure.qty
        if paid > 0:
            if unrealized >= paid * policy.take_profit_pct / 100:
                return ExitDecision(
                    structure, Action.TAKE_PROFIT,
                    f"up ${unrealized:,.2f} on ${paid:,.2f} paid "
                    f"({unrealized / paid * 100:.0f}%, target {policy.take_profit_pct:g}%)",
                    unrealized, mark.value,
                )
            if unrealized <= -paid * policy.stop_loss_pct / 100:
                return ExitDecision(
                    structure, Action.STOP_LOSS,
                    f"down ${-unrealized:,.2f} of ${paid:,.2f} paid "
                    f"({-unrealized / paid * 100:.0f}%, stop {policy.stop_loss_pct:g}%)",
                    unrealized, mark.value,
                )

    return ExitDecision(
        structure, Action.HOLD,
        f"{dte} DTE, unrealized ${unrealized:+,.2f}", unrealized, mark.value,
    )


def closing_order(structure: OpenStructure) -> Structure:
    """The order that flattens an open structure.

    Built from the ledger's own record of which legs were opened together — the broker
    cannot supply this, because it nets legs across structures into one position per
    contract. Closing a condor is one 4-leg order, not four singles: legging out of a
    defined-risk structure re-introduces exactly the risk it was built to bound.
    """
    legs: list[Leg] = []
    for symbol, signed in structure.legs.items():
        if signed == 0:
            continue
        if parse(symbol) is None:
            raise StructureError(f"ledger holds a non-OCC symbol: {symbol}")
        closing_side = Side.SELL if signed > 0 else Side.BUY
        intent = (
            PositionIntent.SELL_TO_CLOSE if signed > 0 else PositionIntent.BUY_TO_CLOSE
        )
        legs.append(Leg(symbol, abs(signed), closing_side, intent))
    if not legs:
        raise StructureError(f"{structure.name} has no open legs to close")
    return Structure(
        name=f"close {structure.name}",
        legs=tuple(legs),
        qty=structure.qty,
    )


def review(ledger: Ledger, chain: dict[str, dict], policy: ExitPolicy,
           *, asof: date | None = None) -> list[ExitDecision]:
    """Every open structure, judged."""
    return [
        evaluate_exit(s, chain, policy, asof=asof) for s in ledger.open_structures
    ]
