"""Whether the strategy engines have earned their vote.

Five engines read the tape every cycle — the indicator bias, the Markov persistence
chain, the SMC structure read, the chart patterns — and until now none of them was ever
marked. They were added because each is defensible in principle. That is not the same
as each being right on this account, on these names, in this month, and the difference
is worth money.

The journal already holds both halves. `market_view` records what every engine said
about an underlying on a cycle; `cycle_start` records the spot beside it. So this is a
measurement the system can take on itself, offline, with no new data source and no call
to a broker.

What it must not do is flatter them. Four things are closed off deliberately, and they
are most of the module:

* **An engine that declines is not scored.** A memoryless Markov chain says, in its own
  words, nothing the base rate does not; two patterns pointing opposite ways is the
  detector declining rather than a bullish read with a caveat. Scoring either as a
  directional call credits or blames it for a coin flip it refused to call.
* **Accuracy is measured against the base rate**, never against a coin. A tape that
  rose on nine days in ten makes every bullish engine look brilliant at 90%. `edge` is
  the figure that survives that, and it is the one to read.
* **A call with no future yet is not counted.** The most recent session has nothing to
  be measured against, and counting it as wrong would make every engine look worse the
  more recently it ran.
* **Below a sample floor there is no accuracy figure at all.** Three right out of four
  is 75% and means nothing; a number with no support is worse than a blank, because a
  blank cannot be acted on by mistake. Constitution VII.

Pure functions over already-parsed events, so the tests write six dicts and assert on
the answer. Reading the file and printing the table live in `cli/scorecard.py`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

BULLISH, BEARISH, NEUTRAL = "bullish", "bearish", "neutral"

#: The engines that get a row, in the order the table prints them.
ENGINES = ("bias", "markov", "smc", "patterns")

#: Directional calls an engine needs before its accuracy is printed rather than
#: withheld. Not a statistical threshold — no honest one exists at this sample size —
#: but a floor low enough to be reachable in a fortnight and high enough that a single
#: lucky week cannot carry a row.
MIN_CALLS = 20

#: How far ahead a call is measured. The structures this agent builds run 21 to 60
#: days, so a thirty-minute horizon would score noise; a day is the shortest window in
#: which a directional read on a daily chart could be said to have been right.
HORIZON_DAYS = 1

#: The Markov chain's own word for "I have nothing to add". Its `edge` is inside
#: sampling error of the base rate, and `markov.build` says so.
MEMORYLESS = "memoryless"

#: Persistence states, which are about the *move*, mapped onto the side an engine is
#: claiming. A chain that says "up persists" is making a bullish call.
_STATE_SIDE = {"up": BULLISH, "down": BEARISH, "flat": NEUTRAL}


@dataclass(frozen=True)
class Call:
    """One engine's read on one underlying at one moment, with the price beside it."""

    engine: str
    underlying: str
    ts: str
    side: str
    spot: Decimal


@dataclass(frozen=True)
class Judged:
    """A call and what the underlying did afterwards.

    `right` is three-valued and the third value carries weight. `None` means the call
    made no directional claim, or the price did not move — neither is an engine being
    wrong, and folding them into a False would understate every engine that knows when
    to keep quiet.
    """

    call: Call
    later: Decimal
    move_pct: Decimal
    right: bool | None


@dataclass(frozen=True)
class EngineScore:
    """One row of the table."""

    engine: str
    #: Everything the engine said, including the reads that claimed no direction.
    calls: int
    #: Those that claimed a direction and had a move to be measured against.
    directional: int
    correct: int
    #: `None` below the sample floor — withheld rather than guessed.
    accuracy: float | None
    #: Accuracy minus the base rate. The only figure worth acting on.
    edge: float | None
    note: str


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _when(ts) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None


def _sides(view: dict) -> dict[str, str]:
    """What each engine claimed on this view. Absent engines simply do not appear."""
    out: dict[str, str] = {}

    bias = view.get("bias")
    if bias in (BULLISH, BEARISH, NEUTRAL):
        out["bias"] = bias

    chain = view.get("persistence") or {}
    # A memoryless chain is not a prediction. See the module docstring.
    if chain and chain.get("label") != MEMORYLESS:
        side = _STATE_SIDE.get(str(chain.get("current_state") or ""))
        if side:
            out["markov"] = side

    structure = view.get("structure") or {}
    if structure.get("direction") in (BULLISH, BEARISH, NEUTRAL):
        out["smc"] = structure["direction"]

    # Patterns are plural and may disagree. Unanimity or nothing — averaging two
    # opposite detections into a side invents an opinion neither detector held.
    sides = {p.get("side") for p in (view.get("patterns") or [])}
    sides.discard(NEUTRAL)
    if len(sides) == 1:
        only = sides.pop()
        if only in (BULLISH, BEARISH):
            out["patterns"] = only

    return out


