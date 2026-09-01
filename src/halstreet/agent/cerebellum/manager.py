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

Four exit conditions, in the order they are checked:

1. **Expiry.** Non-negotiable, and it fires first. A short leg carried into expiry
   week is an assignment problem rather than a pricing one, and Alpaca returns no
   greeks at 0DTE, so a position held that long cannot be risk-assessed even in
   principle. This closes regardless of P&L.
2. **Stop.** A defined-risk structure cannot lose more than its max loss, but waiting
   for that is not a strategy — the last of a max loss is the most expensive and
   least recoverable part of it.
3. **Profit target.** Taking most of the move beats waiting for all of it, because
   the last portion of max gain is bought with the most time and the most risk.
4. **The overnight sweep.** Last, and a veto rather than a reason of its own: near the
   session close, a position that has not earned the hold is flattened. It is checked
   last precisely so a position at its target is reported as having hit its target —
   the journal is what the results are computed from, and it must name the rule that
   took the money. See `_overnight_veto` for the three things that end a hold.

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
from halstreet.agent.hippocampus.ledger import Ledger, OpenStructure
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
    FLATTEN_OVERNIGHT = "flatten_overnight"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExitPolicy:
    """When to close. Separate from `Limits` because these are not entry rules."""

    take_profit_pct: Decimal = Decimal(50)   # of max gain
    stop_loss_pct: Decimal = Decimal(200)    # of credit received / premium paid
    force_close_dte: int = 5

    #: The profit worth holding out for, on any structure that can actually reach it.
    #: `None` disables it and nothing changes.
    #:
    #: A percentage target is a fraction of whatever the structure happened to be worth,
    #: which means a position with $151 of credit in it gets closed for $75. That is
    #: money left on the table: the position had the rest of it available and the
    #: percentage was the only reason to settle.
    #:
    #: So this raises the target rather than adding a second trigger — the distinction
    #: matters and the first version got it backwards. A structure that cannot reach the
    #: figure keeps its percentage target, because a floor nothing can clear would hold
    #: every small winner to expiry. A structure whose percentage already asks for more
    #: keeps that too, for the same reason the figure exists at all.
    take_profit_usd: Decimal | None = None

    #: Close once a position has given back this much of its best-ever gain. `None`
    #: disables it.
    #:
    #: The target rules only ever fire on the way up. A position up $120 that drifts
    #: back to $30 and then into a loss made every dollar of that gain and kept none of
    #: it, and nothing in a profit target or a stop was ever going to catch it — the
    #: stop is measured from the entry, not from the high.
    #:
    #: Two things keep it from being a hair trigger. The peak is a previous cycle's
    #: reading rather than the current one, so a new high is never a giveback; and it
    #: does not arm until the peak clears what the round trip costs, because closing to
    #: protect $8 while paying $15 to do it is not protection.
    giveback_pct: Decimal | None = None

    #: Scalping's one guard rail: a profit target must be worth at least this many
    #: round trips. `None` disables it and nothing changes.
    #:
    #: Taking profit sooner is what makes a scalp a scalp, and it is also how a
    #: strategy pays its edge away without noticing. Friction here is $7.50 a leg, so a
    #: two-leg spread costs $15 to open and close and a condor $30. A 10% target on a
    #: $200 credit asks for $20 — a trade that reports as a win and settles for $5, and
    #: three of those in a session are worse than one loss because nobody looks at them.
    #:
    #: It raises the target rather than refusing the trade. The position is simply held
    #: a little longer, which is the only thing that actually fixes the arithmetic.
    scalp_friction_multiple: Decimal | None = None

    #: Flatten anything that has not earned its overnight hold, this many minutes
    #: before the session close. `None` disables the sweep entirely.
    #:
    #: The competition is scored on P&L over a window, and the overnight gap is the one
    #: risk a defined-risk structure cannot bound: the gates size every position against
    #: a max loss that assumes an orderly market, and a gap does not open in one.
    #:
    #: It is not a nightly flatten, because that arithmetic loses. At $7.50 a leg,
    #: closing a spread tonight and reopening tomorrow costs $15 against roughly $3.50
    #: of decay, so a mechanical sweep pays four days of theta for one night of
    #: comfort. What this closes is the positions that have given no reason to be
    #: carried — see `_overnight_veto` for the three that count.
    flatten_before_close_min: int | None = None

    #: How many losing trades in a row on one (underlying, family) pair before it is
    #: rested, and for how many sessions afterwards. `0` for the count turns the rule
    #: off entirely.
    #:
    #: The agent already tells the model about its losses — the committee's judge is
    #: handed closed structures and their realized P&L. This is the half the model
    #: cannot argue with: `loss_cooldown` refuses the pair outright, and the record it
    #: reads is computed from the ledger rather than remembered.
    #:
    #: Two, not one, because one loss is a trade and two is a pattern; and a pair, not
    #: a symbol, because being wrong twice about calls says nothing about puts.
    loss_cooldown_after: int = 2
    loss_cooldown_days: int = 1

    @classmethod
    def from_env(cls, source: dict[str, str] | None = None) -> ExitPolicy:
        src = os.environ if source is None else source

        def dec(key: str, default: Decimal) -> Decimal:
            raw = (src.get(key) or "").strip()
            return Decimal(raw) if raw else default

        def integer(key: str, default: int) -> int:
            raw = (src.get(key) or "").strip()
            return int(raw) if raw else default

        def opt(key: str) -> Decimal | None:
            raw = (src.get(key) or "").strip()
            return Decimal(raw) if raw else None

        def opt_int(key: str) -> int | None:
            raw = (src.get(key) or "").strip()
            return int(raw) if raw else None

        return cls(
            take_profit_usd=opt("TAKE_PROFIT_USD"),
            giveback_pct=opt("GIVEBACK_PCT"),
            take_profit_pct=dec("TAKE_PROFIT_PCT", cls.take_profit_pct),
            stop_loss_pct=dec("STOP_LOSS_PCT", cls.stop_loss_pct),
            force_close_dte=integer("FORCE_CLOSE_DTE", cls.force_close_dte),
            scalp_friction_multiple=opt("SCALP_FRICTION_MULTIPLE"),
            flatten_before_close_min=opt_int("FLATTEN_BEFORE_CLOSE_MIN"),
            loss_cooldown_after=integer("LOSS_COOLDOWN_AFTER", cls.loss_cooldown_after),
            loss_cooldown_days=integer("LOSS_COOLDOWN_DAYS", cls.loss_cooldown_days),
        )

    def profit_target_usd(self, max_gain_usd: Decimal, *,
                          legs: int | None = None, qty: int = 1) -> Decimal:
        """What this position is being held for, in dollars.

        Three cases and the order is the whole rule:

        * No absolute figure set — the percentage, exactly as before.
        * The figure is more than the structure can ever make — the percentage again.
          A target nothing can clear is not ambition, it is a position held to expiry.
        * Otherwise the larger of the two. The figure is a floor under the percentage,
          not a ceiling over it: on a structure big enough that half its max gain is
          already more than the figure, settling for the figure would be the same
          mistake in the other direction.

        `scalp_friction_multiple` then puts a second floor under the result, for the
        same reason and with the same shape — see the field. It needs `legs` because
        friction is charged per leg per contract; a caller that does not know the leg
        count gets the unfloored answer rather than a guessed one, which is why the
        chart passes it through from the ledger rather than assuming four.
        """
        pct = max_gain_usd * self.take_profit_pct / 100
        target = pct
        if self.take_profit_usd is not None and self.take_profit_usd <= max_gain_usd:
            target = max(pct, self.take_profit_usd)

        if self.scalp_friction_multiple is None or legs is None:
            return target
        floor = round_trip_cost(legs, qty) * self.scalp_friction_multiple
        # Never above what the structure can make: a floor nothing can clear holds the
        # position to expiry, which is the opposite of what a scalp setting is for.
        return max(target, floor) if floor <= max_gain_usd else target

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


