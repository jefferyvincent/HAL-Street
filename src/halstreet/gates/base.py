"""The gate layer: deterministic Python between a model's proposal and an order.

This is the boundary the project is argued on. Everything above it is probabilistic —
a model ranked some structures and wrote a proposal. Everything at or below it is
auditable: plain functions over a proposal and an account snapshot, no model call, no
network, no clock beyond an injected date, and nothing the agent can rewrite at
runtime.

Three rules hold for every gate in this package.

**All gates run.** Evaluation does not stop at the first rejection. The run journal
wants every reason a proposal was refused, and "rejected by 4 gates" is a more useful
artifact than "rejected by the first one we happened to check." Gates are therefore
independent and must not assume an earlier one passed.

**Gates fail closed.** A gate that cannot evaluate — a missing greek, an absent
quote, a leg that is not in the chain — rejects. It never skips, and it never
abstains. A proposal that cannot be risk-assessed is a proposal to reject; the
alternative is a gate that silently stops protecting you exactly when the data is
bad, which is when you need it most.

**Gates are pure.** The caller fetches account, positions and chain once and passes
them in. This keeps the whole layer testable without a broker, which is what makes
`docs/TESTING.md`'s rule — every gate has a test proving it *rejects* — cheap enough
to actually hold to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from halstreet.execution.structures import Structure


@dataclass(frozen=True)
class Proposal:
    """What the model emits, and the only thing gates judge.

    The model chooses the structure and the size. It does not choose the limits those
    are checked against, cannot reach the environment, and has no say in whether the
    gates run.
    """

    structure: Structure
    underlying: str
    rationale: str = ""
    # Model-assigned confidence, carried for the journal. Deliberately not consulted
    # by any gate: a limit that a confident model can talk its way past is not a limit.
    confidence: float | None = None


@dataclass(frozen=True)
class GateContext:
    """Everything the gates are allowed to look at, fetched once by the caller."""

    account: dict
    positions: list[dict] = field(default_factory=list)
    # OCC symbol -> chain snapshot, as returned by get_option_chain. Carries quotes,
    # greeks and IV. A leg absent from here is an unverifiable contract.
    chain: dict[str, dict] = field(default_factory=dict)
    limits: Limits = None  # type: ignore[assignment]
    asof: date = field(default_factory=date.today)
    # Underlying last price. Explicit rather than dug out of a quote dict, because the
    # assignment gate is meaningless without it and must fail closed when it is absent.
    spot: Decimal | None = None
    # Circuit-breaker history — the day's equity baseline, the halt latch, recent
    # entry timestamps. Loaded and persisted by `agent.breaker`; the gates only read
    # it. Absent means the caller did not wire it, and the circuit gates fail closed
    # rather than reading as healthy.
    breaker: Any | None = None
    # The ranked menu the model was shown, as a set of leg-signature frozensets. The
    # menu gate compares against this; empty means the caller did not wire it, and the
    # gate fails closed rather than waving every structure through.
    menu: frozenset[frozenset[tuple[str, int]]] = frozenset()
    # Contracts ordered but not yet booked by the broker, in the same shape as
    # `positions`. A resting limit order is exposure — the commitment is real from the
    # moment it is accepted — and counting only what the broker has filled let the
    # agent place a second SPY spread while the first was still working, every half
    # hour, until the entry throttle stopped it.
    #
    # Separate from `positions` rather than merged into it, because the other gates
    # read that list too: the greek bounds want contracts it can price, and a
    # committed-but-unfilled leg would fail closed there for the wrong reason.
    pending: list[dict] = field(default_factory=list)
    # Which (underlying, family) pairs are resting after a run of losses, and why.
    # Computed from the ledger by `hippocampus.experience`; the gates only read it,
    # the same arrangement as `breaker`.
    #
    # `None` and `{}` are different answers and `loss_cooldown` keeps them different:
    # empty is a measured statement that nothing is resting, missing means nobody
    # looked. A gate that read those the same way would wave everything through on the
    # day the caller forgot to load the ledger.
    benched: dict[tuple[str, str], str] | None = None

    @property
    def equity(self) -> Decimal | None:
        try:
            return Decimal(str(self.account.get("equity")))
        except Exception:
            return None


@dataclass(frozen=True)
class Limits:
    """Hard bounds. Read from the environment at startup; never from the model.

    Defaults mirror .env.example. They are the ceiling, not a suggestion — a config
    file that widens them is a deliberate act by a human, recorded in the journal.
    """

    max_loss_per_position_usd: Decimal = Decimal(1000)
    max_portfolio_risk_pct: Decimal = Decimal(15)
    max_positions_per_underlying: int = 1
    min_dte: int = 7
    min_open_interest: int = 250
    # Contracts traded today. Open interest is published daily and lags; volume is
    # the live half of the pair, so both are checked.
    min_daily_volume: int = 10
    max_bid_ask_width_pct: Decimal = Decimal(10)
    # Assignment proximity: reject a short leg this close to the money, in percent of
    # spot, when it is also near expiry.
    assignment_moneyness_pct: Decimal = Decimal(2)
    assignment_dte: int = 5
    # Net delta in SHARE EQUIVALENTS of the underlying — the conventional unit, where
    # one delta is one share. A 0.5-delta call on 10 contracts is 500. Stated in shares
    # rather than in per-contract deltas because that is the number that tells you what
    # the book actually does when the underlying moves a dollar.
    max_net_delta: Decimal = Decimal(5000)
    # Net vega in dollars per volatility point, summed across contracts.
    max_net_vega: Decimal = Decimal(100)
    # --- circuit breakers (see gates/circuit.py) ---
    # Positions' worth of contracts allowed across one correlated group. SPY, QQQ and
    # IWM are one bet in three tickers; without this the per-underlying cap counts
    # them as three separate names and waves the whole thing through.
    max_correlated_positions: int = 2
    # Positions' worth of contracts allowed across every name NOT in any group above.
    #
    # A separate number from the one over it, because it answers a separate question.
    # "SPY and QQQ move together" is a claim about those two names that someone
    # checked. "KO, PEP and MCD are in no group" is a claim about the *map* — nobody
    # has classified them — and bounding it is humility rather than correlation.
    #
    # It exists because the universe stopped being three tickers in `.env`. While a
    # human picked the names, everything the agent could propose was mapped by
    # construction and "in no group" was a deliberate choice; with news discovery it
    # is the common case, and the correlation cap answered the common case by waving
    # it through. Set to 0 to disable, which restores exactly that behaviour.
    max_unclassified_positions: int = 3
    # Equity drawdown from the day's open that latches trading off. 0 disables.
    daily_loss_limit_pct: Decimal = Decimal(5)
    # Runaway guard, not a risk limit — the loop should never approach it.
    max_entries_per_hour: int = 6
    # Broker positions (one per contract after leg-netting) the book may hold at once.
    max_open_positions: int = 20
    # Share of options buying power kept back rather than committed, so there is
    # always something left to pay for an exit. Negative disables the gate.
    min_buying_power_headroom_pct: Decimal = Decimal(20)

    @classmethod
    def from_env(cls, source: dict[str, str] | None = None) -> Limits:
        """Read the bounds from the environment, falling back to the defaults above.

        A malformed value raises rather than falling back. A risk limit that silently
        reverts to a default because someone typed `MIN_DTE=seven` is worse than no
        limit at all — you would believe you were protected at the number you wrote.
        """
        import os

        src = os.environ if source is None else source

        def dec(key: str, default: Decimal) -> Decimal:
            raw = (src.get(key) or "").strip()
            if not raw:
                return default
            try:
                return Decimal(raw)
            except InvalidOperation:
                raise ConfigurationError(f"{key}={raw!r} is not a number") from None

        def integer(key: str, default: int) -> int:
            raw = (src.get(key) or "").strip()
            if not raw:
                return default
            try:
                return int(raw)
            except ValueError:
                raise ConfigurationError(f"{key}={raw!r} is not an integer") from None

        return cls(
            max_loss_per_position_usd=dec("MAX_LOSS_PER_POSITION_USD",
                                          cls.max_loss_per_position_usd),
            max_portfolio_risk_pct=dec("MAX_PORTFOLIO_RISK_PCT", cls.max_portfolio_risk_pct),
            max_positions_per_underlying=integer(
                "MAX_POSITIONS_PER_UNDERLYING", cls.max_positions_per_underlying
            ),
            min_dte=integer("MIN_DTE", cls.min_dte),
            min_open_interest=integer("MIN_OPEN_INTEREST", cls.min_open_interest),
            min_daily_volume=integer("MIN_DAILY_VOLUME", cls.min_daily_volume),
            max_bid_ask_width_pct=dec("MAX_BID_ASK_WIDTH_PCT", cls.max_bid_ask_width_pct),
            assignment_moneyness_pct=dec("ASSIGNMENT_MONEYNESS_PCT", cls.assignment_moneyness_pct),
            assignment_dte=integer("ASSIGNMENT_DTE", cls.assignment_dte),
            max_net_delta=dec("MAX_NET_DELTA", cls.max_net_delta),
            max_net_vega=dec("MAX_NET_VEGA", cls.max_net_vega),
            max_correlated_positions=integer("MAX_CORRELATED_POSITIONS",
                                             cls.max_correlated_positions),
            max_unclassified_positions=integer("MAX_UNCLASSIFIED_POSITIONS",
                                               cls.max_unclassified_positions),
            daily_loss_limit_pct=dec("DAILY_LOSS_LIMIT_PCT", cls.daily_loss_limit_pct),
            max_entries_per_hour=integer("MAX_ENTRIES_PER_HOUR", cls.max_entries_per_hour),
            max_open_positions=integer("MAX_OPEN_POSITIONS", cls.max_open_positions),
            min_buying_power_headroom_pct=dec("MIN_BUYING_POWER_HEADROOM_PCT",
                                              cls.min_buying_power_headroom_pct),
        )


@dataclass(frozen=True)
class GateResult:
    """One gate's verdict on one proposal."""

    gate: str
    passed: bool
    reason: str = ""
    # Which module the gate came from — contract, liquidity, defined_risk, portfolio,
    # circuit. Stamped automatically by `evaluate` rather than declared per gate, so
    # a gate is in the family its source file says it is and the two cannot drift.
    # The panel groups by this; without it the UI has to slice the list by position,
    # which silently mislabels everything the moment a gate is inserted.
    family: str = ""

    def __str__(self) -> str:
        return f"[{'PASS' if self.passed else 'REJECT'}] {self.gate}" + (
            f" — {self.reason}" if self.reason else ""
        )


