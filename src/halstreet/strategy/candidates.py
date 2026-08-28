"""Deterministic candidate construction and ranking.

Everything here is arithmetic over a chain. No model, no network, no randomness — the
same chain and the same market view produce the same ranked menu, which is what makes
the proposals downstream auditable: when the journal says the agent chose a 762/757
put spread, this module can be re-run against the recorded chain to show that
structure was on the menu, what it looked like, and why it ranked where it did.

**Construction** builds well-formed, correctly-priced structures at sensible strikes.
**Ranking** is `scoring`, the six-term blend ported from TradeScans — bias fit, IV
regime fit, liquidity, reward/risk, probability of profit, and an event-risk penalty,
weighted by the active risk profile. Every candidate carries its own score breakdown,
so the menu is not merely ordered, it is ordered for reasons that survive into the
journal.

Strikes are chosen by **delta**, not by distance in dollars. A 5-point wing means
something different on a $60 stock than on a $760 index, whereas a 0.20-delta short
strike means roughly the same thing everywhere — and Alpaca gives us greeks, so there
is no reason to approximate.

Prices are conservative by construction: **sell at the bid, buy at the ask**. Quoting
a structure at mid and then discovering the fill is worse is the standard way to talk
yourself into a trade that never had the edge you thought it did. The distance
between that and mid is carried separately as `slippage_usd`, where the ranking can
see it and charge for it.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from halstreet import clock
from halstreet.marketdata import occ
from halstreet.marketdata.chain import daily_volume
from halstreet.marketdata.occ import (
    CONTRACT_MULTIPLIER,
    Contract,
    PayoffLeg,
    Right,
    parse,
)
from halstreet.strategy import montecarlo, scoring
from halstreet.strategy import pop as pop_math
from halstreet.strategy import profiles as P


def _dec(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Quote:
    """One contract, reduced to what candidate construction needs."""

    contract: Contract
    bid: Decimal
    ask: Decimal
    delta: Decimal | None
    open_interest: int | None
    volume: int | None
    # Implied volatility as a fraction (0.1325 = 13.25%), per contract. Used only to
    # compute probability of profit; never to price a leg.
    iv: Decimal | None = None

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> Decimal | None:
        return None if self.mid <= 0 else (self.ask - self.bid) / self.mid * 100

    @property
    def half_spread_usd(self) -> Decimal:
        """What crossing from mid to the touch costs on this leg, per contract."""
        return (self.ask - self.bid) / 2 * CONTRACT_MULTIPLIER


@dataclass
class Candidate:
    """A priced, well-formed structure ready to be offered to the model."""

    name: str
    kind: str
    legs: list[dict[str, Any]]
    net: Decimal              # per share; positive = debit, negative = credit
    max_loss_usd: Decimal
    max_gain_usd: Decimal
    dte: int
    short_delta: Decimal | None = None
    worst_spread_pct: Decimal | None = None
    min_open_interest: int | None = None
    min_volume: int | None = None
    # One-way cost of paying the spread on entry, across all legs.
    slippage_usd: Decimal | None = None
    # Probability of finishing profitable at expiry. None when it cannot be computed
    # — a missing IV, say — which the ranking treats as a disadvantage, not a pass.
    pop: float | None = None
    score: Decimal = field(default=Decimal(0))
    breakdown: scoring.ScoreBreakdown | None = None
    #: Sampled outcomes at expiry, at both the market's volatility and the tape's.
    #: None when neither could be measured, which the ranking and the model both read
    #: as "unknown" rather than as "unremarkable".
    scenario: montecarlo.Outlook | None = None
    # The underlying quotes, kept for per-leg liquidity checks. Not serialised: the
    # model gets the summary statistics, not the raw chain it would drown in.
    quotes: tuple[tuple[Quote, str], ...] = field(default=(), repr=False)

    def to_prompt(self) -> dict[str, Any]:
        """The shape handed to the model — priced and ranked, with no advice attached."""
        return {
            "name": self.name,
            "kind": self.kind,
            "legs": self.legs,
            "net_price": str(self.net),
            "max_loss_usd": str(self.max_loss_usd),
            "max_gain_usd": str(self.max_gain_usd),
            "dte": self.dte,
            "short_delta": None if self.short_delta is None else str(self.short_delta),
            "worst_leg_spread_pct": (
                None if self.worst_spread_pct is None else f"{self.worst_spread_pct:.1f}"
            ),
            "min_open_interest": self.min_open_interest,
            "min_daily_volume": self.min_volume,
            "entry_slippage_usd": (
                None if self.slippage_usd is None else f"{self.slippage_usd:.2f}"
            ),
            "prob_of_profit": None if self.pop is None else round(self.pop, 3),
            "score": str(self.score),
            "score_breakdown": None if self.breakdown is None else self.breakdown.to_prompt(),
            # Sampled outcomes, with the assumption they were sampled under. The model
            # was already reasoning about expectation and tail size in prose; this is
            # the arithmetic it was doing in its head.
            "scenario": None if self.scenario is None else self.scenario.to_prompt(),
        }

    @property
    def shorts(self) -> list[Quote]:
        return [q for q, side in self.quotes if side == "sell"]


def quotes_for(chain: dict[str, dict], expiry: date) -> list[Quote]:
    """Every quotable contract at one expiry, sorted by strike."""
    out: list[Quote] = []
    for symbol, snapshot in chain.items():
        contract = parse(symbol)
        if contract is None or contract.expiry != expiry:
            continue
        quote = snapshot.get("latestQuote") or {}
        bid, ask = _dec(quote.get("bp")), _dec(quote.get("ap"))
        if bid is None or ask is None or ask <= 0 or ask < bid:
            continue
        greeks = snapshot.get("greeks") or {}
        out.append(
            Quote(
                contract=contract,
                bid=bid,
                ask=ask,
                delta=_dec(greeks.get("delta")),
                open_interest=snapshot.get("openInterest"),
                volume=daily_volume(snapshot),
                iv=_dec(snapshot.get("impliedVolatility")),
            )
        )
    return sorted(out, key=lambda q: q.contract.strike)


def expiries_by_distance(chain: dict[str, dict], target_dte: int, *,
                         asof: date | None = None, min_dte: int = 7) -> list[date]:
    """Every listed expiry at or beyond `min_dte`, closest to `target_dte` first.

    A list rather than one answer, because *closest* and *usable* are different
    questions and only the caller can settle the second — see `generate`.
    """
    today = asof or clock.today()
    expiries = {
        c.expiry for s in chain if (c := parse(s)) and (c.expiry - today).days >= min_dte
    }
    return sorted(expiries, key=lambda e: (abs((e - today).days - target_dte), e))


def nearest_expiry(chain: dict[str, dict], target_dte: int, *, asof: date | None = None,
                   min_dte: int = 7) -> date | None:
    """The listed expiry closest to `target_dte`, never nearer than `min_dte`.

    The floor is here as well as in the gates on purpose: offering the model an expiry
    the DTE gate will reject wastes a whole cycle, and an agent that keeps proposing
    trades it cannot make looks broken even when it is behaving correctly.

    Closeness alone is not enough to trade on, which is why `generate` walks
    `expiries_by_distance` instead of calling this. Kept because "the nearest listed
    expiry" is still the right answer to that question.
    """
    found = expiries_by_distance(chain, target_dte, asof=asof, min_dte=min_dte)
    return found[0] if found else None


def _by_delta(quotes: list[Quote], right: Right, target: Decimal) -> Quote | None:
    """The contract whose delta is closest to `target` (absolute value)."""
    pool = [q for q in quotes if q.contract.right is right and q.delta is not None]
    if not pool:
        return None
    return min(pool, key=lambda q: abs(abs(q.delta) - target))


def _neighbour(quotes: list[Quote], anchor: Quote, steps: int) -> Quote | None:
    """The contract `steps` strikes away from `anchor`, same right."""
    same = [q for q in quotes if q.contract.right is anchor.contract.right]
    try:
        i = same.index(anchor)
    except ValueError:
        return None
    j = i + steps
    return same[j] if 0 <= j < len(same) else None


def _leg(quote: Quote, side: str) -> dict[str, Any]:
    return {"symbol": quote.contract.symbol, "side": side, "ratio_qty": 1}


def _stats(legs: list[Quote]) -> tuple[Decimal | None, int | None, int | None, Decimal]:
    spreads = [q.spread_pct for q in legs if q.spread_pct is not None]
    ois = [q.open_interest for q in legs if q.open_interest is not None]
    vols = [q.volume for q in legs if q.volume is not None]
    return (
        max(spreads) if spreads else None,
        min(ois) if len(ois) == len(legs) else None,
        min(vols) if len(vols) == len(legs) else None,
        sum((q.half_spread_usd for q in legs), Decimal(0)),
    )


def credit_spread(quotes: list[Quote], right: Right, short_delta: Decimal,
                  width_steps: int, dte: int, *, spot: Decimal | None = None) -> Candidate | None:
    """A short vertical: sell near the money, buy further out for the wing."""
    short = _by_delta(quotes, right, short_delta)
    if short is None:
        return None
    direction = 1 if right is Right.CALL else -1
    long_ = _neighbour(quotes, short, direction * width_steps)
    if long_ is None or long_.contract.strike == short.contract.strike:
        return None

    credit = short.bid - long_.ask
    if credit <= 0:
        return None
    width = abs(long_.contract.strike - short.contract.strike)
    max_loss = (width - credit) * CONTRACT_MULTIPLIER
    if max_loss <= 0:
        return None

    kind = P.CALL_CREDIT if right is Right.CALL else P.PUT_CREDIT
    worst, oi, vol, slip = _stats([short, long_])
    prob = _spread_pop(kind, short, credit, dte, spot)
    return Candidate(
        # The root leads. The name is the structure's identity everywhere it appears
        # afterwards — the journal, the panel, the ledger, the write-up's results —
        # and without it "2026-10-16 765/775 call credit spread" says nothing about
        # which underlying is at risk. The event carries `underlying` beside it, but
        # anything rendering the name alone had no way to know, and a book holding
        # three names that differ only by strike is unreadable.
        name=f"{short.contract.root} {short.contract.expiry} "
             f"{short.contract.strike:g}/{long_.contract.strike:g} "
             f"{'call' if right is Right.CALL else 'put'} credit spread",
        kind=kind,
        legs=[_leg(short, "sell"), _leg(long_, "buy")],
        net=-credit,
        max_loss_usd=max_loss,
        max_gain_usd=credit * CONTRACT_MULTIPLIER,
        dte=dte,
        short_delta=abs(short.delta) if short.delta is not None else None,
        worst_spread_pct=worst,
        min_open_interest=oi,
        min_volume=vol,
        slippage_usd=slip,
        pop=prob,
        quotes=((short, "sell"), (long_, "buy")),
    )


def _spread_pop(kind: str, short: Quote, credit: Decimal, dte: int,
                spot: Decimal | None) -> float | None:
    """POP for a credit vertical, or None when spot or IV is missing."""
    if spot is None or short.iv is None or short.iv <= 0:
        return None
    fn = pop_math.credit_call_spread if kind == P.CALL_CREDIT else pop_math.credit_put_spread
    return fn(float(spot), float(short.contract.strike), float(credit), dte, float(short.iv))


def iron_condor(quotes: list[Quote], short_delta: Decimal, width_steps: int,
                dte: int, *, spot: Decimal | None = None) -> Candidate | None:
    """Both credit spreads at once. Four legs — exactly Alpaca's ceiling."""
    put = credit_spread(quotes, Right.PUT, short_delta, width_steps, dte, spot=spot)
    call = credit_spread(quotes, Right.CALL, short_delta, width_steps, dte, spot=spot)
    if put is None or call is None:
        return None

    credit = -(put.net + call.net)
    if credit <= 0:
        return None
    # Only one side can lose, so risk is the wider wing less the total credit taken.
    widest = max(put.max_loss_usd + put.max_gain_usd, call.max_loss_usd + call.max_gain_usd)
    max_loss = widest - credit * CONTRACT_MULTIPLIER
    if max_loss <= 0:
        return None

    short_put, short_call = put.shorts[0], call.shorts[0]
    # A condor whose short strikes crossed is not a condor. This cannot happen with
    # a sane chain, but a delta target near 0.50 on a skewed surface can pick short
    # strikes on the wrong sides of spot, and the structure would be nonsense.
    if short_put.contract.strike >= short_call.contract.strike:
        return None

    legs = [put.legs[1], put.legs[0], call.legs[0], call.legs[1]]
    quads = (put.quotes[1], put.quotes[0], call.quotes[0], call.quotes[1])
    worst, oi, vol, slip = _stats([q for q, _ in quads])

    prob = None
    if spot is not None and short_put.iv and short_call.iv:
        prob = pop_math.iron_condor(
            float(spot), float(short_put.contract.strike), float(short_call.contract.strike),
            float(credit), dte, float(short_put.iv), float(short_call.iv),
        )

    return Candidate(
        name=f"{short_put.contract.root} {short_put.contract.expiry} "
             f"{short_put.contract.strike:g}/"
             f"{short_call.contract.strike:g} iron condor",
        kind=P.IRON_CONDOR,
        legs=legs,
        net=-credit,
        max_loss_usd=max_loss,
        max_gain_usd=credit * CONTRACT_MULTIPLIER,
        dte=dte,
        short_delta=put.short_delta,
        worst_spread_pct=worst,
        min_open_interest=oi,
        min_volume=vol,
        slippage_usd=slip,
        pop=prob,
        quotes=quads,
    )


