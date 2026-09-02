"""Risk profiles: how aggressively to build, and what to weight when ranking.

Ported from TradeScans' `profile-config.ts`. A profile is one coherent set of
answers to *what should we even look at* — how far out, how far from the money, how
liquid, and what matters when comparing two candidates. It is the thing that makes
`conservative` and `aggressive` different agents rather than the same agent with a
different position size.

**A profile can never loosen a gate.** This is the load-bearing rule of the file.
The profiles are tuned parameters from a consumer product; the gates are the
deterministic layer this whole project is argued on. `EffectiveFloor.compose` takes
the stricter of the two on every dimension, so pointing the agent at
`ultra_aggressive` widens the search but cannot widen the risk. If a profile's floor
is looser than `.env`, `.env` wins, silently and always. The reverse — a profile
stricter than the gates — is honoured, because searching less than you are allowed
to is a preference, not a risk.

**The whitelists are trimmed to what this agent builds.** TradeScans ranked fifteen
structure types; HAL Street constructs three, because the 4-leg ceiling and the
defined-risk gate exclude the rest. The profile ordering is preserved: verticals from
the most conservative profile up, iron condors from `moderate` up — a condor is two
short verticals, so a profile that will not sell one side should not sell both.

**Spread limits are in percent, not fractions.** The TypeScript stored `0.05` and
meant 5%; every limit in HAL Street is in percent because that is how `.env` reads.
Converting once, here, beats a factor-of-100 bug in a liquidity filter. The vendor's
second, mid-dependent spread rule is deliberately not ported — `LiquidityFloor`
explains why, and the short version is that it would make this layer looser than the
gate it is supposed to anticipate.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from decimal import Decimal

# Structure kinds this agent can actually construct. These strings match
# `Candidate.kind` in `candidates`.
PUT_CREDIT = "put_credit_spread"
CALL_CREDIT = "call_credit_spread"
IRON_CONDOR = "iron_condor"
PUT_DEBIT = "put_debit_spread"
CALL_DEBIT = "call_debit_spread"

VERTICALS = (PUT_CREDIT, CALL_CREDIT)
DEBIT_VERTICALS = (PUT_DEBIT, CALL_DEBIT)
VERTICALS_AND_CONDORS = (PUT_CREDIT, CALL_CREDIT, IRON_CONDOR)
#: Everything, for a profile that wants to trade both sides of volatility.
#:
#: The credit-only whitelists are the reason the agent could not act on a
#: bullish read except by selling puts — and could not act at all in a regime
#: where realized vol runs above implied, which is precisely when a long
#: vertical is the trade.
ALL_STRUCTURES = (PUT_CREDIT, CALL_CREDIT, IRON_CONDOR, PUT_DEBIT, CALL_DEBIT)

# All three are net-credit structures, so every profile prefers a high-volatility
# tape. The distinction the vendor drew between credit- and debit-preferred
# strategies collapses here — kept as a set rather than inlined so that adding a
# debit structure later restores the distinction instead of silently mis-scoring it.
CREDIT_STRUCTURES = frozenset(VERTICALS_AND_CONDORS)
DEBIT_STRUCTURES: frozenset[str] = frozenset(DEBIT_VERTICALS)


@dataclass(frozen=True)
class Weights:
    """What matters when comparing two legal candidates. Consumed by `scoring`."""

    bias_alignment: float
    iv_regime_fit: float
    liquidity: float
    reward_risk: float
    prob_of_profit: float
    event_risk: float          # subtracted, not added


@dataclass(frozen=True)
class LiquidityFloor:
    """Minimum tradeability for a leg. Percentages, not fractions.

    TradeScans carried a second rule here — below a $10 mid, cap the spread in
    absolute dollars rather than as a percentage, on the reasoning that 5% of a
    $0.30 contract is 1.5 cents and no real market quotes that tight. It is a sound
    rule, and it is deliberately **not ported**, for two measured reasons.

    It solves a problem this universe does not have. Sampling the live 45-DTE chains
    for SPY, QQQ and IWM at every delta and width this agent builds, the widest leg
    quoted 5.0% and the cheapest cost $1.22 — every one comfortably inside the flat
    10% ceiling. The dollar rule would never once have fired.

    And it would have made the pre-filter looser than the gate. `liquidity_floor`
    enforces a flat `MAX_BID_ASK_WIDTH_PCT` on every leg; a pre-filter that admitted
    a 33%-wide cheap wing would hand the model a structure the gate is certain to
    reject — the exact failure this pre-filter exists to prevent. Restoring the rule
    means changing the gate first, and that is a decision for the audited layer, not
    for a parameter table.
    """

    min_open_interest: int
    # Contracts traded today. **Retuned downward from the vendor's numbers**, which
    # were 50/25/10/5 across the profiles and were set for a scanner over single-name
    # options that a human was about to look at. On a 45-DTE index option that figure
    # measures recency, not liquidity: mid-morning, a contract with 5,000 open
    # interest and a 0.9% market has routinely traded fewer than ten times.
    #
    # It is also biased in the worst possible direction. The further out of the money
    # a strike sits, the less it trades today — so a volume floor selects hardest
    # against exactly the OTM structures a premium-selling strategy is built on. At
    # the old 25, the 0.30-0.45 delta band was unreachable on all three underlyings
    # and QQQ produced no candidates at all.
    #
    # Measured on the live 45-DTE chains, holding everything else fixed:
    #
    #   volume floor 25 -> SPY  9, QQQ 0, IWM 1     deltas 0.2, 0.3, 0.5
    #   volume floor  5 -> SPY 19, QQQ 7, IWM 9     deltas 0.2, 0.3, 0.4, 0.5
    #
    # Open interest and spread do the real work: over the same sweep, moving the
    # spread ceiling between 8% and 12% changed nothing whatsoever, and open interest
    # 250 -> 300 moved one candidate. The floor is kept above zero because "has
    # traded at all today" is still a genuine staleness check on a quote.
    min_daily_volume: int
    max_spread_pct: Decimal


@dataclass(frozen=True)
class Profile:
    name: str
    min_dte: int
    max_dte: int
    short_delta_min: Decimal
    short_delta_max: Decimal
    liquidity: LiquidityFloor
    weights: Weights
    structures: tuple[str, ...]
    # Fraction of equity this profile is willing to put at risk in one position.
    # Advisory here: the max-loss and portfolio-risk gates are the enforcement.
    position_sizing_cap_pct: Decimal

    @property
    def short_deltas(self) -> tuple[Decimal, ...]:
        """Delta targets to build at — the band's edges and its middle.

        Three points rather than a sweep. The candidates differ enough to be a real
        choice and few enough that the model is choosing between structures rather
        than between rounding errors.
        """
        low, high = self.short_delta_min, self.short_delta_max
        mid = ((low + high) / 2).quantize(Decimal("0.01"))
        return tuple(sorted({low, mid, high}))

    def builds(self, kind: str) -> bool:
        return kind in self.structures

    def target_dte(self, requested: int) -> int:
        """Clamp a requested DTE into this profile's band."""
        return max(self.min_dte, min(self.max_dte, requested))