def _giveback(structure: OpenStructure, policy: ExitPolicy,
              unrealized: Decimal) -> str | None:
    """Why this position should be closed to protect what it already made, or None.

    Silent on a position that is down. Giving back a gain and taking a loss are
    different acts, and closing here would book a real loss under a rule whose whole
    purpose is protecting a profit — the stop owns that case and is measured from the
    entry, which is the right place to measure a loss from.
    """
    peak = structure.peak_usd
    if policy.giveback_pct is None or peak is None or unrealized <= 0:
        return None
    # Noise below the cost of the round trip is not a gain to protect.
    floor = round_trip_cost(len(structure.legs), structure.qty)
    if peak <= floor:
        return None
    kept = peak * (100 - policy.giveback_pct) / 100
    if unrealized > kept:
        return None
    return (f"up ${unrealized:,.2f}, gave back ${peak - unrealized:,.2f} of a "
            f"${peak:,.2f} peak ({(peak - unrealized) / peak * 100:.0f}%, limit "
            f"{policy.giveback_pct:g}%) — the trade was right and this keeps what it "
            "made rather than watching it become nothing")


def _overnight_veto(unrealized: Decimal, event: bool | None) -> str | None:
    """Why this position may not be carried through the close, or None if it may.

    Three vetoes, and the third is the one worth arguing about.

    A **losing** position is not positive data. The gap is the risk being avoided, and
    a trade already going the wrong way is the worst thing to hand to it — closing
    costs the round trip, which is the price of not finding out.

    A **scheduled event** before the next session is the case where the overnight move
    is not a tail at all but the expected outcome. Nothing in a delta or a spread width
    prices an earnings print.

    A calendar that **could not be read** flattens too, which is the same fail-closed
    rule every gate follows: not knowing whether there is an event tonight is not the
    same as knowing there is none, and only one of those is safe to hold through. This
    is the branch that would quietly become "assume it is quiet" if `None` were ever
    folded into `False`.
    """
    if unrealized < 0:
        return (f"down ${-unrealized:,.2f} into the close — a position going the wrong "
                "way is not data that it is worth the overnight gap")
    if event is None:
        return ("the events calendar could not be read, so an event before the next "
                "session cannot be ruled out — not knowing is not the same as knowing "
                "there is nothing")
    if event:
        return ("a scheduled event before the next session — an overnight print is not "
                "a tail this structure's width was priced for")
    return None