def score(candidate: Candidate, ctx: scoring.Context) -> scoring.ScoreBreakdown:
    """Rank one candidate. See `scoring` for what the six terms mean."""
    return scoring.score(
        dte=candidate.dte,
        kind=candidate.kind,
        max_gain_usd=float(candidate.max_gain_usd),
        max_loss_usd=float(candidate.max_loss_usd),
        slippage_usd=None if candidate.slippage_usd is None else float(candidate.slippage_usd),
        pop=candidate.pop,
        ctx=ctx,
    )


def viable(candidate: Candidate) -> bool:
    """Whether the structure can win at all once the spread is paid.

    Entry slippage at or above max gain means the best case is already spent
    crossing the market — and that is the *one-way* cost, so the round trip is worse
    still. Nothing downstream catches this: the gates judge risk, not edge, and a
    structure risking $186 to make $14 while paying $32 to get in passes every one of
    them. It is the strategy layer's job to not offer it.

    Observed live rather than reasoned about: a QQQ 710/708 put spread came off the
    chain at $14 max gain against $32.50 of entry slippage, and was the only thing on
    that cycle's menu.

    This is a floor, not a standard. It only removes structures that cannot win at
    all; judging whether the remaining edge is *worth* taking is the model's call,
    informed by the friction figure in its prompt.
    """
    if candidate.max_gain_usd <= 0:
        return False
    if candidate.slippage_usd is None:
        return True
    return candidate.slippage_usd < candidate.max_gain_usd