ULTRA_CONSERVATIVE = Profile(
    name="ultra_conservative",
    min_dte=30, max_dte=60,
    short_delta_min=Decimal("0.10"), short_delta_max=Decimal("0.25"),
    liquidity=LiquidityFloor(min_open_interest=500, min_daily_volume=15,
                             max_spread_pct=Decimal(5)),
    weights=Weights(bias_alignment=0.05, iv_regime_fit=0.35, liquidity=0.30,
                    reward_risk=0.10, prob_of_profit=0.10, event_risk=0.25),
    structures=VERTICALS,
    position_sizing_cap_pct=Decimal(1),
)

CONSERVATIVE = Profile(
    name="conservative",
    min_dte=30, max_dte=60,
    short_delta_min=Decimal("0.15"), short_delta_max=Decimal("0.30"),
    liquidity=LiquidityFloor(min_open_interest=500, min_daily_volume=15,
                             max_spread_pct=Decimal(5)),
    weights=Weights(bias_alignment=0.10, iv_regime_fit=0.30, liquidity=0.25,
                    reward_risk=0.15, prob_of_profit=0.10, event_risk=0.20),
    structures=VERTICALS,
    position_sizing_cap_pct=Decimal(2),
)

MODERATE = Profile(
    name="moderate",
    min_dte=21, max_dte=60,
    short_delta_min=Decimal("0.20"), short_delta_max=Decimal("0.45"),
    liquidity=LiquidityFloor(min_open_interest=250, min_daily_volume=5,
                             max_spread_pct=Decimal(8)),
    weights=Weights(bias_alignment=0.25, iv_regime_fit=0.20, liquidity=0.20,
                    reward_risk=0.20, prob_of_profit=0.10, event_risk=0.05),
    structures=VERTICALS_AND_CONDORS,
    position_sizing_cap_pct=Decimal(5),
)