def _target_note(policy: ExitPolicy, max_gain_usd: Decimal, *,
                 legs: int | None = None, qty: int = 1) -> str:
    """Which rule set the target this position was closed on.

    Named rather than assumed: a reason that says "target 50%" while a dollar floor did
    the closing is a diagnostic stating something false, which Constitution VII does not
    allow whether or not anyone would have noticed. The friction floor is a third rule
    that can set it, and it says so — "target $30 (2x round trip)" is the difference
    between a reader understanding the exit and guessing at it.
    """
    target = policy.profit_target_usd(max_gain_usd, legs=legs, qty=qty)
    if legs is not None and policy.scalp_friction_multiple is not None:
        floor = round_trip_cost(legs, qty) * policy.scalp_friction_multiple
        if target == floor:
            return (f"target ${floor:,.2f}, "
                    f"{policy.scalp_friction_multiple:g}x the round trip")
    if policy.take_profit_usd is not None and target == policy.take_profit_usd:
        return f"target ${policy.take_profit_usd:,.2f}"
    return f"target {policy.take_profit_pct:g}%"


def exit_levels(entry_price: Decimal, policy: ExitPolicy, *, qty: int = 1,
                legs: int | None = None) -> Levels:
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

    def target_mark(pct_target: Decimal) -> Decimal:
        """The mark the policy's dollar target corresponds to.

        Same `profit_target_usd` the exit acts on, converted into mark space — the
        chart's whole claim is that it cannot disagree with the rule, so it may not
        carry a second copy of the arithmetic.

        P&L rises with the mark for a credit and a debit alike, since `unrealized` is
        `(mark - entry) * multiplier * qty` in both, so one conversion covers each.

        This is the one place quantity does not cancel. A percentage target is a price
        and does not move when you trade ten instead of one; a dollar target is reached
        ten times sooner, so the line sits nearer the entry.
        """
        # Both rules that can raise the target off the percentage have to be asked,
        # not just the dollar one. This early-out read `take_profit_usd is None` while
        # that was the only such rule; the friction floor is a second, and a level
        # function that did not know about it would draw a line the exit does not act
        # on — which is the failure this whole conversion exists to prevent.
        floored = policy.scalp_friction_multiple is not None and legs is not None
        if (policy.take_profit_usd is None and not floored) or qty <= 0:
            return pct_target
        max_gain = abs(entry_price) * CONTRACT_MULTIPLIER * qty
        target = policy.profit_target_usd(max_gain, legs=legs, qty=qty)
        return entry_price + target / (CONTRACT_MULTIPLIER * qty)

    if credit:
        # A rising mark is the loss here, and it has no ceiling: the short leg can be
        # bought back for any price. Every level is reachable.
        return Levels(entry=entry_price, target=target_mark(entry_price * (1 - tp)),
                      stop=entry_price * (1 + sl), credit=True)
    stop = entry_price * (1 - sl)
    return Levels(entry=entry_price, target=target_mark(entry_price * (1 + tp)),
                  stop=max(stop, Decimal(0)), credit=False,
                  stop_reachable=stop >= 0)


