"""Multi-leg option structures and their wire form for Alpaca's MCP server.

HAL could only ever place equities and single-leg options. Everything this project
exists to trade is multi-leg, so this module is the new boundary: a typed structure
in, the exact dict `place_option_order` expects out.

Two properties of that tool drive the design.

**Four legs, hard.** Enforced in the MCP server's override and again in alpaca-py.
An iron condor is exactly four, which means the ceiling is not comfortable headroom
— it is the wall, and it is why a condor roll cannot be one atomic order. Structures
are validated at construction so an over-wide structure dies here rather than as an
opaque broker rejection after the model has already committed to it.

**Everything crosses the wire as a string.** qty, ratio_qty and limit_price are all
`str` in the tool signature. Floats must not get near a strike or a limit price, so
prices are Decimal throughout and serialised through one function that never emits
scientific notation and never rounds silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

MAX_LEGS = 4
MIN_MLEG_LEGS = 2


class StructureError(ValueError):
    """A structure that cannot be expressed as a single Alpaca order."""


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PositionIntent(str, Enum):
    BUY_TO_OPEN = "buy_to_open"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_OPEN = "sell_to_open"
    SELL_TO_CLOSE = "sell_to_close"


def money(value: Decimal | str | int) -> str:
    """Serialise a price to a plain decimal string, quantized to the penny.

    Rejects anything that would round — a limit price the caller did not actually
    choose is a silent execution bug, and options quote in pennies anyway.
    """
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StructureError(f"not a usable price: {value!r}") from exc
    if d != d.quantize(Decimal("0.01")):
        raise StructureError(
            f"price {d} is finer than the penny increment Alpaca accepts for options"
        )
    # Negative is allowed and meaningful: on a multi-leg order the limit price is a net
    # debit (positive) or net credit (negative), so a credit spread legitimately prices
    # below zero.
    return f"{d.quantize(Decimal('0.01')):f}"


def whole(value: int | str) -> str:
    """Serialise a contract count. Fractional option contracts do not exist."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StructureError(f"not a usable quantity: {value!r}") from exc
    if d != d.to_integral_value() or d <= 0:
        raise StructureError(
            f"quantity must be a positive whole number of contracts, got {value!r}")
    return f"{d.to_integral_value():f}"


@dataclass(frozen=True)
class Leg:
    """One leg of a structure, identified by its OCC symbol.

    `ratio_qty` is proportional to the order-level qty, not an absolute count: a
    1×1 vertical carries ratio_qty 1 on both legs whether you trade one spread or
    fifty.
    """

    symbol: str
    ratio_qty: int = 1
    side: Side | None = None
    position_intent: PositionIntent | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise StructureError("leg needs an OCC symbol")
        if self.side is None and self.position_intent is None:
            raise StructureError(
                f"leg {self.symbol} needs at least one of side or position_intent "
                "(Alpaca rejects a leg carrying neither)"
            )

    def to_wire(self) -> dict[str, str]:
        leg: dict[str, str] = {"symbol": self.symbol, "ratio_qty": whole(self.ratio_qty)}
        if self.side is not None:
            leg["side"] = self.side.value
        if self.position_intent is not None:
            leg["position_intent"] = self.position_intent.value
        return leg


