"""Candidate ranking — the six-term blend, ported from TradeScans' `scoring.ts`.

This replaces the reward/risk-over-spread placeholder that `candidates.score()` used
to be. Six terms, each normalised to 0-1, weighted by the active profile:

| term          | asks                                                      |
|---------------|-----------------------------------------------------------|
| bias fit      | does this structure want the direction the tape suggests?  |
| IV regime fit | is this the volatility environment to sell premium in?     |
| liquidity     | what fraction of the risk does crossing the spread eat?    |
| reward/risk   | how much is won per dollar at risk?                        |
| POP           | how often does it finish profitable?                       |
| event risk    | is there a known event inside the holding period?          |

Event risk is **subtracted**. The other five are earned.

**Nothing here approves a trade.** The score reorders a menu that the gates will
judge afterwards, and every candidate on that menu already passed the pre-filter.
A high score cannot rescue a structure the gates reject, and the model is free to
pick the third-ranked candidate — or none. Ranking is the last place in the pipeline
where being wrong is cheap, which is exactly why the tuned heuristics live here and
not in the gate layer.

**The breakdown is kept, not just the total.** `ScoreBreakdown` is journalled with
every candidate, so "why was this one top of the menu?" has an answer that is six
numbers rather than one. That is what makes the ranking auditable rather than
merely deterministic.

Two departures from the TypeScript, both because HAL Street knows more than the
vendor's generic engine did:

*Directional structures are classified exactly.* TradeScans put `vertical_call` and
`vertical_put` in **both** the bullish and bearish lists, because a "vertical" there
might be a credit or a debit spread and the type alone did not say. Here it does: a
put credit spread is bullish, a call credit spread is bearish, and the bias term
stops being a coin flip for two thirds of the menu.

*Scores are reported on a 0-100 scale.* The raw blend lands in roughly [-25, 95];
multiplying by 100 makes the journal and the decisions panel readable without
changing any ordering.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from halstreet.strategy import profiles as P
from halstreet.strategy.bias import BEARISH, BULLISH, NEUTRAL
from halstreet.strategy.regime import HIGH, LOW, MEDIUM, UNKNOWN

# Reward/risk at or above this scores full marks. A credit spread paying more than
# 5:1 is not five times better than one paying 5:1 — past that point the ratio is
# telling you the short strike is far enough out to be nearly worthless, which the
# POP term already rewards. Without the cap, ranking collapses onto lottery wings.
REWARD_RISK_SOFT_CAP = 5.0

# Slippage is judged against max loss *plus* this, so that a $50-risk structure is
# not scored as catastrophically illiquid over a few dollars of spread. Without the
# floor the term divides by a small number and dominates everything else.
SLIPPAGE_FLOOR_USD = 100.0

# How harshly slippage-as-a-fraction-of-risk is punished. At the vendor's 5x, giving
# up 20% of max loss to the spread scores zero liquidity.
SLIPPAGE_PENALTY = 5.0

# Which direction each structure wants. The vendor could not fill this in; we can.
STRUCTURE_BIAS: dict[str, str] = {
    P.PUT_CREDIT: BULLISH,     # short puts below the money — wants up, or sideways
    P.CALL_CREDIT: BEARISH,    # short calls above the money — wants down, or sideways
    P.IRON_CONDOR: NEUTRAL,    # wants neither, and pays for the privilege
    # The long verticals, and the pairing is the part worth reading twice: a long CALL
    # vertical is bullish, and the credit structure that wants the same thing is the
    # PUT credit spread. Matching them by right rather than by direction is how a menu
    # ends up scored against the opposite of the read that built it.
    P.CALL_DEBIT: BULLISH,     # long the near call, short the far one — wants up
    P.PUT_DEBIT: BEARISH,      # long the near put, short the far one — wants down
}

EVENT_NONE = "none"
EVENT_PRESENT = "present"
EVENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class EventWindow:
    """Known events ahead, as days from the scan — resolved once, asked per candidate.

    This used to be a single string per underlying, which is why the term could not
    discriminate: every candidate on SPY got the same answer regardless of when it
    expired. Two spreads on the same name, one expiring before an event and one
    spanning it, are not the same trade.

    `known` and an empty `days_out` are different from `known=False`. The first says
    the calendar was read and the window is clear; the second says it could not be
    read. Only the first is grounds for removing a penalty, and collapsing them is
    exactly the mistake this replaced.
    """

    known: bool = False
    days_out: tuple[int, ...] = ()

    def risk_for(self, dte: int | None) -> str:
        if not self.known:
            return EVENT_UNKNOWN
        if dte is None:
            # No expiry to judge against: fall back to the whole window.
            return EVENT_PRESENT if self.days_out else EVENT_NONE
        return EVENT_PRESENT if any(0 <= d <= dte for d in self.days_out) else EVENT_NONE


@dataclass(frozen=True)
class Context:
    """Everything the ranking knows that is not in the candidate itself."""

    bias: str = NEUTRAL
    regime: str = UNKNOWN
    #: Resolved once per underlying per cycle; each candidate asks it about its own
    #: expiry. Defaults to "not checked", which is penalised.
    events: EventWindow = EventWindow()
    weights: P.Weights = P.MODERATE.weights
    #: Annualized realized volatility, as a fraction. Not part of the ranking — the
    #: regime *label* above is what the six terms read. This is here because the menu
    #: is where a structure's scenario is sampled, and `montecarlo` refuses to run on
    #: a volatility nobody measured rather than defaulting to one.
    realized_vol: float | None = None


@dataclass(frozen=True)
class ScoreBreakdown:
    """The six terms, before weighting. Journalled with every candidate."""

    bias_fit: float
    iv_regime_fit: float
    liquidity: float
    reward_risk: float
    pop: float
    event_risk: float
    total: float

    def to_prompt(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}


def bias_fit(kind: str, bias: str) -> float:
    """1 when the structure wants the tape's direction, 0 when it opposes it.

    A neutral read scores every structure 0.5 except the iron condor, which gets
    full marks — "no direction" is not the absence of a signal for a condor, it is
    the signal.
    """
    wants = STRUCTURE_BIAS.get(kind)
    if wants is None:
        return 0.5
    if bias == NEUTRAL:
        return 1.0 if wants == NEUTRAL else 0.5
    if wants == NEUTRAL:
        # A condor into a trending tape is not disqualified — one side is simply
        # doing the work — but it is not what you would choose.
        return 0.5
    return 1.0 if wants == bias else 0.0


def iv_regime_fit(kind: str, regime: str) -> float:
    """Credit structures want high volatility; debit structures want low.

    Unknown scores 0.5 rather than 0. Every candidate in one scan shares the same
    regime, so a zero here would penalise the whole menu equally and change no
    ordering — while pushing every total down enough to look like the agent found
    nothing worth trading.
    """
    if regime == UNKNOWN:
        return 0.5
    if kind in P.CREDIT_STRUCTURES:
        return {HIGH: 1.0, MEDIUM: 0.6, LOW: 0.2}.get(regime, 0.5)
    if kind in P.DEBIT_STRUCTURES:
        return {LOW: 1.0, MEDIUM: 0.6, HIGH: 0.2}.get(regime, 0.5)
    return 0.5


def liquidity_fit(slippage_usd: float | None, max_loss_usd: float) -> float:
    """What fraction of the risk crossing the spread would eat.

    `slippage_usd` is the one-way cost of paying the spread on entry — half the
    bid-ask on every leg. Measured friction on this account is ~$7.50 per leg per
    contract for a full round trip, so ~$3.75 one-way, and a four-leg entry costing
    ~$15 by this estimate is the right order of magnitude.

    Unknown slippage scores 0, not 0.5. Spread width is the one input we always
    have; if it is missing the quote itself is suspect.
    """
    if slippage_usd is None:
        return 0.0
    ratio = slippage_usd / (abs(max_loss_usd) + SLIPPAGE_FLOOR_USD)
    return max(0.0, 1.0 - ratio * SLIPPAGE_PENALTY)


def reward_risk_fit(max_gain_usd: float, max_loss_usd: float) -> float:
    if max_loss_usd <= 0:
        return 0.0
    return min(1.0, (max_gain_usd / max_loss_usd) / REWARD_RISK_SOFT_CAP)


def pop_fit(pop: float | None) -> float:
    """Probability of profit, clamped. Unknown scores 0.

    Unlike the regime, POP varies across the menu, so an unknown is a genuine
    disadvantage rather than a constant — a candidate whose odds cannot be computed
    should lose to one whose can.
    """
    return 0.0 if pop is None else max(0.0, min(1.0, pop))


def event_penalty(event_risk: str) -> float:
    """1 when an event is known or unknown, 0 only when it is known to be absent."""
    return 0.0 if event_risk == EVENT_NONE else 1.0


def score(*, kind: str, max_gain_usd: float, max_loss_usd: float,
          slippage_usd: float | None, pop: float | None,
          ctx: Context, dte: int | None = None) -> ScoreBreakdown:
    """Rank one candidate. Returns the breakdown; `total` is on a 0-100 scale.

    `dte` is what makes the event term a per-candidate judgement rather than a
    per-underlying constant: the question is whether an event falls inside *this*
    structure's holding period, not inside some window chosen elsewhere.
    """
    breakdown = {
        "bias_fit": bias_fit(kind, ctx.bias),
        "iv_regime_fit": iv_regime_fit(kind, ctx.regime),
        "liquidity": liquidity_fit(slippage_usd, max_loss_usd),
        "reward_risk": reward_risk_fit(max_gain_usd, max_loss_usd),
        "pop": pop_fit(pop),
        "event_risk": event_penalty(ctx.events.risk_for(dte)),
    }
    w = ctx.weights
    total = 100.0 * (
        w.bias_alignment * breakdown["bias_fit"]
        + w.iv_regime_fit * breakdown["iv_regime_fit"]
        + w.liquidity * breakdown["liquidity"]
        + w.reward_risk * breakdown["reward_risk"]
        + w.prob_of_profit * breakdown["pop"]
        - w.event_risk * breakdown["event_risk"]
    )
    return ScoreBreakdown(total=total, **breakdown)


def as_decimal(total: float) -> Decimal:
    """The score as a Decimal, for the journal.

    A score is not money and the arithmetic above is float on purpose — a normal CDF
    has no exact decimal form. Quantizing at the boundary keeps the recorded value
    byte-stable across runs and platforms, which is what a reproducible journal needs.
    """
    return Decimal(f"{total:.4f}")
