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

#: The least context to show before a position was opened. A structure entered an
#: hour ago still needs a few candles to sit against.
MIN_LEAD_IN_DAYS = 2

#: And beyond that, a share of how long it has been held — so the lead-in grows with
#: the position rather than dwarfing it.
LEAD_IN_SHARE = 0.25

#: Hourly is the finest that still spans a month without thousands of points. Daily
#: would collapse a position held for three days into three dots.
TIMEFRAME = "1Hour"

#: Bar size by how much history is being drawn, and the bucket each one groups into.
#:
#: A fixed hourly bar is wrong at both ends. Over a two-day window it yields a dozen
#: points, and a candle needs several observations to have a body at all — an
#: hour-old position drew three flat candles. Over a two-month one it yields hundreds,
#: which is a smudge. Every charting tool picks its bar from the span; this does the
#: same, and the bucket moves with it so the candle count stays in a readable band.
_RESOLUTIONS = (
    # (window in days, bar timeframe, characters of the timestamp that share a bucket)
    (5, "15Min", 13),    # bucket by hour
    (20, "1Hour", 10),   # bucket by session
    (10_000, "1Day", 10),
)


def resolution(days: float) -> tuple[str, int]:
    """The bar size and bucket width for a window this long."""
    for limit, timeframe, width in _RESOLUTIONS:
        if days <= limit:
            return timeframe, width
    return _RESOLUTIONS[-1][1], _RESOLUTIONS[-1][2]


def window_days(structure: OpenStructure) -> float:
    """How much history the chart will cover, in days."""
    try:
        start = datetime.strptime(start_of_window(structure), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return float(LOOKBACK_DAYS)
    return max(1.0, (datetime.now(UTC) - start).total_seconds() / 86400)


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Point:
    t: str
    value: Decimal


def net_candles(points: list[Point], bucket: int = 10) -> list[dict]:
    """The net price bucketed into one candle per session.

    **Built from the observed net, never from the legs' own highs and lows.** That
    distinction is the whole of the work here. A spread's high is not the sum of its
    legs' highs: the legs move together, so when the short leg prints its high the
    long one usually has too, and the net range is a fraction of the summed one.
    Adding signed highs would draw a body and wicks spanning prices that never
    traded — a chart that looks more informative and is less true.

    So each candle's open, high, low and close are four of the hourly net values
    this function was already given. Every point drawn is a price the structure was
    actually at.

    `bucket` is how many characters of the timestamp share a candle: 10 groups by
    date, 13 by hour. It moves with the bar size so the candle count stays readable
    at any window, and because it groups on the stamp itself a gap produces no candle
    rather than a wide one — a weekend simply is not there.
    """
    buckets: dict[str, list[Point]] = {}
    for point in points:
        buckets.setdefault(str(point.t)[:bucket], []).append(point)

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")[:bucket]
    out: list[dict] = []
    for key in sorted(buckets):
        session = buckets[key]
        values = [p.value for p in session]
        out.append({
            "t": session[0].t,
            "o": values[0],
            "h": max(values),
            "l": min(values),
            "c": values[-1],
            # Whether this candle's bucket is the one the clock is currently in.
            # Without it the newest candle is indistinguishable from a closed one,
            # and a reader has no way to tell a finished hour from four minutes of
            # it — which is the difference between a shape that means something and
            # one that is about to change.
            "forming": key == now,
        })
    return out


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
    """The position's life, plus a little context — proportional, not fixed.

    It used to take a flat month before the open, which is not what the docstring
    claimed and is worse the newer the position. A structure opened this morning got
    a chart that was *entirely* prehistory: thirty days of what those two contracts
    cost as a pair before anyone held them, back when the underlying was somewhere
    else and the spread meant something different. Measured on a live QQQ position,
    the candles spanned -3.84 to -0.50 while the position itself had traded between
    -1.0 and -1.7 — the part worth looking at squeezed into a fifth of the chart by
    a month of prices nobody acted on.

    So the lead-in scales with how long the position has been held: a couple of days
    for a fresh one, a week for a month-old one. Enough to see what the structure was
    doing as it was entered, never enough to bury it.
    """
    opened = structure.opened_at
    try:
        anchor = datetime.fromisoformat(opened) if opened else datetime.now(UTC)
    except (TypeError, ValueError):
        anchor = datetime.now(UTC)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    held = max(0.0, (datetime.now(UTC) - anchor).total_seconds() / 86400)
    lead = min(LOOKBACK_DAYS, max(MIN_LEAD_IN_DAYS, held * LEAD_IN_SHARE))
    return (anchor - timedelta(days=lead)).strftime("%Y-%m-%d")


def build(structure: OpenStructure, bars: dict[str, list[dict]],
          policy: ExitPolicy, bucket: int = 10) -> dict[str, Any]:
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
        # The same prices as candles, one per session. See `net_candles` for why they
        # are bucketed from the net rather than summed from the legs' own ranges.
        # Only the prices are stringified. `str(False)` is "False", which is truthy
        # in Python and in JavaScript, so a blanket conversion marked every candle as
        # still forming and the panel would have drawn the whole chart hollow.
        "candles": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in c.items()}
            for c in net_candles(series, bucket)
        ],
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