# Moderate's judgement, on a shorter window.
#
# The DTE band and the risk posture used to be welded together: anything faster than
# 21 days meant `aggressive`, which also widens the short delta band from 0.20-0.45 to
# 0.30-0.55, drops the liquidity floors and raises the sizing cap. Three risk increases
# to buy one change of window.
#
# Every selection rule below is *referenced* from MODERATE rather than copied, so the
# two cannot drift: retuning moderate's liquidity floor retunes this one, which is the
# whole claim the profile makes. Only the window is its own.
#
# It is not a claim of identical risk. A 10 DTE spread at the same delta carries more
# gamma than a 45 DTE one and will lose faster when it loses; what is held constant is
# how a candidate is chosen, not how it behaves afterwards. The floor at 7 keeps it
# clear of the same-day expiry band where Alpaca returns no greeks and the delta and
# vega gates fail closed.
MODERATE_SHORT = Profile(
    name="moderate_short",
    min_dte=7, max_dte=21,
    short_delta_min=MODERATE.short_delta_min,
    short_delta_max=MODERATE.short_delta_max,
    liquidity=MODERATE.liquidity,
    weights=MODERATE.weights,
    structures=MODERATE.structures,
    position_sizing_cap_pct=MODERATE.position_sizing_cap_pct,
)


AGGRESSIVE = Profile(
    name="aggressive",
    min_dte=7, max_dte=45,
    short_delta_min=Decimal("0.30"), short_delta_max=Decimal("0.55"),
    liquidity=LiquidityFloor(min_open_interest=250, min_daily_volume=3,
                             max_spread_pct=Decimal(10)),
    weights=Weights(bias_alignment=0.35, iv_regime_fit=0.10, liquidity=0.15,
                    reward_risk=0.25, prob_of_profit=0.10, event_risk=0.05),
    structures=VERTICALS_AND_CONDORS,
    position_sizing_cap_pct=Decimal(7),
)

# The vendor's fifth profile permitted naked shorts. Here it does not, and cannot:
# `defined_risk_only` rejects an unhedged short leg no matter which profile built it.
# What survives of "ultra aggressive" is a wider delta band, a looser liquidity floor
# and a hunger for reward/risk — which is the honest remainder once undefined risk is
# off the table.
ULTRA_AGGRESSIVE = Profile(
    name="ultra_aggressive",
    min_dte=7, max_dte=45,
    short_delta_min=Decimal("0.30"), short_delta_max=Decimal("0.70"),
    liquidity=LiquidityFloor(min_open_interest=100, min_daily_volume=1,
                             max_spread_pct=Decimal(12)),
    weights=Weights(bias_alignment=0.40, iv_regime_fit=0.05, liquidity=0.10,
                    reward_risk=0.30, prob_of_profit=0.10, event_risk=0.05),
    structures=VERTICALS_AND_CONDORS,
    position_sizing_cap_pct=Decimal(10),
)

PROFILES: dict[str, Profile] = {
    p.name: p for p in
    (ULTRA_CONSERVATIVE, CONSERVATIVE, MODERATE, MODERATE_SHORT, AGGRESSIVE,
     ULTRA_AGGRESSIVE)
}

DEFAULT_PROFILE = MODERATE


class UnknownProfile(ValueError):
    """Raised for a RISK_PROFILE the table does not contain."""


def get(name: str) -> Profile:
    key = (name or "").strip().lower()
    if key not in PROFILES:
        raise UnknownProfile(
            f"RISK_PROFILE={name!r} is not one of {', '.join(sorted(PROFILES))}"
        )
    return PROFILES[key]


def from_env(source: dict[str, str] | None = None) -> Profile:
    """The configured profile, or `moderate`.

    An unrecognised name raises rather than falling back, for the same reason
    `Limits.from_env` does: silently trading a different profile than the one written
    in the config is worse than refusing to start.
    """
    src = os.environ if source is None else source
    raw = (src.get("RISK_PROFILE") or "").strip()
    profile = DEFAULT_PROFILE if not raw else get(raw)

    # Every shipped profile is credit-only, which is the shape the agent had before the
    # long verticals existed. Rather than a parallel set of profiles differing in one
    # field, the set is overridable directly — a profile is a risk posture, and which
    # structures express it is a separate choice.
    kinds = (src.get("STRUCTURES") or "").strip()
    if not kinds:
        return profile
    named = tuple(k.strip() for k in kinds.split(",") if k.strip())
    if not named:
        raise ValueError("STRUCTURES names no structures; leave it blank to use the "
                         "profile's own set")
    return replace_structures(profile, named)


