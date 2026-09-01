"""What the desk has learned from its own closed trades.

`committee.reflection` already puts closed structures and their realized P&L in front
of the judge. That is *advice*, and the whole thesis of this project is that a
confident model can talk its way past advice. This module is the deterministic half:
a record of which (underlying, family) pairs have been losing, which `loss_cooldown`
refuses on and no amount of rationale can argue with.

**Computed, never stored.** The ledger is already the record of what happened, and a
second file tracking streaks would be a second claim to keep in step with it — the day
they disagreed, the agent would bench a pair that had just won, or trade one that had
just lost twice. Recomputing from the ledger every cycle costs a walk over a list and
cannot drift.

Three properties worth stating, because each is a decision rather than an accident:

* **The run is consecutive, not cumulative.** A pair that just worked is not a pair to
  stop trading, however badly it did last month. A win resets it.
* **The bench lapses.** A cooldown that never expires is a delisting, and this system
  discovers its universe from the tape — a name benched forever would quietly shrink
  the tradeable world every time it was wrong twice.
* **It keys on the pair, not the symbol.** Being wrong twice about calls says nothing
  about puts, and benching the whole underlying throws away the half of the book that
  was never tested.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from halstreet.strategy.family import classify

#: `(underlying, family) -> why it is benched`.
BenchRecord = dict[tuple[str, str], str]


def _closed_on(structure: Any) -> date | None:
    """The session a structure closed on, or None if the stamp cannot be read.

    A date rather than an instant, because the window below is counted in sessions.
    `clock.today()` is the only time source the trading path may read — there is no
    `clock.now()`, and a host wall-clock read here is a lint error precisely so a rule
    about the exchange's calendar cannot end up answering the host's.
    """
    try:
        return datetime.fromisoformat(str(structure.closed_at)).date()
    except (TypeError, ValueError):
        return None


def benched_pairs(structures: list[Any], *, after: int, days: int,
                  today: date) -> BenchRecord:
    """Which (underlying, family) pairs are resting, and why.

    `after` consecutive losing closes benches a pair for `days` sessions from the
    **most recent** loss — not from the first, because the run is what is being timed
    out and the newest loss is the freshest evidence that it continues.

    Sessions rather than hours, since a trader thinks in "not again today" and the
    only clock this layer may read is `clock.today()`.

    A structure with no realized figure is skipped rather than counted: unknown is not
    a loss, and benching on the strength of a number nobody has is the failure mode
    this codebase names most often. One with an unreadable close time is skipped too,
    for a narrower reason — a cooldown whose clock cannot be read can never expire,
    so it is not allowed to start one.
    """
    if after <= 0:
        return {}

    # (when it closed, what it lost) per pair, oldest first.
    runs: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
    dated = []
    for structure in structures:
        when = _closed_on(structure)
        if when is not None:
            dated.append((when, structure))

    for when, structure in sorted(dated, key=lambda pair: pair[0]):
        realized = structure.realized()
        if realized is None:
            continue
        key = (str(structure.underlying), classify(structure.legs or {}))
        if realized < 0:
            runs.setdefault(key, []).append((when, realized))
        else:
            # A win — or a scratch, which is not a loss either — ends the run.
            runs[key] = []

    out: BenchRecord = {}
    for (underlying, family), losses in runs.items():
        if len(losses) < after:
            continue
        last, _ = losses[-1]
        lifts = last + timedelta(days=max(days, 0))
        # `>` not `>=`: a bench that lifts today has already served its time. Written
        # this way round so `days=0` is a coherent setting — the run is recorded, and
        # nothing is ever benched — rather than an off-by-one that rests a pair for a
        # session nobody asked for.
        if today > lifts:
            continue
        lost = -sum(amount for _, amount in losses)
        # The figure as well as the count, because "two in a row" and "two in a row
        # for $840" are different facts and only one of them says how much it matters.
        out[(underlying, family)] = (
            f"{len(losses)} losing {family} trade(s) in a row on {underlying}, "
            f"${lost:,.2f} in total, the last closed {last:%Y-%m-%d}. "
            f"Resting until {lifts:%Y-%m-%d}."
        )
    return out