def calls(events: list[dict]) -> list[Call]:
    """Every engine call in a journal, priced from its own underlying's cycle.

    The spot comes from the most recent `cycle_start` for *that* underlying at or
    before the view. A read priced off whichever name happened to scan first would be
    measuring the wrong instrument and would never say so.
    """
    latest: dict[str, Decimal] = {}
    out: list[Call] = []
    for event in events:
        kind = event.get("event")
        underlying = event.get("underlying")
        if kind == "cycle_start":
            spot = _dec(event.get("spot"))
            if spot is not None and spot > 0 and underlying:
                latest[str(underlying)] = spot
            continue
        if kind != "market_view" or not underlying:
            continue
        spot = latest.get(str(underlying))
        if spot is None:
            # No price beside the read, so no move to measure. Not a wrong engine.
            continue
        for engine, side in _sides(event).items():
            out.append(Call(engine=engine, underlying=str(underlying),
                            ts=str(event.get("ts")), side=side, spot=spot))
    return out


def prices(events: list[dict]) -> dict[str, list[tuple[datetime, Decimal]]]:
    """Every spot the journal recorded, per underlying, in time order."""
    out: dict[str, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for event in events:
        if event.get("event") != "cycle_start":
            continue
        when, spot = _when(event.get("ts")), _dec(event.get("spot"))
        underlying = event.get("underlying")
        if when and spot is not None and spot > 0 and underlying:
            out[str(underlying)].append((when, spot))
    for series in out.values():
        series.sort(key=lambda row: row[0])
    return dict(out)


def _after(series, when: datetime, horizon_days: int) -> Decimal | None:
    """The first price at least `horizon_days` after `when`, or None if none yet."""
    deadline = when + timedelta(days=horizon_days)
    for stamp, price in series:
        if stamp >= deadline:
            return price
    return None


def judge(calls_: list[Call], prices_: dict, horizon_days: int = HORIZON_DAYS,
          ) -> list[Judged]:
    """Mark each call against what its underlying did over the horizon.

    Calls with no price at the horizon are dropped rather than marked wrong — the most
    recent session has no future to be measured against, and counting it against the
    engine would penalise recency itself.
    """
    out: list[Judged] = []
    for call in calls_:
        when = _when(call.ts)
        series = prices_.get(call.underlying) or []
        if when is None or not series:
            continue
        later = _after(series, when, horizon_days)
        if later is None:
            continue
        move = (later - call.spot) / call.spot * 100
        if call.side == NEUTRAL or move == 0:
            # No claim, or no move to test it with. Neither is a wrong engine.
            right: bool | None = None
        else:
            right = (move > 0) if call.side == BULLISH else (move < 0)
        out.append(Judged(call=call, later=later, move_pct=move, right=right))
    return out


def base_rate(judged: list[Judged]) -> float | None:
    """How often price rose across the very moves being scored.

    Taken from the judged set itself rather than a constant or a different window: an
    engine has to beat the tape it was actually read against, and a rate measured
    somewhere else would be a different question wearing the same name.
    """
    moves = [j for j in judged if j.move_pct != 0]
    if not moves:
        return None
    return round(sum(1 for j in moves if j.move_pct > 0) / len(moves), 4)


def score(judged: list[Judged], base_rate: float | None,
          min_calls: int = MIN_CALLS) -> list[EngineScore]:
    """One row per engine that said anything, ordered by edge and then by name."""
    by_engine: dict[str, list[Judged]] = defaultdict(list)
    for j in judged:
        by_engine[j.call.engine].append(j)

    rows: list[EngineScore] = []
    for engine, items in by_engine.items():
        directional = [j for j in items if j.right is not None]
        correct = sum(1 for j in directional if j.right)
        if len(directional) < min_calls:
            rows.append(EngineScore(
                engine=engine, calls=len(items), directional=len(directional),
                correct=correct, accuracy=None, edge=None,
                note=f"{len(directional)} of {min_calls} calls needed before this "
                     "says anything"))
            continue
        accuracy = round(correct / len(directional), 4)
        edge = None if base_rate is None else round(accuracy - base_rate, 4)
        rows.append(EngineScore(
            engine=engine, calls=len(items), directional=len(directional),
            correct=correct, accuracy=accuracy, edge=edge,
            note="" if base_rate is not None
                 else "no base rate: nothing moved in the scored window"))
    rows.sort(key=lambda r: (-(r.edge if r.edge is not None else -99), r.engine))
    return rows