def leg_ok(quote: Quote, floor: P.EffectiveFloor) -> bool:
    """Whether one contract clears every liquidity floor. Fails closed on unknowns.

    Extracted so there is one definition of the question. `tradeable` asks it of every
    leg of a built structure; discovery asks it of a bare chain, before a symbol is
    given one of the scan's slots. Two implementations of "is this leg liquid" would
    be two answers, and the day they disagreed the agent would scan a name it had
    already decided it could not trade.
    """
    if quote.open_interest is None or quote.open_interest < floor.min_open_interest:
        return False
    if quote.volume is None or quote.volume < floor.min_daily_volume:
        return False
    spread = quote.spread_pct
    return spread is not None and spread <= floor.max_spread_pct


def tradeable(candidate: Candidate, floor: P.EffectiveFloor) -> bool:
    """Whether the liquidity gate would accept every leg of this structure.

    Applied before the menu is built, for the same reason the DTE floor is: offering
    the model a structure that is certain to be rejected burns the whole cycle, and an
    agent that keeps proposing trades it cannot make looks broken even when every part
    of it is behaving correctly.

    This is not a second implementation of the gate. It is a pre-filter using limits
    the gate has already clamped (`EffectiveFloor.compose`); the gate still runs
    afterwards and is still the authority. Fails closed on unknown values, exactly as
    the gate does.

    Spread is judged **per leg**, not on the structure's worst leg alone. The two
    coincide today — the ceiling is a flat percentage, so the worst leg decides — but
    writing it per leg means a mid-dependent rule can be introduced in the gate later
    without this pre-filter silently continuing to apply the old one.
    """
    if not candidate.quotes:
        return False
    return all(leg_ok(quote, floor) for quote, _side in candidate.quotes)


