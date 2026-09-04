"""The schema the model must emit, and the parser that refuses anything else.

This is the narrow opening in the wall. Above it the model may reason however it
likes; through it, only this shape passes. Everything the model is *not* allowed to
decide is simply absent from the schema — there is no field for the environment, no
field for the risk limits, no field for whether the gates run. A model cannot argue
its way past a parameter that does not exist.

Two rules govern parsing:

**Reject, never repair.** A malformed proposal is discarded with a reason, not
patched into something plausible. Repairing model output means inventing a trade
nobody proposed and then trading it, and the resulting position would be attributable
to no decision anyone made.

**The structured layer validates shape; the gates validate merit.** This module cares
that a proposal is well-formed — real OCC symbols, a legal leg count, a stated size.
Whether it is a *good idea* is `gates/`, and nothing here duplicates that judgement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from halstreet.execution.structures import (
    MAX_LEGS,
    Leg,
    PositionIntent,
    Side,
    Structure,
    StructureError,
)
from halstreet.gates.base import Proposal
from halstreet.marketdata.occ import parse as parse_occ

# The JSON contract, embedded in the system prompt. Kept beside the parser so the two
# cannot drift — a prompt describing a field the parser rejects is a silent failure
# that looks like a stupid model.
SCHEMA = {
    "type": "object",
    "required": ["action", "underlying", "name", "legs", "qty", "limit_price", "rationale"],
    "additionalProperties": False,
    "properties": {
        "action": {
            "enum": ["trade", "pass"],
            "description": (
                "'trade' to propose the structure below; 'pass' to decline this cycle. "
                "Passing is a real answer and costs nothing — a mediocre trade costs "
                "real spread. When you pass, 'rationale' becomes the ONLY output of "
                "this cycle and must carry its full weight: name the candidate you "
                "came closest to taking and the number that stopped you. A one-word "
                "or empty rationale on a pass is not acceptable. Set 'legs' to [] and "
                "'qty' to 0; those two are ignored on a pass, but 'rationale' is not."
            ),
        },
        "underlying": {"type": "string", "description": "Ticker, e.g. SPY"},
        "name": {"type": "string", "description": "Human label, e.g. 'Oct-16 765/770 call spread'"},
        "qty": {"type": "integer", "minimum": 1, "description": "Number of structures"},
        "limit_price": {
            "type": "string",
            "description": (
                "Net price per share as a decimal string. POSITIVE for a debit you pay, "
                "NEGATIVE for a credit you receive. Required — a structure with no price "
                "has no knowable max loss and will be rejected."
            ),
        },
        "rationale": {"type": "string",
                      "description": "Why this structure, in one or two sentences"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "legs": {
            "type": "array",
            "maxItems": MAX_LEGS,
            "items": {
                "type": "object",
                "required": ["symbol", "side"],
                "additionalProperties": False,
                "properties": {
                    "symbol": {"type": "string",
                               "description": "Full OCC symbol, e.g. SPY261016C00765000"},
                    "side": {"enum": ["buy", "sell"]},
                    "ratio_qty": {"type": "integer", "minimum": 1, "default": 1},
                },
            },
        },
    },
}


# A pass has to name what it nearly took and the number that stopped it. Below this
# it is not a reason, it is a shrug — measured against live output, real ones run
# several hundred characters and the degenerate ones come back empty or as ":".
MIN_PASS_RATIONALE_CHARS = 40


class ProposalError(ValueError):
    """A proposal that could not be parsed. Carries the reason for the journal."""


@dataclass(frozen=True)
class ParseResult:
    proposal: Proposal | None
    error: str | None = None
    # The model declined this cycle. Distinct from both a proposal and a parse
    # failure: nothing went wrong, and there is nothing to gate.
    passed: bool = False
    rationale: str = ""

    @property
    def ok(self) -> bool:
        return self.proposal is not None

    @property
    def abstained(self) -> bool:
        return self.passed and self.proposal is None

    @property
    def unexplained(self) -> bool:
        """A decline that did not say why.

        On a passing cycle the rationale is the *only* thing produced — there is no
        position left behind to inspect — so an empty one makes the cycle
        unauditable. Worth one corrective round trip, but never worth downgrading a
        considered pass into a failure, which is why this is a flag rather than a
        parse error.
        """
        return self.abstained and len(self.rationale) < MIN_PASS_RATIONALE_CHARS


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ProposalError(f"{field}={value!r} is not a decimal") from None


def parse_proposal(payload: str | dict) -> ParseResult:
    """Parse one model proposal. Never raises — returns the reason instead.

    The caller journals a rejection and moves on; a malformed proposal is an ordinary
    event in a loop that runs unattended, not an exception worth stopping for.
    """
    try:
        parsed = _parse(payload)
    except ProposalError as exc:
        return ParseResult(None, str(exc))
    except (StructureError, json.JSONDecodeError) as exc:
        return ParseResult(None, f"{type(exc).__name__}: {exc}")
    if isinstance(parsed, str):          # an abstention, carrying its reason
        return ParseResult(None, passed=True, rationale=parsed)
    return ParseResult(parsed)


def _parse(payload: str | dict) -> Proposal | str:
    """A Proposal, or the rationale string when the model declined to trade."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ProposalError(f"expected a JSON object, got {type(data).__name__}")

    unknown = set(data) - set(SCHEMA["properties"])
    if unknown:
        raise ProposalError(
            f"unknown field(s) {sorted(unknown)}. The schema is closed: a field the "
            "parser does not know is a field the gates never checked."
        )
    # `action` is required of the model so structured output always emits it, but a
    # missing one parses as "trade". Refusing a proposal that is complete apart from
    # a field describing what it already obviously is would be pedantry with a cost.
    missing = [k for k in SCHEMA["required"] if k not in data and k != "action"]
    if missing:
        raise ProposalError(f"missing required field(s) {missing}")

    # Declining is a first-class outcome, checked before anything else is validated.
    # Without it the model has no way to say "nothing here is worth taking" — the
    # instruction to propose nothing and a schema that requires a priced structure
    # cannot both be satisfied, and what comes back is qty 0 or an empty legs array,
    # which reads as a broken model rather than a considered pass.
    if str(data.get("action") or "").strip().lower() == "pass":
        # A pass with no reason is still a pass — refusing it would turn the one
        # outcome we want the model to reach for back into a failure. But it is
        # labelled as unexplained rather than given a plausible-sounding default,
        # because the journal should not put words in the model's mouth.
        return str(data.get("rationale") or "").strip() or "(no reason given)"

    underlying = str(data["underlying"]).strip().upper()
    if not underlying:
        raise ProposalError("underlying is empty")

    raw_legs = data["legs"]
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ProposalError("legs must be a non-empty array")
    if len(raw_legs) > MAX_LEGS:
        raise ProposalError(
            f"{len(raw_legs)} legs exceeds Alpaca's {MAX_LEGS}-leg ceiling for a single order"
        )

    legs: list[Leg] = []
    for i, raw in enumerate(raw_legs):
        if not isinstance(raw, dict):
            raise ProposalError(f"leg {i} is not an object")
        symbol = str(raw.get("symbol") or "").strip().upper()
        contract = parse_occ(symbol)
        if contract is None:
            raise ProposalError(f"leg {i} symbol {symbol!r} is not a valid OCC option symbol")
        if contract.root != underlying:
            raise ProposalError(
                f"leg {i} {symbol} is on {contract.root}, not the proposed {underlying}"
            )
        side_raw = str(raw.get("side") or "").strip().lower()
        if side_raw not in ("buy", "sell"):
            raise ProposalError(f"leg {i} side must be 'buy' or 'sell', got {side_raw!r}")
        side = Side(side_raw)
        ratio = raw.get("ratio_qty", 1)
        if not isinstance(ratio, int) or ratio < 1:
            raise ProposalError(f"leg {i} ratio_qty must be a positive integer, got {ratio!r}")
        legs.append(
            Leg(
                symbol,
                ratio,
                side,
                PositionIntent.BUY_TO_OPEN if side is Side.BUY else PositionIntent.SELL_TO_OPEN,
            )
        )

    qty = data["qty"]
    if not isinstance(qty, int) or qty < 1:
        raise ProposalError(f"qty must be a positive integer, got {qty!r}")

    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise ProposalError(f"confidence must be a number, got {confidence!r}")

    structure = Structure(
        name=str(data["name"]).strip() or f"{underlying} structure",
        legs=tuple(legs),
        qty=qty,
        limit_price=_decimal(data["limit_price"], "limit_price"),
    )
    return Proposal(
        structure=structure,
        underlying=underlying,
        rationale=str(data.get("rationale") or "").strip(),
        confidence=float(confidence) if confidence is not None else None,
    )


def schema_prompt() -> str:
    """The schema as it goes into the system prompt."""
    return json.dumps(SCHEMA, indent=2)