@dataclass(frozen=True)
class Structure:
    """A defined-risk option structure destined for a single Alpaca order.

    This type deliberately knows nothing about whether the structure is a *good*
    idea — max loss, DTE, liquidity and concentration are all decided in `gates/`,
    on the auditable side of the boundary. All this enforces is what the broker
    itself will and will not accept, so that a rejection surfaces here with a
    legible reason instead of as an error code after submission.
    """

    name: str
    legs: tuple[Leg, ...]
    qty: int = 1
    # For a multi-leg order this is the NET debit or credit, not a per-leg price, and
    # the sign carries the meaning: positive is a debit you pay, negative a credit you
    # receive. Getting that backwards on a credit spread inverts the trade, so callers
    # should be explicit rather than passing through whatever the strategy engine
    # happened to compute.
    limit_price: Decimal | None = None
    # "day" is the only value Alpaca accepts for options. Kept as a field so the
    # constraint is visible at the call site instead of buried in a serialiser.
    time_in_force: str = "day"
    # Idempotency key. The broker treats a repeat of the same id as the same order, so
    # a submission that times out can be retried without risking a double position —
    # which matters precisely because this agent runs unattended and nobody is
    # watching to notice it opened the condor twice.
    client_order_id: str | None = None

    def __post_init__(self) -> None:
        n = len(self.legs)
        if n == 0:
            raise StructureError(f"{self.name}: a structure needs at least one leg")
        if n > MAX_LEGS:
            raise StructureError(
                f"{self.name}: {n} legs exceeds Alpaca's hard ceiling of {MAX_LEGS}. "
                "This structure cannot be placed as one order — it must be decomposed, "
                "which means accepting leg risk between the parts."
            )
        symbols = [leg.symbol for leg in self.legs]
        if len(set(symbols)) != n:
            dupes = sorted({s for s in symbols if symbols.count(s) > 1})
            raise StructureError(
                f"{self.name}: every leg must have a unique symbol; repeated {dupes}"
            )
        whole(self.qty)
        # Validate the price here rather than at to_wire(). Otherwise a sub-penny
        # limit survives parsing and gating, is journalled as an approved proposal,
        # and only fails at submission — long after the decision was recorded.
        if self.limit_price is not None:
            money(self.limit_price)

    @property
    def is_multileg(self) -> bool:
        return len(self.legs) >= MIN_MLEG_LEGS

    def to_wire(self) -> dict[str, object]:
        """The exact keyword arguments for the MCP `place_option_order` tool.

        Note there is no `order_class` here for the multi-leg case: the server sets
        it to "mleg" itself whenever `legs` is supplied, and setting it redundantly
        is one more thing to keep in sync with a tool we do not own.
        """
        args: dict[str, object] = {
            "qty": whole(self.qty),
            "time_in_force": self.time_in_force,
            "type": "limit" if self.limit_price is not None else "market",
        }
        if self.limit_price is not None:
            args["limit_price"] = money(self.limit_price)
        if self.client_order_id is not None:
            args["client_order_id"] = self.client_order_id

        if self.is_multileg:
            args["legs"] = [leg.to_wire() for leg in self.legs]
        else:
            leg = self.legs[0]
            args["symbol"] = leg.symbol
            if leg.side is not None:
                args["side"] = leg.side.value
            if leg.position_intent is not None:
                args["position_intent"] = leg.position_intent.value
        return args