def generate(chain: dict[str, dict], *, spot: Decimal | None = None,
             target_dte: int = 45, limits=None, profile: P.Profile | None = None,
             ctx: scoring.Context | None = None, limit: int = 6,
             width_steps: tuple[int, ...] = (1, 2, 4),
             asof: date | None = None) -> list[Candidate]:
    """Build and rank the menu handed to the model.

    Returns at most `limit` candidates, best-scoring first. Keeping the menu short is
    not only about tokens: a model given forty near-identical structures will pick
    between them on noise.

    `limits` is a `gates.base.Limits`; combined with the profile it produces the
    effective floor, which is the stricter of the two on every dimension. Passing a
    profile alone cannot loosen anything.
    """
    from halstreet.gates.base import Limits

    profile = profile or P.DEFAULT_PROFILE
    limits = limits if limits is not None else Limits()
    ctx = ctx or scoring.Context(weights=profile.weights)
    floor = P.EffectiveFloor.compose(profile, limits)

    dte_target = profile.target_dte(target_dte)
    today = asof or clock.today()
    for expiry in expiries_by_distance(chain, dte_target, asof=asof,
                                       min_dte=floor.min_dte)[:MAX_EXPIRIES_TRIED]:
        menu = _menu_for(chain, expiry, spot=spot, dte=(expiry - today).days,
                         profile=profile, floor=floor, ctx=ctx, limit=limit,
                         width_steps=width_steps)
        if menu:
            return menu
    return []