@dataclass(frozen=True)
class EffectiveFloor:
    """The floor actually applied — the stricter of profile and gate limits."""

    min_open_interest: int
    # Contracts traded today. **Retuned downward from the vendor's numbers**, which
    # were 50/25/10/5 across the profiles and were set for a scanner over single-name
    # options that a human was about to look at. On a 45-DTE index option that figure
    # measures recency, not liquidity: mid-morning, a contract with 5,000 open
    # interest and a 0.9% market has routinely traded fewer than ten times.
    #
    # It is also biased in the worst possible direction. The further out of the money
    # a strike sits, the less it trades today — so a volume floor selects hardest
    # against exactly the OTM structures a premium-selling strategy is built on. At
    # the old 25, the 0.30-0.45 delta band was unreachable on all three underlyings
    # and QQQ produced no candidates at all.
    #
    # Measured on the live 45-DTE chains, holding everything else fixed:
    #
    #   volume floor 25 -> SPY  9, QQQ 0, IWM 1     deltas 0.2, 0.3, 0.5
    #   volume floor  5 -> SPY 19, QQQ 7, IWM 9     deltas 0.2, 0.3, 0.4, 0.5
    #
    # Open interest and spread do the real work: over the same sweep, moving the
    # spread ceiling between 8% and 12% changed nothing whatsoever, and open interest
    # 250 -> 300 moved one candidate. The floor is kept above zero because "has
    # traded at all today" is still a genuine staleness check on a quote.
    min_daily_volume: int
    max_spread_pct: Decimal
    min_dte: int
    # Every dimension where the two disagreed, in both directions. Reporting only
    # the clamps would hide the more surprising case: a ported vendor default
    # silently *tightening* a limit the operator deliberately chose in `.env`. That
    # is how `MIN_DAILY_VOLUME=10` quietly became 25 and starved a whole underlying
    # of candidates — a real observed failure, and one that showed up as "no
    # candidates built from the chain" rather than as anything about volume.
    clamped: list[str] = field(default_factory=list)
    tightened: list[str] = field(default_factory=list)

    @property
    def notes(self) -> list[str]:
        return ([f"loosened by .env: {n}" for n in self.clamped]
                + [f"tightened by profile: {n}" for n in self.tightened])

    @classmethod
    def compose(cls, profile: Profile, limits) -> EffectiveFloor:
        """Strictest-wins on every dimension. `limits` is a `gates.base.Limits`."""
        clamped: list[str] = []
        tightened: list[str] = []
        floor = profile.liquidity

        def note(name: str, mine, theirs, *, higher_is_stricter: bool) -> None:
            if mine == theirs:
                return
            mine_stricter = mine > theirs if higher_is_stricter else mine < theirs
            (tightened if mine_stricter else clamped).append(
                f"{name} {theirs} -> {mine}" if mine_stricter else f"{name} {mine} -> {theirs}")

        note("open interest", floor.min_open_interest, limits.min_open_interest,
             higher_is_stricter=True)
        note("daily volume", floor.min_daily_volume, limits.min_daily_volume,
             higher_is_stricter=True)
        note("spread %", floor.max_spread_pct, limits.max_bid_ask_width_pct,
             higher_is_stricter=False)
        note("min DTE", profile.min_dte, limits.min_dte, higher_is_stricter=True)

        return cls(
            min_open_interest=max(floor.min_open_interest, limits.min_open_interest),
            min_daily_volume=max(floor.min_daily_volume, limits.min_daily_volume),
            max_spread_pct=min(floor.max_spread_pct, limits.max_bid_ask_width_pct),
            min_dte=max(profile.min_dte, limits.min_dte),
            clamped=clamped,
            tightened=tightened,
        )


def replace_structures(profile: Profile, structures: tuple[str, ...]) -> Profile:
    """The same profile, building a different set of structures.

    A named function rather than `dataclasses.replace` at the call sites, because the
    whitelist is the one field where a typo produces an empty menu instead of an error
    — every builder is skipped, `generate` returns nothing, and the cycle reports
    "no candidates" as though the chain were thin.
    """
    unknown = set(structures) - set(ALL_STRUCTURES)
    if unknown:
        raise ValueError(f"unknown structure kind(s): {sorted(unknown)}")
    return dataclasses.replace(profile, structures=tuple(structures))