@dataclass(frozen=True)
class LegMark:
    """One leg of a structure, priced — and its share of the position's P&L.

    The panel wants this because "the spread is ten dollars down" invites exactly one
    follow-up question, and until now nothing could answer it: the ledger recorded the
    net and threw the legs away.

    `basis` is what this leg actually filled at on the opening order, per contract,
    positive on both sides — see `execution.fills`. It is `None` for a structure
    opened before per-leg fills were kept, and the P&L is `None` with it rather than
    being invented from the net.
    """

    symbol: str
    #: Signed contracts *per structure*, before size. `qty` scales it, exactly as it
    #: does for the net — keeping the two in step is why `pnl` takes the structure.
    signed: int
    bid: Decimal | None
    ask: Decimal | None
    basis: Decimal | None = None

    @property
    def mid(self) -> Decimal | None:
        """The same mid `mark_structure` sums, or `None` on the same conditions.

        A one-sided or zero-ask quote is not a price. This is the single definition of
        that judgement; the net is built from these, so a leg the panel shows as
        unpriced is a leg the net is refusing to include.
        """
        if self.bid is None or self.ask is None or self.ask <= 0:
            return None
        return (self.bid + self.ask) / 2

    @property
    def priced(self) -> bool:
        return self.mid is not None

    def value(self, qty: int) -> Decimal | None:
        """What this leg contributes to the position's current value, in dollars.

        Negative for a short leg: it is what you would have to pay to be rid of it.
        """
        mid = self.mid
        return None if mid is None else mid * self.signed * qty * CONTRACT_MULTIPLIER

    def pnl(self, qty: int) -> Decimal | None:
        """This leg's unrealized P&L in dollars, from its own fill.

        `(mid - basis) * signed`: a short leg carries a negative `signed`, so it makes
        money when its mid falls below what it was sold for, which is the right sign
        without a special case.

        These sum to the structure's unrealized P&L exactly, because the leg fills sum
        to the net fill and the leg mids sum to the net mark. That identity is pinned
        by test — the instant it stops holding, one of the two numbers on the screen is
        wrong and there is no way to tell which.
        """
        mid, basis = self.mid, self.basis
        if mid is None or basis is None:
            return None
        return (mid - basis) * self.signed * qty * CONTRACT_MULTIPLIER


def mark_legs(structure: OpenStructure, chain: dict[str, dict]) -> list[LegMark]:
    """Every leg of a structure, priced from the chain, in the ledger's own order.

    The parts `mark_structure` is built out of. Written this way round so the legs and
    the net cannot disagree about what a mid is or which legs are missing: there is
    one arithmetic, and the net is its sum.
    """
    fills = structure.entry_legs or {}
    return [
        LegMark(
            symbol=symbol,
            signed=signed,
            bid=_dec(((chain.get(symbol) or {}).get("latestQuote") or {}).get("bp")),
            ask=_dec(((chain.get(symbol) or {}).get("latestQuote") or {}).get("ap")),
            basis=fills.get(symbol),
        )
        for symbol, signed in structure.legs.items()
    ]