#: How many expiries `generate` will try before giving up on a cycle.
#:
#: One was the bug. `generate` took the expiry closest to the target DTE and returned
#: an empty menu if nothing could be built on it — and on a live SPY chain the closest
#: expiry was a stub: 2026-10-09 carried 58 contracts spanning |delta| 0.30 to 0.72,
#: with no strike anywhere near the 0.20 delta the profile sells. 2026-10-16 sat seven
#: days further out, comfortably inside the same 21-60 band, and carried 442 contracts
#: across the full ladder. Closeness won, nothing could be built, and the cycle
#: produced no menu, no proposal and no decision — for all three underlyings at once,
#: with nothing in the journal but `candidates: 0`.
#:
#: Three is enough to step over a thinly-listed weekly without wandering to an expiry
#: nobody asked for; the DTE floor and the profile's band still bound where it can go.
MAX_EXPIRIES_TRIED = 3


def _menu_for(chain: dict[str, dict], expiry: date, *, spot: Decimal | None, dte: int,
              profile: P.Profile, floor: P.EffectiveFloor, ctx: scoring.Context,
              limit: int, width_steps: tuple[int, ...]) -> list[Candidate]:
    """Build and rank the menu for one expiry. Empty means this expiry is unusable."""
    quotes = quotes_for(chain, expiry)
    if not quotes:
        return []

    out: list[Candidate] = []
    for delta in profile.short_deltas:
        for steps in width_steps:
            for right in (Right.CALL, Right.PUT):
                kind = P.CALL_CREDIT if right is Right.CALL else P.PUT_CREDIT
                if not profile.builds(kind):
                    continue
                if (c := credit_spread(quotes, right, delta, steps, dte, spot=spot)) is not None:
                    out.append(c)
            if profile.builds(P.IRON_CONDOR) and (
                    c := iron_condor(quotes, delta, steps, dte, spot=spot)) is not None:
                out.append(c)

    seen: set[tuple] = set()
    unique: list[Candidate] = []
    for c in out:
        key = tuple(leg["symbol"] for leg in c.legs)
        if key in seen:
            continue
        seen.add(key)
        if not viable(c) or not tradeable(c, floor):
            continue
        c.breakdown = score(c, ctx)
        c.score = scoring.as_decimal(c.breakdown.total)
        c.scenario = scenario_for(c, spot=spot, vol=ctx.realized_vol)
        unique.append(c)

    # Ties broken by POP, then by name — so the same chain always produces the same
    # order rather than whatever the dict happened to iterate.
    unique.sort(key=lambda c: (c.score, c.pop or 0.0, c.name), reverse=True)
    return diversify(unique, limit)


