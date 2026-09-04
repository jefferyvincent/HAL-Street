"""The gate layer.

`ALL_GATES` is the chain every proposal runs, in the order the journal reports them.
Order is presentational only — evaluation never short-circuits, so a proposal that
violates four rules is recorded as violating four rules.

The environment assertion is deliberately absent from this list. It is not a gate over
a proposal; it runs inside `execution.place_structure`, against the broker's own
account snapshot, immediately before every order. Putting it here would imply it could
be reordered, disabled, or passed a stale context — and it is the one check that must
hold at the moment of submission rather than at the moment of judgement.

Two more rules live in `execution.structures` rather than here, for the same reason:
the 4-leg ceiling and roll atomicity are refusals to *construct* an order at all, so
they fire before a proposal is even well-formed.
"""

from __future__ import annotations

from halstreet.gates.base import (
    ConfigurationError,
    Decision,
    Gate,
    GateContext,
    GateResult,
    Limits,
    Proposal,
    evaluate,
)
from halstreet.gates.circuit import (
    CORRELATED,
    DAILY_LOSS,
    ENTRY_RATE,
    LOSS_COOLDOWN,
    OPEN_POSITIONS,
    SESSION_CUTOFF,
    correlated_exposure,
    daily_loss_halt,
    entry_rate_throttle,
    loss_cooldown,
    open_position_count,
    session_cutoff,
)
from halstreet.gates.contract import (
    CONTRACT_EXISTS,
    DTE_FLOOR,
    ON_THE_MENU,
    contract_exists,
    dte_floor,
    on_the_menu,
)
from halstreet.gates.defined_risk import (
    BUYING_POWER,
    DEFINED_RISK,
    MAX_LOSS,
    PORTFOLIO_RISK,
    defined_risk_only,
    max_loss_per_position,
    options_buying_power,
    portfolio_risk_ceiling,
)
from halstreet.gates.liquidity import LIQUIDITY, SPREAD_WIDTH, liquidity_floor, spread_width
from halstreet.gates.portfolio import (
    ASSIGNMENT,
    CONCENTRATION,
    GREEK_BOUNDS,
    assignment_proximity,
    portfolio_greek_bounds,
    underlying_concentration,
)

ALL_GATES: list[Gate] = [
    # Should we be opening anything at all right now? These judge the situation rather
    # than the proposal, and none of them looks at the structure's own merits.
    daily_loss_halt,
    entry_rate_throttle,
    session_cutoff,
    open_position_count,
    # Have we just been wrong about this exact idea? Reads a record computed from the
    # ledger, so a losing run stops the trade rather than only warning the model.
    loss_cooldown,
    # Is this even a real structure, and is it one we actually offered?
    contract_exists,
    on_the_menu,
    # Is its shape acceptable?
    defined_risk_only,
    dte_floor,
    # Is it the right size?
    max_loss_per_position,
    portfolio_risk_ceiling,
    options_buying_power,
    # Can we actually trade it?
    liquidity_floor,
    spread_width,
    # Is it the right thing to add to this book?
    underlying_concentration,
    correlated_exposure,
    portfolio_greek_bounds,
    assignment_proximity,
]

__all__ = [
    "ALL_GATES",
    "ASSIGNMENT",
    "BUYING_POWER",
    "CONCENTRATION",
    "CONTRACT_EXISTS",
    "CORRELATED",
    "DAILY_LOSS",
    "DEFINED_RISK",
    "DTE_FLOOR",
    "ENTRY_RATE",
    "GREEK_BOUNDS",
    "LIQUIDITY",
    "LOSS_COOLDOWN",
    "MAX_LOSS",
    "ON_THE_MENU",
    "OPEN_POSITIONS",
    "PORTFOLIO_RISK",
    "SESSION_CUTOFF",
    "SPREAD_WIDTH",
    "ConfigurationError",
    "Decision",
    "Gate",
    "GateContext",
    "GateResult",
    "Limits",
    "Proposal",
    "assignment_proximity",
    "contract_exists",
    "correlated_exposure",
    "daily_loss_halt",
    "defined_risk_only",
    "dte_floor",
    "entry_rate_throttle",
    "evaluate",
    "liquidity_floor",
    "max_loss_per_position",
    "open_position_count",
    "options_buying_power",
    "portfolio_greek_bounds",
    "portfolio_risk_ceiling",
    "session_cutoff",
    "spread_width",
    "underlying_concentration",
]