@dataclass(frozen=True)
class StructureGreeks:
    """Net delta and vega for one held structure, and which legs could not answer.

    Shaped like `Mark`, and for the same reason: an incomplete reading is reported as
    incomplete rather than as a smaller number. A net that quietly dropped a leg with
    no greeks would describe a position the account is not carrying.
    """

    delta: Decimal
    vega: Decimal
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


def structure_greeks(structure: OpenStructure, chain: dict[str, dict]) -> StructureGreeks:
    """What this one structure is doing to the book's delta and vega.

    `portfolio_greek_bounds` answers the book-level version of this question and is the
    one that can reject a trade; this is the per-position view the panel draws, and it
    deliberately uses the gate's units so a reader is never converting between two
    conventions on one screen. **Delta is share-equivalents** — signed contracts times
    the multiplier — because that is the number that says what the position does when
    the tape moves a dollar. **Vega is per contract**, unmultiplied, because it is
    already quoted per point of implied volatility.

    Fails closed on a missing greek, exactly as the gate does. Alpaca omits them where
    inverting Black-Scholes is ill-conditioned, and entirely at 0DTE.
    """
    delta = Decimal(0)
    vega = Decimal(0)
    missing: list[str] = []

    for symbol, signed in structure.legs.items():
        greeks = (chain.get(symbol) or {}).get("greeks")
        d = _dec((greeks or {}).get("delta"))
        v = _dec((greeks or {}).get("vega"))
        if d is None or v is None:
            missing.append(symbol)
            continue
        contracts = Decimal(signed * structure.qty)
        delta += d * contracts * CONTRACT_MULTIPLIER
        vega += v * contracts

    return StructureGreeks(delta=delta, vega=vega, missing=tuple(missing))


def mark_structure(structure: OpenStructure, chain: dict[str, dict]) -> Mark:
    """Current net mark for an open structure, using leg mids.

    Signed the same way entry prices are: positive means it would cost you to be in
    this position (a debit), negative means you hold it for a credit. Incomplete data
    is reported rather than guessed — a mark computed from three of four legs is not a
    mark, and acting on one would be worse than holding.

    The sum of `mark_legs`, rather than its own second walk of the chain. When the
    panel began showing per-leg prices there were briefly going to be two versions of
    "what is a usable quote", and two versions of that rule is how a leg table comes to
    show four prices under a mark that says it only has three.
    """
    total = Decimal(0)
    missing: list[str] = []
    for leg in mark_legs(structure, chain):
        mid = leg.mid
        if mid is None:
            missing.append(leg.symbol)
            continue
        total += mid * leg.signed
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
        """Whether the loop turns this decision into a closing order.

        Written as "everything except the two that are not instructions" rather than as
        a list of the ones that are. The list version was silently wrong the day
        `FLATTEN_OVERNIGHT` was added: the decision was journalled, read as a rule that
        had fired, and the position was still on the book in the morning. A new action
        now has to be argued *into* the holding set instead of being forgotten out of
        the closing one.
        """
        return self.action not in (Action.HOLD, Action.UNKNOWN)

    def __str__(self) -> str:
        pnl = "" if self.unrealized_usd is None else f" (${self.unrealized_usd:+,.2f})"
        return f"{self.structure.name}: {self.action.value}{pnl} — {self.reason}"