def payoff_legs(candidate: Candidate) -> list[PayoffLeg]:
    """The legs reduced to what an expiry payoff depends on.

    Empty when any leg cannot be parsed, rather than partial. A structure simulated
    with one of its wings missing is not a conservative estimate of that structure; it
    is a confident estimate of a different and far riskier one.
    """
    out: list[PayoffLeg] = []
    for leg in candidate.legs:
        contract = occ.parse(str(leg.get("symbol")))
        if contract is None:
            return []
        out.append(PayoffLeg(right=contract.right, strike=contract.strike,
                             ratio=int(leg.get("ratio_qty") or 1),
                             long=str(leg.get("side")) == "buy"))
    return out


def scenario_for(candidate: Candidate, *, spot: Decimal | None,
                 vol: float | None) -> montecarlo.Scenario | None:
    """Sample this structure's outcomes, or None where it cannot honestly be sampled.

    Seeded from the structure's own name, so the same chain always produces the same
    figures: these are journalled, and a record nobody can reproduce is not a record.

    Friction is **one** crossing, not two, and the missing half is already paid.
    `credit = short.bid - long.ask` — the worst of both touches — so what a candidate
    carries as `net` is the money that actually arrives after getting in. Charging
    `slippage_usd` again on entry deducted it twice and made every structure on every
    menu look worse than it is, in the one direction that stops an agent trading.

    What remains owed is the exit. The simulation settles at expiry, where there is no
    exit trade at all; the book does not hold to expiry — the manager takes profit at
    50% and force-closes at 5 DTE — so one crossing out is the honest charge and the
    expiry model is the reason it has to be added by hand.
    """
    legs = payoff_legs(candidate)
    if not legs or spot is None:
        return None
    slip = candidate.slippage_usd or Decimal(0)
    out = montecarlo.outlook(
        legs=legs, net=candidate.net, spot=spot, dte=candidate.dte,
        vol_realized=vol, vol_implied=short_iv(candidate),
        friction_usd=slip, seed=zlib.crc32(candidate.name.encode()),
    )
    return out if (out.at_implied or out.at_realized) else None


def short_iv(candidate: Candidate) -> float | None:
    """The implied volatility the credit was quoted at, from the legs being sold.

    The short strikes, because they are what the structure is paid for. A condor has
    two and takes their mean — one number for a one-volatility model, which ignores
    skew and is worth naming: index put skew is steep enough that the downside tail is
    fatter than a shared vol implies. `pop.py` prices each tail with its own leg's IV
    and is the better read of *probability*; this is the better read of *expectation*,
    and they are not the same question.
    """
    ivs = [float(q.iv) for q in candidate.shorts if q.iv is not None and q.iv > 0]
    return sum(ivs) / len(ivs) if ivs else None


def diversify(ranked: list[Candidate], limit: int) -> list[Candidate]:
    """Take the best of each kind in turn, rather than the best `limit` overall.

    A straight top-N collapses. Measured on a live SPY chain under a bullish read,
    the six best-scoring candidates were all put credit spreads on the same 0.45-delta
    short strike, differing only in wing width — because the bias term is worth 25
    points under the moderate profile and sweeps every directional structure to the
    top at once. The model was then choosing between rounding errors, which is the
    failure the short menu was supposed to prevent, not cause.

    Round-robin by kind fixes it without touching the ranking: the order within each
    kind is exactly the score order, and the best candidate overall is still first.
    What changes is that the model always sees a real alternative — if the tape is
    wrong about direction, there is something on the menu that does not care.
    """
    if limit <= 0:
        return []
    buckets: dict[str, list[Candidate]] = {}
    for candidate in ranked:                    # already sorted best-first
        buckets.setdefault(candidate.kind, []).append(candidate)

    # Kinds are visited in the order their best candidate scored, so the top pick is
    # unchanged and the menu still opens with the highest-ranked structure.
    order = sorted(buckets, key=lambda k: buckets[k][0].score, reverse=True)
    out: list[Candidate] = []
    while len(out) < limit and any(buckets[k] for k in order):
        for kind in order:
            if buckets[kind] and len(out) < limit:
                out.append(buckets[kind].pop(0))
    return out
