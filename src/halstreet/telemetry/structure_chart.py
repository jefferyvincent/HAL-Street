"""One structure's price history, against the levels its exit policy acts on.

The panel draws a line and three rules across it: where it was opened, where the
profit target sits, and where the stop sits. Those three come from
`manager.exit_levels`, which is the same function `evaluate_exit` is pinned to by
test — so the picture cannot drift from the rule it depicts. A chart that disagrees
with the policy is worse than no chart, because it is believed.

**The net, not a leg.** A spread's price is `sum(signed * close)` across its legs, on
the same sign convention `mark_structure` uses: positive means it would cost you to be
in the position, negative means you hold it for a credit. Charting one leg would show
a line that moves for reasons the position does not care about.

**Only structures the agent traded.** The route takes a `structure_id` from our own
ledger and resolves the symbols itself. The panel cannot name contracts, which means
this is not a general market-data proxy that happens to live behind a read-only
dashboard — it can ask about the book, and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.agent.manager import ExitPolicy, exit_levels

#: How far back to chart. A structure is opened inside the scan window, so this covers
#: its whole life with room for the run-up that preceded it.
LOOKBACK_DAYS = 30

#: Hourly is the finest that still spans a month without thousands of points. Daily
#: would collapse a position held for three days into three dots.
TIMEFRAME = "1Hour"


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Point:
    t: str
    value: Decimal


def net_series(structure: OpenStructure, bars: dict[str, list[dict]]) -> list[Point]:
    """The structure's own price over time.

    Aligned on timestamps present in *every* leg. A bar missing from one leg is a
    partial mark, and `mark_structure` already refuses to act on one of those — the
    chart holds itself to the same standard rather than drawing a line whose dips are
    an absent quote rather than a price.
    """
    by_leg: dict[str, dict[str, Decimal]] = {}
    for symbol in structure.legs:
        rows = bars.get(symbol) or []
        closes: dict[str, Decimal] = {}
        for row in rows:
            when, close = row.get("t"), _dec(row.get("c"))
            if when and close is not None:
                closes[str(when)] = close
        by_leg[symbol] = closes

    if not by_leg or any(not closes for closes in by_leg.values()):
        return []

    shared = set.intersection(*(set(closes) for closes in by_leg.values()))
    out: list[Point] = []
    for when in sorted(shared):
        total = sum(by_leg[symbol][when] * signed for symbol, signed in structure.legs.items())
        out.append(Point(t=when, value=total))
    return out


def start_of_window(structure: OpenStructure) -> str:
    """Far enough back to show the position's whole life, and no further."""
    opened = structure.opened_at
    try:
        anchor = datetime.fromisoformat(opened) if opened else datetime.now(UTC)
    except (TypeError, ValueError):
        anchor = datetime.now(UTC)
    return (anchor - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")


def build(structure: OpenStructure, bars: dict[str, list[dict]],
          policy: ExitPolicy) -> dict[str, Any]:
    """Everything the chart needs, in the shape the panel renders."""
    series = net_series(structure, bars)
    entry = structure.entry_price
    levels = exit_levels(entry, policy) if entry is not None else None

    return {
        "structure_id": structure.structure_id,
        "name": structure.name,
        "underlying": structure.underlying,
        "qty": structure.qty,
        "open": structure.is_open,
        "opened_at": structure.opened_at,
        "closed_at": structure.closed_at,
        "dte": structure.dte(),
        "legs": [{"symbol": s, "signed": n} for s, n in sorted(structure.legs.items())],
        "series": [{"t": p.t, "v": str(p.value)} for p in series],
        # None when the entry price is unknown — the panel says so rather than drawing
        # three lines through a number nobody has.
        "levels": levels.to_prompt() if levels else None,
        "entry_filled": structure.entry_filled,
        "exit_price": None if structure.exit_price is None else str(structure.exit_price),
        "exit_filled": structure.exit_filled,
        "policy": {
            "take_profit_pct": str(policy.take_profit_pct),
            "stop_loss_pct": str(policy.stop_loss_pct),
            "force_close_dte": policy.force_close_dte,
        },
        "realized_usd": None if (r := structure.realized()) is None else str(r),
    }


def find(ledger: Ledger, structure_id: str) -> OpenStructure | None:
    return next((s for s in ledger.structures if s.structure_id == structure_id), None)