class ConfigurationError(RuntimeError):
    """A risk limit that could not be read. Never silently defaulted."""


class Gate(Protocol):
    """A gate is a pure function from (proposal, context) to a verdict."""

    __name__: str

    def __call__(self, proposal: Proposal, ctx: GateContext) -> GateResult: ...


@dataclass(frozen=True)
class Decision:
    """The full verdict, and the record that goes in the journal."""

    proposal: Proposal
    results: list[GateResult]

    @property
    def approved(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def rejections(self) -> list[GateResult]:
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        if self.approved:
            return f"APPROVED: {self.proposal.structure.name} ({len(self.results)} gates passed)"
        reasons = "; ".join(f"{r.gate}: {r.reason}" for r in self.rejections)
        return (
            f"REJECTED: {self.proposal.structure.name} "
            f"({len(self.rejections)}/{len(self.results)} gates) — {reasons}"
        )


def evaluate(proposal: Proposal, ctx: GateContext, gates: list[Gate]) -> Decision:
    """Run every gate and collect every verdict.

    A gate that raises is itself a rejection. A crashing gate has not proven the
    proposal safe, and turning an exception into an approval would invert the whole
    point of the layer — so the exception is caught, recorded by name, and counted
    against the proposal.
    """
    results: list[GateResult] = []
    for gate in gates:
        name = getattr(gate, "gate_name", getattr(gate, "__name__", repr(gate)))
        family = family_of(gate)
        try:
            result = gate(proposal, ctx)
        except Exception as exc:
            result = GateResult(name, False, f"gate raised {type(exc).__name__}: {exc}")
        # Stamped here, not trusted from the gate: a gate that forgot to set it, or a
        # raising gate that never got the chance, still lands in the right family.
        results.append(replace(result, family=family))
    return Decision(proposal, results)


# Presentation order for the families, and the order the panel lays them out in. It
# runs narrowest-to-widest: is the contract real, can we trade it, is the risk bounded,
# does it fit the book, should we be trading at all.
FAMILIES: tuple[str, ...] = (
    "contract", "liquidity", "defined_risk", "portfolio", "circuit",
)


def family_of(gate: Gate) -> str:
    """Which gate module a gate came from.

    Derived from `__module__` rather than declared, because the module *is* the
    grouping — `gates/circuit.py` holds the circuit breakers by definition. A
    declared family is one more thing to forget to update when a gate moves file.
    """
    module = getattr(gate, "__module__", "") or ""
    leaf = module.rsplit(".", 1)[-1]
    return leaf if leaf in FAMILIES else "other"


def gate(name: str) -> Callable[[Callable[..., GateResult]], Any]:
    """Name a gate for the journal, independently of its function name."""

    def decorate(fn: Callable[..., GateResult]) -> Any:
        fn.gate_name = name  # type: ignore[attr-defined]
        return fn

    return decorate


def reject(name: str, reason: str) -> GateResult:
    return GateResult(name, False, reason)


def allow(name: str, reason: str = "") -> GateResult:
    return GateResult(name, True, reason)