def evaluate_exit(structure: OpenStructure, chain: dict[str, dict], policy: ExitPolicy,
                  *, asof: date | None = None,
                  minutes_to_close: float | None = None,
                  event_before_next_session: bool | None = None) -> ExitDecision:
    """Decide what to do with one open structure.

    Pure, and the two overnight arguments are why they are arguments: the minutes come
    from the *broker's* clock and the event flag from the calendar, both of which are
    I/O this function must not do. `minutes_to_close=None` means nobody asked the
    clock, and the sweep then never arms — a flatten decided against a guess about what
    time it is would be worse than no flatten at all.
    """
    today = asof or clock.today()
    dte = structure.dte(today)

    # 0. Is this a position at all? The ledger records on acceptance, so an order still
    #    resting at its limit sits here looking like everything else — and its
    #    `entry_price` is the limit we *asked* for, so the `entry_price is None` guard
    #    below does not catch it. Everything after that point would mark a phantom
    #    against a price nobody paid, and `should_close` reaches `_close`, which submits
    #    a closing order for contracts the account does not hold. That either bounces or
    #    opens a short, and the second is worse than the first.
    #
    #    Before the expiry branch, deliberately: that one acts without looking at a
    #    price at all, so it is the single path that would close a phantom with no mark
    #    involved. An unfilled order near expiry wants cancelling, which is a human's
    #    act and not this function's — so it says so rather than holding silently.
    if not structure.entry_filled:
        return ExitDecision(
            structure, Action.UNKNOWN,
            "the entry order has not filled, so there is no position to manage. "
            "Cancel the working order if it is no longer wanted — closing is not the "
            "same act and would sell contracts the account does not hold.",
        )

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

    # Protecting a gain comes before the targets, because it is the only rule here that
    # looks at where the position has *been*. The targets fire on the way up and this is
    # a failure on the way down; checked after them it would be unreachable on exactly
    # the positions that need it, the ones that peaked below their target.
    given_back = _giveback(structure, policy, unrealized)
    if given_back is not None:
        return ExitDecision(structure, Action.TAKE_PROFIT, given_back,
                            unrealized, mark.value)

    if entry_credit > 0:
        # Credit structure: max gain is the credit taken.
        target = policy.profit_target_usd(entry_credit, legs=len(structure.legs),
                                          qty=structure.qty)
        stop = entry_credit * policy.stop_loss_pct / 100
        if unrealized >= target:
            note = _target_note(policy, entry_credit, legs=len(structure.legs),
                                qty=structure.qty)
            return ExitDecision(
                structure, Action.TAKE_PROFIT,
                f"captured ${unrealized:,.2f} of the ${entry_credit:,.2f} credit "
                f"({unrealized / entry_credit * 100:.0f}%, {note})",
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
            if unrealized >= policy.profit_target_usd(
                    paid, legs=len(structure.legs), qty=structure.qty):
                note = _target_note(policy, paid, legs=len(structure.legs),
                                    qty=structure.qty)
                return ExitDecision(
                    structure, Action.TAKE_PROFIT,
                    f"up ${unrealized:,.2f} on ${paid:,.2f} paid "
                    f"({unrealized / paid * 100:.0f}%, {note})",
                    unrealized, mark.value,
                )
            if unrealized <= -paid * policy.stop_loss_pct / 100:
                return ExitDecision(
                    structure, Action.STOP_LOSS,
                    f"down ${-unrealized:,.2f} of ${paid:,.2f} paid "
                    f"({-unrealized / paid * 100:.0f}%, stop {policy.stop_loss_pct:g}%)",
                    unrealized, mark.value,
                )

    # Last, deliberately. Every rule above closes for a reason of its own, and a
    # position at its target that got reported as an overnight flatten would name the
    # wrong rule for the money in the journal the results are computed from.
    if (policy.flatten_before_close_min is not None and minutes_to_close is not None
            and minutes_to_close <= policy.flatten_before_close_min):
        veto = _overnight_veto(unrealized, event_before_next_session)
        if veto is not None:
            return ExitDecision(structure, Action.FLATTEN_OVERNIGHT, veto,
                                unrealized, mark.value)
        return ExitDecision(
            structure, Action.HOLD,
            f"held through the close: {dte} DTE, up ${unrealized:,.2f}, no scheduled "
            "event before the next session",
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
           *, asof: date | None = None, minutes_to_close: float | None = None,
           events_by_underlying: dict[str, bool | None] | None = None) -> list[ExitDecision]:
    """Every open structure, judged.

    One clock reading covers the whole book — the session closes once — while the
    events answer is per name, so it arrives keyed by underlying. A name absent from
    the mapping is one the calendar did not answer for, which `.get` returns as `None`
    and the veto treats as unknown: the fail-closed default falls out of the lookup
    rather than depending on every caller remembering to fill the map.
    """
    events = events_by_underlying or {}
    return [
        evaluate_exit(s, chain, policy, asof=asof, minutes_to_close=minutes_to_close,
                      event_before_next_session=events.get(s.underlying))
        for s in ledger.open_structures
    ]