def vertical(
    name: str, long_symbol: str, short_symbol: str, qty: int = 1,
    limit_price: Decimal | None = None,
) -> Structure:
    """A two-leg debit or credit vertical. Defined risk by construction."""
    return Structure(
        name=name,
        legs=(
            Leg(long_symbol, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),
            Leg(short_symbol, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
        ),
        qty=qty,
        limit_price=limit_price,
    )


def iron_condor(
    name: str, long_put: str, short_put: str, short_call: str, long_call: str,
    qty: int = 1, limit_price: Decimal | None = None,
) -> Structure:
    """A four-leg iron condor — exactly at the leg ceiling.

    Long wings first in each pair so the defined-risk reading is obvious: the two
    bought legs bound the two sold ones.
    """
    return Structure(
        name=name,
        legs=(
            Leg(long_put, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),
            Leg(short_put, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
            Leg(short_call, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
            Leg(long_call, 1, Side.BUY, PositionIntent.BUY_TO_OPEN),
        ),
        qty=qty,
        limit_price=limit_price,
    )


# --- exits: closing and rolling -----------------------------------------------
#
# The 4-leg ceiling decides what a roll can be. Closing a structure costs as many
# legs as it has, and opening the replacement costs as many again, so a roll is
# expressible as one order only when those two totals fit inside four. That admits
# 2-leg structures and excludes everything else.
#
# Settled policy: 4-leg structures have no roll primitive. A condor exits by
# closing, and any re-entry afterwards is a fresh proposal through the full gate
# chain. The alternative — close-then-reopen as two orders — leaves a gap holding
# a position no gate ever evaluated, which is exactly the thing this project claims
# it does not do. It is refused here, at construction, so a model that proposes a
# condor roll is stopped before an order exists rather than halfway through one.

_CLOSE_INTENT: dict[Side, PositionIntent] = {
    Side.BUY: PositionIntent.SELL_TO_CLOSE,
    Side.SELL: PositionIntent.BUY_TO_CLOSE,
}

_OPENING_INTENTS = frozenset({PositionIntent.BUY_TO_OPEN, PositionIntent.SELL_TO_OPEN})


def _invert(leg: Leg) -> Leg:
    """The leg that closes `leg` — same contract, opposite side and a closing intent."""
    if leg.side is None:
        raise StructureError(
            f"cannot close {leg.symbol}: the open leg carries no side, so the closing "
            "direction is unknown"
        )
    if leg.position_intent is not None and leg.position_intent not in _OPENING_INTENTS:
        raise StructureError(
            f"cannot close {leg.symbol}: it is already a closing leg "
            f"({leg.position_intent.value})"
        )
    closing_side = Side.SELL if leg.side is Side.BUY else Side.BUY
    return Leg(leg.symbol, leg.ratio_qty, closing_side, _CLOSE_INTENT[leg.side])


def can_roll(open_structure: Structure, replacement: Structure) -> bool:
    """Whether this roll fits in a single order. See `roll` for why that is the test."""
    return len(open_structure.legs) + len(replacement.legs) <= MAX_LEGS


def close(open_structure: Structure, qty: int | None = None,
          limit_price: Decimal | None = None) -> Structure:
    """The order that flattens an open structure.

    Always available, whatever the leg count — closing a condor is four legs, not
    eight. Exits are never gated on the entry rules that let the position on, for
    the same reason HAL's risk engine only ever blocks entries: when something has
    gone wrong you still need to be able to get out.
    """
    return Structure(
        name=f"close {open_structure.name}",
        legs=tuple(_invert(leg) for leg in open_structure.legs),
        qty=open_structure.qty if qty is None else qty,
        limit_price=limit_price,
        time_in_force=open_structure.time_in_force,
    )


def roll(open_structure: Structure, replacement: Structure,
         limit_price: Decimal | None = None) -> Structure:
    """One atomic order that closes `open_structure` and opens `replacement`.

    Raises StructureError when the two together exceed the 4-leg ceiling — which is
    every 4-leg structure, by design. Use `close` instead and let the re-entry be a
    fresh proposal.
    """
    n_close, n_open = len(open_structure.legs), len(replacement.legs)
    if n_close + n_open > MAX_LEGS:
        raise StructureError(
            f"cannot roll {open_structure.name} ({n_close} legs) into "
            f"{replacement.name} ({n_open} legs): {n_close + n_open} legs exceeds the "
            f"{MAX_LEGS}-leg ceiling, so this roll cannot be one order. Close the position "
            "instead and let the re-entry be a fresh proposal — a two-order roll would hold "
            "an intermediate position no gate evaluated."
        )
    if open_structure.qty != replacement.qty:
        raise StructureError(
            f"roll qty mismatch: closing {open_structure.qty} but opening "
            f"{replacement.qty}. A single order carries one qty; size the replacement to "
            "match, or close and re-enter separately."
        )
    return Structure(
        name=f"roll {open_structure.name} -> {replacement.name}",
        legs=tuple(_invert(leg) for leg in open_structure.legs) + replacement.legs,
        qty=open_structure.qty,
        limit_price=limit_price,
        time_in_force=replacement.time_in_force,
    )
