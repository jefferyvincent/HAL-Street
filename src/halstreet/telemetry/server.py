"""A read-only view of the run, for the desktop panel.

**Read-only, and that is a design decision rather than an omission.** There is no
POST, no order endpoint, no way to clear the halt latch, no way to change a limit. A
dashboard that can trade is a second path to the broker that does not go through
`gates/`, and the entire argument of this project is that there is exactly one such
path. Clearing a latched halt is a deliberate human act at the CLI (`--clear-halt`),
where it is visible in shell history, not a button someone can hit twice.

**The socket is send-only, and provably so.** A WebSocket is duplex by nature, which
makes it the one thing here that could quietly become a write path — a client frame
carrying `{"action": "halt"}` is only dangerous if something reads it. Nothing does.
`receive`, `receive_text`, `receive_json` and `iter_*` appear nowhere in this module,
so there is no code for a crafted frame to reach; a test greps for them. Disconnects
surface when a send fails, which is why the push loop heartbeats even when nothing has
changed rather than blocking on a read.

Everything served is derived from files already on disk — the journal, the ledger, the
circuit state. The server holds no state of its own and can be started, killed and
restarted mid-run without the agent noticing.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from halstreet import clock, paths
from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.brainstem.schedule import (
    pass_window_seconds,
    scan_interval_seconds,
    silent_after_seconds,
)
from halstreet.agent.cerebellum.manager import (
    CONTRACT_MULTIPLIER,
    ExitPolicy,
    mark_legs,
    mark_structure,
)
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.gates import ALL_GATES
from halstreet.gates.base import FAMILIES, Limits, family_of
from halstreet.marketdata.discovery import MAX_TAGS_PER_HEADLINE
from halstreet.strategy.exposure import agrees, exposure_of
from halstreet.telemetry import pnl, pricing, structure_chart
from halstreet.telemetry.journal import Journal

# The panel is a Vite build. In production the bundle is served from here, same origin
# as the API, so the browser and the Tauri shell both reach /api and /ws with no CORS
# and no second port. In development Vite serves it on :1420 and proxies here instead.
DIST = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "dist"

# How often the socket pushes when nothing has changed. Two jobs: it keeps the footer
# clock honest, and it is how a dead client is noticed at all — nothing reads from the
# socket, so a failed send is the only disconnect signal there is.
HEARTBEAT_S = 5.0

# How often the files behind the snapshot are stat'd for a change. Cheap enough to do
# often; a scan cycle writes several records, so this coalesces them into one push.
WATCH_S = 0.5

# How much history the panel gets. Enough to show a session, small enough that a
# five-second poll is not shipping a quarter of a megabyte each time — the payload
# carries exactly what the panel renders and nothing else. Anyone who wants the raw
# stream reads the JSONL directly; it is append-only and always there.
RECENT_DECISIONS = 40

# Closed structures the book view lists.
RECENT_CLOSED = 25

# Points on the equity chart. A scan every 30 minutes makes this several sessions.
EQUITY_POINTS = 500


def _plain(value: Any) -> Any:
    """Decimals to strings, never to floats — the journal's rule, kept here too."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


#: Committee sessions kept for the panel. Each carries two researchers' prose, so
#: this is the largest thing in the payload and the count is deliberately small.
RECENT_COMMITTEES = 12


#: How much of the run to show as activity. Enough for a scan of three underlyings
#: to be visible whole, few enough that a five-second poll stays small.
RECENT_ACTIVITY = 24

#: What the agent spends its time doing, in the order it does it.
_ACTIVITY = ("session", "cycle_start", "candidates", "committee", "proposal",
             "gate_decision", "order", "fill_correction", "exit_decision",
             "divergence", "halt", "error")


def _committees(events: list[dict]) -> list[dict]:
    """Recent committee sessions, newest first, each paired with what it decided.

    The whole deliberation, not a summary of it. A committee whose reasoning is not
    readable is the same opacity as one model call at four times the price, and
    until now it was written to the journal and shown nowhere.

    Paired by walking forward to the next proposal for the same underlying: the loop
    writes `committee` then `proposal` back to back, and joining them here saves the
    panel from re-deriving an ordering it cannot see.
    """
    out: list[dict] = []
    for i, event in enumerate(events):
        if event.get("event") != "committee":
            continue
        root = event.get("underlying")
        verdict = next(
            (e for e in events[i + 1:i + 4]
             if e.get("event") == "proposal" and e.get("underlying") == root),
            {},
        )
        gates = next(
            (e for e in events[i + 1:i + 6]
             if e.get("event") == "gate_decision" and e.get("underlying") == root),
            {},
        )
        out.append({
            "ts": event.get("ts"),
            "underlying": root,
            "headlines": event.get("headlines", 0),
            "catalyst": event.get("catalyst") or {},
            "bull": event.get("bull") or "",
            "bear": event.get("bear") or "",
            # Which cases the record bounded — see `committee.clip`. Older records
            # predate the field and get an empty list, which is the truthful answer
            # for them: nobody wrote down whether anything was lost.
            "clipped": event.get("clipped") or [],
            # What the desk was handed: every structure the deterministic side built,
            # each one already scored against the catalyst's read. It was written down
            # from the first committee and shown nowhere — so the tab had the argument
            # and not the thing being argued about.
            "burn": event.get("burn") or None,
            "reflection": event.get("reflection") or [],
            "tokens": event.get("tokens") or {},
            # And where they went. One total says the committee is expensive; this
            # says which quarter of it to look at, and which model spent it.
            "stages": event.get("stages") or {},
            "errors": event.get("errors") or [],
            # What came out of it, so the tree ends somewhere rather than trailing off.
            "outcome": {
                "passed": bool(verdict.get("passed")),
                "ok": bool(verdict.get("ok")),
                "rationale": verdict.get("rationale") or "",
                "structure": (verdict.get("structure") or {}).get("name")
                             or gates.get("structure") or "",
                "error": verdict.get("error"),
                "approved": gates.get("approved"),
                "rejected_by": gates.get("rejected_by") or [],
            },
        })
    return list(reversed(out[-RECENT_COMMITTEES:]))


#: Beyond this, the agent is not mid-cycle — it has stopped, crashed, or is waiting
#: for the next scan. A cycle is seconds of work; a stage that has said nothing for
#: three minutes is not a stage in progress, and drawing a spinner over it is worse
#: than drawing nothing because it says the opposite of what is true.
IN_FLIGHT_S = 180.0

#: What the agent is doing *next*, by the last thing it wrote down.
#:
#: Each record is written when a stage finishes, so the label is the stage that
#: follows it — "candidates" on disk means the committee is now deliberating, which
#: is the slow one and the one anyone watching is actually waiting on.
#:
#: `proposal` is deliberately absent. A cycle that ends in a considered pass writes
#: it last and stops, so treating it as a stage would show "at the gates" for minutes
#: on a book that is doing nothing. What follows a proposal is gate evaluation, which
#: is deterministic and takes microseconds — there is no waiting to report.
_STAGE = {
    "cycle_start": "reading the tape",
    "market_view": "building structures",
    "candidates": "deliberating",
    "committee": "writing the proposal",
}

#: The same rule one level in, for the stages inside a deliberation.
#:
#: `candidates` above can only ever say "deliberating", because from that record alone
#: there is no telling whether a committee is about to sit or a single call is about to
#: run. Once a stage record lands there is, and the four model calls stop being one
#: unchanging word over the slowest minute of the cycle.
#:
#: No entry for `judge`: the full `committee` record is written the moment it returns,
#: and `_STAGE` above already speaks for that.
_COMMITTEE_STAGE = {
    "catalyst": "bull and bear arguing",
    "debate": "the judge deciding",
}

#: In the order they run, so the panel can draw the ones still to come.
COMMITTEE_STAGES = ("catalyst", "debate", "judge")


def _in_flight(events: list[dict]) -> dict | None:
    """What the agent is in the middle of, if anything, from the last record it wrote.

    Most cycles produce no gate decision, so a panel keyed on outcomes looks asleep
    while the agent is working — the same reason the activity feed exists. The
    committee view had the sharper version of the problem: its slowest stage is three
    model calls deep, and there was nothing on the screen between "nothing here yet"
    and a finished card appearing.

    Derived rather than pushed. Nothing reports "I am busy" — the agent writes a
    record when a stage *finishes*, so the last record plus a clock says what is
    running now, and only the last one: walking back past it to find a stage would
    report one forever, because every completed cycle has four sitting behind its
    outcome. It can be wrong in exactly one direction: a process killed mid-cycle
    looks busy until `IN_FLIGHT_S` passes, which is why that ceiling is short.
    """
    if not events:
        return None
    event = events[-1]
    kind = str(event.get("event"))
    if kind == "committee_stage":
        stage = _COMMITTEE_STAGE.get(str(event.get("stage")))
    else:
        stage = _STAGE.get(kind)
    if stage is None:
        # The last thing written finished something. Walking further back to find a
        # stage would report one forever: every completed cycle has four of them
        # sitting just behind its outcome.
        return None
    started = _age(event.get("ts"))
    if started is None or started > IN_FLIGHT_S:
        return None
    underlying = event.get("underlying") or ""
    done = _stages_done(events, underlying)
    read = next((e for e in done if e.get("stage") == "catalyst"), {})
    return {"stage": stage, "event": kind,
            "underlying": underlying, "since": event.get("ts"),
            "done": [str(e.get("stage")) for e in done],
            "lean": read.get("lean"), "confidence": read.get("confidence"),
            "catalyst_error": read.get("error")}


def _stages_done(events: list[dict], underlying: str) -> list[dict]:
    """The stage records belonging to the deliberation running right now.

    Bounded at the last `cycle_start`, and matched on the underlying. The agent walks
    the universe one name at a time into one journal file, so without both the live
    card would open on the next name already showing the previous one's catalyst read
    — a real read, attributed to the wrong symbol, on the one surface whose entire job
    is to say what is happening now.
    """
    if not underlying:
        return []
    cycle = 0
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("event") == "cycle_start":
            cycle = i
            break
    return [e for e in events[cycle:]
            if e.get("event") == "committee_stage" and e.get("underlying") == underlying]


def _age(ts: Any) -> float | None:
    """Seconds since a journal timestamp, or None if it cannot be read as one."""
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(str(ts))).total_seconds()
    except (TypeError, ValueError):
        return None


def _activity_line(event: dict) -> str:
    """One short phrase for what happened. No prices — this is a pulse, not a record."""
    kind = event.get("event")
    if kind == "session":
        return f"market {event.get('state')}"
    if kind == "cycle_start":
        return f"scanning at {event.get('spot')}"
    if kind == "candidates":
        n = event.get("count") or 0
        return f"{n} structure(s) built" if n else "nothing worth building"
    if kind == "committee":
        catalyst = (event.get("catalyst") or {}).get("lean", "?")
        errors = event.get("errors") or []
        note = f", {len(errors)} stage(s) unavailable" if errors else ""
        return f"committee read {catalyst} on {event.get('headlines', 0)} headline(s){note}"
    if kind == "proposal":
        if event.get("passed"):
            # The rationale, because on a passing cycle it is the only thing that
            # survives — there is no position to look at afterwards.
            return f"passed — {event.get('rationale') or 'no reason given'}"
        return "proposed" if event.get("ok") else f"unusable answer: {event.get('error')}"
    if kind == "gate_decision":
        if event.get("approved"):
            return f"approved by all {len(event.get('gates') or [])} gates"
        return f"rejected by {', '.join(event.get('rejected_by') or []) or 'a gate'}"
    if kind == "order":
        verb = "closing" if event.get("intent") == "close" else "opening"
        return f"{verb} order {'submitted' if event.get('submitted') else 'not sent'}"
    if kind == "exit_decision":
        return f"exit check: {event.get('action')}"
    if kind == "halt":
        return f"HALTED — {event.get('reason') or event.get('detail') or ''}"
    if kind == "error":
        return f"error in {event.get('where')}"
    return kind or ""


def _activity(events: list[dict]) -> list[dict]:
    """The run as a pulse, newest last.

    The panel was built around gate decisions, and an agent that declines every
    cycle produces none — so on a day of considered passes every view was empty and
    the whole thing read as broken. Most of what this agent does is scan, read the
    tape, deliberate and decline, and none of that was visible anywhere.
    """
    out = [
        {"ts": e.get("ts"), "event": e.get("event"),
         "underlying": e.get("underlying") or "", "detail": _activity_line(e)}
        for e in events if e.get("event") in _ACTIVITY
    ]
    return out[-RECENT_ACTIVITY:]


def _decisions_with_positions(events: list[dict]) -> list[dict]:
    """Gate decisions, each carrying the structure it became if it became one.

    An approved decision and the position it opened were connected by nothing but a
    name, so the panel could show the verdict and could not offer a way through to
    the trade. Names are not identifiers — two spreads a week apart can share one —
    and the id was being generated at submission and never written to the journal.

    Joined on the order that follows: `_submit` journals the order and then records
    the structure under the same id, so an approved decision is followed within a
    couple of records by the order that carries it. A decision that was rejected, or
    approved in a dry run, gets `None` and the panel offers nothing rather than a
    link to a position that does not exist.
    """
    # Whichever cycle each decision belongs to, so a record written before the flag
    # existed can still be told apart. The agent stamps `dry_run` on the decision
    # itself now; this covers the history, and a stamped record always wins.
    armed: bool | None = None
    dry_at: dict[int, bool | None] = {}
    for i, event in enumerate(events):
        if event.get("event") == "cycle_start":
            armed = bool(event["dry_run"]) if "dry_run" in event else None
        dry_at[i] = armed

    out: list[dict] = []
    for i, event in enumerate(events):
        if event.get("event") != "gate_decision":
            continue
        # Only an approved decision can have become a position. A rejected one is
        # never submitted, so the next order in the file belongs to a different
        # decision entirely — and joining on proximity alone handed a rejection
        # somebody else's trade.
        opened = next(
            (e for e in events[i + 1:i + 4]
             if e.get("event") == "order" and e.get("intent", "open") == "open"
             and e.get("submitted") and e.get("structure_id")
             and e.get("structure") == event.get("structure")),
            None,
        ) if event.get("approved") else None
        out.append({**event,
                    "structure_id": opened.get("structure_id") if opened else None,
                    # None means unknown rather than "armed": a journal from before
                    # this was recorded cannot say, and the panel should not claim
                    # otherwise in either direction.
                    "dry_run": event.get("dry_run", dry_at.get(i))})
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _round(value: Any, places: int) -> Any:
    """Quantize for display, leaving anything unparseable exactly as it came."""
    number = _dec(value)
    if number is None:
        return value
    return number.quantize(Decimal(10) ** -places)


def _marks_by_structure(events: list[dict]) -> dict[str, dict]:
    """The agent's own latest read of each open position.

    A per-position mark needs live quotes, and the snapshot must not reach the
    broker — it is polled every five seconds. But the agent prices the whole book
    every cycle and writes the result down, so the freshest honest number is already
    in the journal. This is that number, labelled as of when it was taken rather
    than presented as live.
    """
    out: dict[str, dict] = {}
    for event in events:
        if event.get("event") != "exit_decision":
            continue
        key = str(event.get("structure_id") or "")
        if key:
            out[key] = {
                "mark": event.get("mark"),
                "unrealized_usd": event.get("unrealized_usd"),
                "dte": event.get("dte"),
                "action": event.get("action"),
                "reason": event.get("reason"),
                "as_of": event.get("ts"),
            }
    return out


#: Points in a position's spark line. A thumbnail two centimetres wide cannot show
#: more, and the whole history is one route away on the chart itself.
SPARK_POINTS = 40


def _mark_series(events: list[dict]) -> dict[str, list[dict]]:
    """Every mark the agent has taken of each position, oldest first.

    The console showed one number and no shape: a position at -$19 could have been
    drifting there all day or have fallen off a cliff in the last cycle, and those are
    different situations. This is the difference, and it costs nothing — the agent
    prices the whole book every cycle and writes the result down, so the series is
    already on disk.

    Its own marks rather than a price feed, which is the honest framing and also the
    only one available here: the snapshot is polled every five seconds and must not
    reach the broker. Sampled once per cycle, so the spacing is however often the
    agent looked — half-hourly on a slow scan. That makes it a record of what the desk
    saw, not a tick chart, and the card says so by stamping the last read's age.

    Unparseable marks are skipped rather than plotted as zero. A gap in a line is a
    gap; a zero is a claim the structure was worthless.
    """
    out: dict[str, list[dict]] = {}
    for event in events:
        if event.get("event") != "exit_decision":
            continue
        key = str(event.get("structure_id") or "")
        value = _dec(event.get("mark"))
        if not key or value is None:
            continue
        out.setdefault(key, []).append({"t": event.get("ts"), "v": value,
                                        "pnl": _dec(event.get("unrealized_usd"))})
    return {k: v[-SPARK_POINTS:] for k, v in out.items()}


def _spend(events: list[dict]) -> dict:
    """What the model calls have cost this journal, in tokens and where possible money.

    **Counted from `proposal` events only, and that is the whole subtlety.** The
    committee journals its session total and the loop then journals the same figure
    again on the proposal it produced — the two records carry one spend between them,
    and summing both doubles it. I did exactly that when first reading these numbers
    and reported 1.39M input against a real 693K. The proposal record is the one to
    count because it is the only one present on both paths: with the committee off
    there is no committee record at all, and the single call still journals its usage
    there.

    The per-model split comes from `committee.stages`, which is the only place a model
    name appears. On a committee cycle the stages sum exactly to the proposal's total
    — catalyst plus debate plus judge — so a cycle is either fully attributed or not
    attributed at all, and whatever the stages do not account for is reported as
    `unattributed` rather than silently assigned to something.

    Cost is `None` for a model with no configured price, and the total is marked
    `partial` when any counted token had none. A dollar figure that quietly omits a
    tier is worse than no dollar figure, and the tiering put two thirds of the input
    on the tier whose price this project cannot cite.
    """
    total = {"in": 0, "out": 0, "cache_read": 0}
    by_model: dict[str, dict[str, int]] = {}
    cycles = 0

    for event in events:
        kind = event.get("event")
        tokens = event.get("tokens")
        if kind == "proposal" and isinstance(tokens, dict):
            cycles += 1
            for key in total:
                value = tokens.get(key)
                if isinstance(value, int):
                    total[key] += value
        elif kind == "committee":
            stages = event.get("stages")
            if not isinstance(stages, dict):
                # A string here iterates one character at a time; an int raises
                # outright. This route is polled every five seconds, so either one
                # empties the whole panel. Found by test, like the identical hole in
                # `_gate_readings`.
                continue
            for spend in stages.values():
                if not isinstance(spend, dict):
                    continue
                model = spend.get("model")
                if not model:
                    continue  # a stage that made no call — see `catalyst`
                row = by_model.setdefault(str(model), {"in": 0, "out": 0, "cache_read": 0})
                for key in row:
                    value = spend.get(key)
                    if isinstance(value, int):
                        row[key] += value

    table = pricing.from_env()
    models = []
    priced_cost = Decimal(0)
    partial = False
    for name in sorted(by_model):
        row = by_model[name]
        money = pricing.cost(name, tokens_in=row["in"], tokens_out=row["out"], table=table)
        if money is None:
            partial = True
        else:
            priced_cost += money
        models.append({"model": name, **row, "cost_usd": money})

    attributed = {k: sum(r[k] for r in by_model.values()) for k in total}
    # What the stages could not account for: every cycle run before per-stage
    # accounting existed, and every cycle run with the committee off.
    unattributed = {k: max(0, total[k] - attributed[k]) for k in total}
    if unattributed["in"] or unattributed["out"]:
        partial = True

    return {
        "total": total,
        "cycles": cycles,
        "models": models,
        "unattributed": unattributed,
        # Rounded once, at the edge, like every other money figure here.
        "cost_usd": _round(priced_cost, 2),
        # True when some counted tokens had no price. The number below it is a floor,
        # not a total, and the panel says so rather than implying otherwise.
        "partial": partial,
        "prices": {k: {"in": str(v[0]), "out": str(v[1])} for k, v in table.items()},
    }


def _patterns_by_underlying(events: list[dict]) -> dict[str, list[dict]]:
    """The most recent confirmed patterns per underlying, from the market views.

    Latest only. Every scan writes one, and a position held for a week would
    otherwise accumulate every read the agent has ever taken of its underlying —
    the panel wants what the chart is doing now, not a history of what it did.
    """
    out: dict[str, list[dict]] = {}
    for event in events:
        if event.get("event") != "market_view":
            continue
        root = str(event.get("underlying") or "").upper()
        if root:
            out[root] = list(event.get("patterns") or [])
    return out


def _pattern_read(structure: Any, by_underlying: dict[str, list[dict]]) -> dict:
    """One position's chart read: its exposure, and which patterns run against it.

    Surfacing only, and the shape says so — `against` is a list to show, never a
    verdict to act on. Nothing downstream of this dictionary can close a position.

    Exposure is a property of the whole structure rather than of a leg, which is
    the part HAL's single-instrument version cannot answer here: a put credit
    spread is short a put and long a further put, reads "bearish" leg by leg, and
    is bullish. See `strategy.exposure`.
    """
    found = by_underlying.get(str(structure.underlying).upper(), [])
    lean = exposure_of(structure.legs)
    against, confirming = [], []
    for pattern in found:
        verdict = agrees(lean, str(pattern.get("side") or ""))
        if verdict is False:
            against.append(pattern)
        elif verdict is True:
            confirming.append(pattern)
    return {
        "exposure": lean,
        "patterns": found,
        "against": against,
        "confirming": confirming,
    }


def _legs_view(structure: Any, chain: dict[str, dict]) -> list[dict]:
    """Each leg of one structure: what it is, what it costs now, what it has done.

    The question "the spread is ten dollars down — which leg?" had no answer anywhere
    in this system until the opening order's per-leg fills were kept, because the
    ledger recorded the net and discarded the rest.

    Every figure here is scaled by the structure's size, like the P&L beside it, so a
    two-contract position's legs add up to the two-contract total rather than to a
    single spread. `basis` is the exception and is deliberately per contract: it is a
    price, and a price does not change when you trade ten.

    Nothing is computed twice. `mark_legs` is what `mark_structure` sums, so a leg
    shown as unpriced here is a leg the net is refusing to include, and the P&L column
    adds to the structure's own P&L exactly rather than approximately.
    """
    qty = structure.qty
    return [
        {
            "symbol": leg.symbol,
            "signed": leg.signed,
            "contracts": leg.signed * qty,
            "bid": leg.bid,
            "ask": leg.ask,
            "mid": leg.mid,
            # What it filled at, per contract, and what it is worth now in dollars.
            "basis": leg.basis,
            "value_usd": leg.value(qty),
            "unrealized_usd": leg.pnl(qty),
        }
        for leg in mark_legs(structure, chain)
    ]


#: How long the journal can go quiet before its session record stops being current.
#:
#: The scheduler writes a boundary when it crosses one, so the record only stays true
#: while something is running to write the next. When the agent exits mid-session
#: nothing writes the close, and the badge went on asserting OPEN into the evening —
#: seen on 2026-08-27, where the soak stopped at 15:40 and the panel still said the
#: market was open at 16:10.
#:
#: Generous, because a cycle takes minutes and a quiet stretch is not a dead agent.
#: The point is to stop a *dead* one making a live claim, not to blink.
SESSION_STALE_S = 900.0


def _when(value: Any) -> datetime | None:
    """One of Alpaca's boundary timestamps, parsed. They carry their own offset —
    `2026-08-27 16:00:00-04:00` — so nothing here needs to know where the exchange is."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def _crossed(record: dict) -> tuple[str, str] | None:
    """The most recent session boundary that has already passed, and what it implies.

    The session record carries the broker's own answer to "when does this session
    next open and next close". Those are forward-looking and published *by Alpaca*,
    so reading them is not a second claim about when the market is open — it is the
    same claim `clock.py` already relies on, read one step further ahead.

    That matters because the alternative is a hardcoded exchange calendar, which is
    the thing this codebase specifically refuses to keep: New York, daylight saving,
    half-days, holidays. None of that is knowledge this process should hold.

    The later of the two passed boundaries wins, so this keeps working across a whole
    weekend: on Saturday the Friday close is the last thing that happened, and on
    Monday morning it is the Monday open.
    """
    now = datetime.now(UTC)
    passed = [
        (when, state, str(record.get(key)))
        for key, state in (("next_open", "open"), ("next_close", "closed"))
        if (when := _when(record.get(key))) is not None and when <= now
    ]
    if not passed:
        return None
    _, state, raw = max(passed)
    return state, raw


#: How far apart two `cycle_start` records can be and still belong to one scan.
#:
#: From the cadence, not a constant. Ten minutes is right at the thirty-minute default
#: and wrong at five, where it is the whole gap between passes and would merge two of
#: them into one table. `schedule.pass_window_seconds` owns the rule.


def _pass(events: list[dict]) -> dict | None:
    """The scan the agent is on, symbol by symbol, in the order it works them.

    The panel could say what the agent was doing *right now* and what it had decided
    *eventually*, with nothing in between. A pass is a minute or two in which four
    names are already settled and one is mid-committee, and none of that shape was
    anywhere — so watching the agent meant watching one amber word.

    Segmented on `cycle_start`, which the loop writes once per underlying. Everything
    between one and the next belongs to that name, and events are matched on the
    underlying as well: one journal is worked one name at a time, and a row that
    collected the next symbol's menu would be a table that lies while looking right.

    The last row is the live one, if anything is. Nothing here decides *whether* the
    agent is running — `_in_flight` owns that, from the same records — this only says
    which row it would be on.
    """
    starts = [i for i, e in enumerate(events) if e.get("event") == "cycle_start"]
    if not starts:
        return None

    # The trailing run of scans close enough together to be one pass.
    first = starts[-1]
    for a, b in zip(reversed(starts[:-1]), reversed(starts[1:]), strict=True):
        gap = _gap(events[a].get("ts"), events[b].get("ts"))
        if gap is None or gap > pass_window_seconds():
            break
        first = a

    live = _in_flight(events) is not None
    bounds = [i for i in starts if i >= first] + [len(events)]
    rows = [_pass_row(events[a:b], last=(b == len(events)) and live)
            for a, b in itertools.pairwise(bounds)]
    return {"at": events[first].get("ts"), "rows": rows}


def _pass_row(segment: list[dict], *, last: bool) -> dict:
    """One name's journey through the cycle, from its own records only."""
    head = segment[0]
    name = head.get("underlying")
    # This name's records, plus the ones that carry no name at all. The unnamed ones
    # are not a leak: `order` is written without an underlying, and a scan-level
    # `error` inside this segment happened between this name's cycle_start and the
    # next one, so it is this name's. A record belonging to another symbol is
    # excluded by having that symbol on it.
    mine = [e for e in segment if e.get("underlying") in (name, None)]

    def latest(kind: str) -> dict | None:
        return next((e for e in reversed(mine) if e.get("event") == kind), None)

    menu, proposal = latest("candidates"), latest("proposal")
    gates, order, failed = latest("gate_decision"), latest("order"), latest("error")

    verdict = None
    if gates is not None:
        verdict = "approved" if gates.get("approved") else "rejected"

    # Order last, and only a *submitted* one counts as the end of the line. A dry run
    # gates and journals exactly as a live cycle does and stops before submission;
    # reporting it as submitted is the failure the dry-run label exists to prevent.
    if failed is not None:
        outcome = "error"
    elif order is not None and order.get("submitted"):
        outcome = "submitted"
    elif verdict is not None:
        outcome = verdict
    elif proposal is not None and proposal.get("passed"):
        outcome = "passed"
    elif proposal is not None and not proposal.get("ok"):
        outcome = "error"
    elif menu is not None and not (menu.get("count") or 0):
        outcome = "no menu"
    elif last:
        outcome = "running"
    else:
        # Started, wrote nothing else, and the agent has moved on. Not an outcome we
        # can name — and naming one anyway is how a table invents a decision.
        outcome = "unfinished"

    return {
        "underlying": name,
        "at": head.get("ts"),
        "spot": head.get("spot"),
        "menu": None if menu is None else (menu.get("count") or 0),
        "committee": None if latest("committee") is None else "sat",
        "proposal": None if proposal is None
                    else ("passed" if proposal.get("passed")
                          else "proposed" if proposal.get("ok") else "failed"),
        "gates": verdict,
        "rejected_by": (gates or {}).get("rejected_by") or [],
        "order": None if order is None
                 else ("submitted" if order.get("submitted") else "held"),
        "error": None if failed is None else str(failed.get("detail") or failed.get("error") or ""),
        "outcome": outcome,
        "running": last and outcome == "running",
    }


def _gap(a: Any, b: Any) -> float | None:
    """Seconds between two journal stamps, or None if either cannot be read."""
    try:
        return abs((datetime.fromisoformat(str(b)) - datetime.fromisoformat(str(a)))
                   .total_seconds())
    except (TypeError, ValueError):
        return None


#: How old a macro read may be and still be this scan's.
#:
#: One cadence plus a pass's worth of slack. Beyond it the read belongs to a scan that
#: has already been superseded, and it must not be drawn beside the current one.
MACRO_FRESH_S = 45 * 60


def _macro(events: list[dict]) -> dict | None:
    """The macro-odds read for the scan in progress, or None if this one has no read.

    Aged out, and that is the whole of it. Walking back to the newest read of any age
    meant a pass that could not reach the venue drew the *previous* pass's prices: the
    agent recorded "could not ask" and the panel showed this morning's numbers beside
    this afternoon's scan. Two surfaces disagreeing about one fact, with the one that
    can be seen being the one that was wrong.

    A stamp that cannot be read fails toward absent. A price we cannot place in time
    is not a price from now.
    """
    for event in reversed(events):
        if event.get("event") != "macro":
            continue
        age = _age(event.get("ts"))
        if age is None or age > MACRO_FRESH_S:
            return None
        return {"venue": event.get("venue"), "at": event.get("ts"),
                "odds": event.get("odds") or []}
    return None


def _boundary_passed(market: dict | None, since: datetime) -> bool:
    """A published session boundary has come and gone since we last said anything.

    The socket pushes when a file changes, which is the right trigger for everything
    the agent writes and no trigger at all for the one value derived from the wall
    clock. With nothing running there is nothing to change, so the badge froze:
    measured on 2026-08-28, the route answered "closed" at 16:01 while the browser had
    been showing "open" since 15:26, because 15:26 was the last time anything touched
    the journal. The market had shut half an hour earlier and no bell rang, because no
    snapshot carrying the close ever reached the page.

    Bounded on both sides — after the last push, at or before now — so the crossing is
    worth exactly one push. Testing only "has it passed" would re-push every half
    second for the rest of the day.

    Cheap on purpose. This runs twice a second on every open socket, so it reads two
    strings off the snapshot we already built rather than going near the journal.
    """
    if not market:
        return False
    now = datetime.now(UTC)
    for key in ("next_open", "next_close"):
        when = _when(market.get(key))
        if when is not None and since < when <= now:
            return True
    return False


def _still(record: dict) -> str | None:
    """When the recorded state's own next boundary is still ahead, and so still true.

    The mirror of `_crossed`, and the half it was missing. "The close has passed, so
    the market is closed" and "the close has not passed, so it is open" are one claim
    read in two directions off the same figure Alpaca published — but only the first
    direction was taken. So a panel watching a stopped agent at 15:50 drew OPEN with a
    question mark beside it while the broker's own 16:00 close sat unread in the very
    record being hedged.

    Only the boundary that ends the recorded state counts. An open session's
    `next_open` is tomorrow morning's and says nothing whatever about this afternoon;
    reading it as confirmation would turn the wrong number into an answer.

    The agent's silence is not evidence about the market. It is its own fact, it is
    reported as `stale`, and the console says so in its own words.
    """
    ends = {"open": "next_close", "closed": "next_open"}.get(str(record.get("state")))
    if ends is None:
        return None
    when = _when(record.get(ends))
    return str(record.get(ends)) if when is not None and when > datetime.now(UTC) else None


#: How many headlines the ticker carries. A strip you read one line at a time does
#: not need a day of history behind it, and this rides on a route polled every five
#: seconds.
TICKER_HEADLINES = 24


#: Cells drawn on the heat map at most.
#:
#: A census names sixty to eighty symbols on an ordinary morning, which fits. The
#: bound is for the morning it does not — a payload polled every five seconds is the
#: wrong place to discover that the tape had four hundred names in it. Cut by heat,
#: never by arrival order: dropping the hottest to keep an alphabetical tail would
#: make the map lie about the very thing it draws.
DISCOVERY_CELLS = 160


def _discovery(events: list[dict]) -> dict[str, Any]:
    """The latest census — what the tape was talking about, and what came of each name.

    The *latest*, not the accumulation. A name that was loud at the open would stay on
    the map all day if passes were merged, which is the opposite of what a heat map of
    a live feed is for.

    The tail is the point. Six scanned names on their own are a list; what makes this a
    map is the sixty below them and where the cut fell across the lot. So every cell
    keeps its status — scanned, refused, or never reached — because "the screen threw
    it out" and "the walk stopped before it got here" are different facts, and drawing
    them alike would have the map assert a judgement about names nobody screened.

    Never raises. The route it feeds is polled every five seconds, and a journal is
    append-only text that predates any shape this function expects.
    """
    latest: dict = {}
    for event in events:
        if event.get("event") == "discovery":
            latest = event

    rows = latest.get("tally")
    cells: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            cell = {
                "symbol": symbol,
                "mentions": _int(row.get("mentions")),
                "status": str(row.get("status") or ""),
                # Untrusted publisher text, as everywhere it appears. It leaves here
                # as a string and the panel renders it as text, never as markup.
                "headline": str(row.get("headline") or "")[:180],
            }
            if reason := str(row.get("reason") or ""):
                cell["reason"] = reason
            cells.append(cell)

    cells.sort(key=lambda c: (-c["mentions"], c["symbol"]))
    cells = cells[:DISCOVERY_CELLS]
    return {
        "headlines": _int(latest.get("headlines")),
        "symbols": _int(latest.get("symbols")),
        # The scale the map's ramp is drawn against. Relative, because a four-mention
        # morning and a forty-mention afternoon must both fill it — an absolute scale
        # renders every quiet day as one flat cold grid, which is true and useless.
        # Floored at 1 so an all-zero census cannot divide the ramp by nothing.
        "hottest": max([c["mentions"] for c in cells] or [0]) or 1,
        "cells": cells,
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _headlines(events: list[dict]) -> list[dict]:
    """What the agent is watching, newest first, one entry per article.

    **Two sources.** The catalyst's per-underlying reads, and discovery's market-wide
    census. For a long time it was only the first, which made the strip narrower than
    it looked: a per-symbol feed can only ever carry news about symbols the agent is
    already scanning, so a pinned universe of three tickers scrolled the same handful
    of stories all day. Measured on a real soak — twelve of fourteen items carried
    SPY, because `get_news(SPY)` returns twelve a cycle and `get_news(IWM)` returns
    two. The census was already being fetched every pass to rank the universe and was
    simply not being read here.

    **Provenance travels with the article.** `read` says a catalyst actually had this
    in front of it before deciding; a census sighting sets it false and leaves `roots`
    empty, because `roots` means "which of our underlyings' reads picked this up" and
    the answer for a census article is none of them. Filling that field with the
    publisher's tags would convert a fact about the desk into a fact about the
    publisher, and the strip makes the first claim in its own tooltip.

    The latest read per underlying rather than every read ever taken: the catalyst
    fetches the same 48-hour window each cycle, so a day of scanning journals the same
    article twenty times and a ticker built from all of them would scroll one story
    over and over. The census follows the same rule for the same reason.

    Deduplicated across underlyings too, and this is the more interesting half. A
    macro story is tagged with SPY, QQQ and IWM at once and arrives three times from
    three separate reads — the ticker shows it once, tagged with every root that
    picked it up, which is also the more useful thing to know about it. `also_tagged`
    in the catalyst prompt exists for the same reason: a headline carrying eleven
    tickers is macro noise, and reading it as company news would be reading it wrong.

    **Untrusted publisher text.** It reached us through a fenced section of the
    catalyst's prompt and it leaves here as data. Nothing downstream treats a headline
    as an instruction, and the panel renders it as text rather than as markup.
    """
    latest: dict[str, list[dict]] = {}
    census: list[dict] = []
    for event in events:
        kind = event.get("event")
        if kind == "committee" and isinstance(event.get("feed"), list):
            latest[str(event.get("underlying") or "")] = event["feed"]
        elif kind == "discovery":
            # The latest census only, like the heat map — and reset even when this
            # event carries no feed, so a pass that read nothing clears the last one
            # rather than leaving yesterday's tape on the strip.
            feed = event.get("feed")
            census = feed if isinstance(feed, list) else []

    seen: dict[str, dict] = {}

    def _add(item: Any, root: str) -> None:
        """One article, from either source. `root` is "" for a census sighting."""
        if not isinstance(item, dict):
            return
        text = str(item.get("headline") or "").strip()
        if not text:
            return
        row = seen.setdefault(text, {
            **item, "headline": text, "roots": [],
            # Whether a catalyst actually read this before deciding, as opposed to it
            # merely going past in the census. The strip says the desk read these, and
            # for a census article that is not true — so the claim travels with the
            # article rather than being assumed of the whole list.
            "read": False,
            # Normalised rather than passed through. A record written before the
            # link was kept has no `url` key at all, and the panel's type says
            # `string` — an absent key reaches it as `undefined` and a null as
            # `null`, neither of which that type admits. Both mean the same thing
            # here, so both become the empty string and the type stays true.
            "url": str(item.get("url") or ""),
        })
        if root:
            row["read"] = True
            if root not in row["roots"]:
                row["roots"].append(root)

    # The census first, so a story in both sources is upgraded to "read" by the
    # committee pass rather than the other way round. `_add` only ever sets `read`
    # true, so the order cannot decide the answer — this is belt to that braces.
    for item in census:
        _add(item, "")
    for root, feed in latest.items():
        for item in feed:
            _add(item, root)

    # Roundups off the strip. Benzinga slices one pre-market story by sector and files
    # it four times — "12 Consumer Discretionary Stocks Moving", "12 Health Care
    # Stocks Moving" — twelve tickers each, and four near-identical headlines in a row
    # is a sixth of the strip saying one thing. That is the repetition widening the
    # source was meant to cure, arriving by another door.
    #
    # Deliberately `discovery.MAX_TAGS_PER_HEADLINE` and not a second number: it is
    # the same judgement the tally already makes — past this many tags an article is
    # macro noise rather than company news — and two constants meaning that would
    # drift until the map and the strip disagreed about the same morning.
    #
    # A preference, not a boundary, so it never empties the strip. On a thin
    # pre-market the census can be roundups end to end, and a blank strip there reads
    # as a broken panel rather than a quiet tape. They are real articles: worth less
    # than company news, worth more than nothing.
    rows = list(seen.values())
    def _tags(row: dict) -> int:
        # `len` of a string is a number too, and a bare `len(...)` here would grade a
        # malformed record on its character count. Anything that is not a list has no
        # tags as far as this question goes.
        tags = row.get("symbols")
        return len(tags) if isinstance(tags, list) else 0

    news = [r for r in rows if _tags(r) <= MAX_TAGS_PER_HEADLINE]
    # By recency, and unreadable timestamps last rather than first — an article whose
    # `ts` we could not parse is not breaking news, and `age_hours` is already None
    # for it everywhere else.
    ordered = sorted(
        news or rows,
        key=lambda r: (r.get("age_hours") is None, r.get("age_hours") or 0.0),
    )
    for row in ordered:
        row["roots"] = sorted(row["roots"])
    return ordered[:TICKER_HEADLINES]


def _after_hours(ts: Any, session: Any) -> bool | None:
    """Whether a timestamp falls at or after the session's close. `None` if unknowable.

    A gate reading is a measurement of a moment, and a moment after the close is a
    different fact from the same words during the session. `portfolio-greek-bounds`
    refusing a proposal for "no greeks" at 16:44 is the gate working — nobody is
    quoting, so the exposure the desk already carries cannot be bounded, and opening
    more on an unmeasurable book is exactly what fail-closed exists to stop. The same
    sentence at 11:00 would be a data outage worth chasing.

    `None` rather than `False` when there is no usable boundary. "We cannot tell" and
    "the market was open" are different claims, and the louder of the two must not be
    what a missing field defaults to.

    The close comes from the session record, which took it from Alpaca's clock. No
    calendar is kept here — see `_crossed` for why that matters.
    """
    if not isinstance(session, dict):
        return None
    close = _when(session.get("next_close"))
    taken = _when(ts)
    if close is None or taken is None:
        return None
    return taken >= close


def _gate_readings(events: list[dict]) -> dict[str, dict]:
    """What each gate measured the last time it ran, and when.

    The gates tab listed sixteen names and a rejection count, which answers "does this
    gate exist" and "has it ever bitten" — neither of which is a question anyone has
    while watching a book. The question is *how close are we*, and the answer was
    already in the journal and being thrown away: every gate writes its own reading
    with its verdict.

        open-position-count    2/20 open positions
        entry-rate-throttle    1/6 entries this hour
        daily-loss-halt        within the 5% floor of $89,817

    Those are instrument readings. Nothing here computes them — recomputing a gate's
    own arithmetic in the panel is how a dashboard comes to disagree with the thing it
    depicts, and these are the exact strings the gate produced when it ran.

    Most recent evaluation only. A gate's reading is a measurement of a moment, and a
    history of them is what the run journal is for.
    """
    for event in reversed(events):
        if event.get("event") != "gate_decision":
            continue
        gates = event.get("gates")
        if not isinstance(gates, list):
            # A string iterates one character at a time and every character raises on
            # `.get`. This route is polled every five seconds, and a raise here empties
            # the whole panel — found by test, not by staring at it.
            return {}
        # The session in force, for the one thing a reading cannot say about itself.
        session = next((e for e in reversed(events)
                        if e.get("event") == "session"), None)
        shut = _after_hours(event.get("ts"), session)
        return {
            str(gate["gate"]): {
                "reason": gate.get("reason") or "",
                "passed": bool(gate.get("passed")),
                "at": event.get("ts"),
                "structure": event.get("structure") or "",
                # Whether the market was shut when this was measured. See
                # `_after_hours`: the same words mean different things either side of
                # the close, and the tab should not make the reader work that out.
                "after_hours": shut,
            }
            for gate in gates
            if isinstance(gate, dict) and gate.get("gate")
        }
    return {}


def _armed(events: list[dict]) -> bool | None:
    """Whether the last cycle would have submitted, or was only rehearsing.

    `True` armed, `False` dry run, `None` nothing has scanned yet or the journal
    predates the flag. Three values, because "we do not know" and "it is live" must
    never render the same.

    This is the loudest thing a trading console can get wrong in either direction. A
    dry run that looks live invites someone to panic about an order that was never
    sent; a live run that looks like a rehearsal is worse, and is why the unknown case
    is its own value rather than being folded into the safe-looking one.
    """
    for event in reversed(events):
        if event.get("event") == "cycle_start" and "dry_run" in event:
            return not bool(event["dry_run"])
    return None


def _last_session(events: list[dict]) -> dict | None:
    """What the market is doing, and how confident the panel is entitled to be.

    A session record is a report of a *crossing*, not a live reading. So when the
    agent exits mid-session nothing writes the close, and the badge went on asserting
    OPEN into the evening — the soak stopped at 15:40 and the panel still said the
    market was open at 16:10.

    The first fix for that hedged: it showed the last-seen state with a question mark.
    That was the wrong answer to a question that has a right one. The record already
    carries `next_close` from Alpaca's own clock, that time has passed, and "the
    market is closed" is a statement the panel is fully entitled to make.

    So `state` is derived from the last boundary that has actually passed, falling
    back to the recorded state when none has. `source` says which, because the three
    are genuinely different claims and the panel says different things for each:

      observed   — the agent is running and wrote this crossing down.
      boundary   — nobody wrote it down, but the broker had already published when it
                   would happen and that time has passed.
      last-seen  — no boundary to reason from and nothing writing. The one case where
                   the panel does not know, and has to say so.

    `observed` (the bool) is a different and older distinction, kept unchanged: a bell
    that rang versus the state the scheduler merely found on startup. It gates a
    sound; `source` gates a label.

    `stale` is measured against the whole journal rather than against the session
    record, because the record is *meant* to be old: a market open at 09:30 is a
    nine-hour-old record at 18:30 and a perfectly current one at 14:00. What makes it
    stale is silence everywhere else.
    """
    latest = _age(events[-1].get("ts")) if events else None
    for event in reversed(events):
        if event.get("event") != "session":
            continue
        recorded = event.get("state")
        stale = latest is None or latest > SESSION_STALE_S
        crossed = _crossed(event)
        # Four claims, strongest first. A boundary that passed is a *change* and
        # outranks everything. An agent that is writing right now outranks a published
        # figure, because "it is running and wrote this down" says more than "the
        # broker said this would last until four". Only when neither holds does the
        # unreached boundary settle it, and only when that is missing too is the panel
        # actually in the dark.
        ahead = _still(event)
        if crossed is not None:
            state, source, at, until = crossed[0], "boundary", crossed[1], None
        elif not stale:
            state, source, at, until = recorded, "observed", None, None
        elif ahead is not None:
            state, source, at, until = recorded, "published", None, ahead
        else:
            state, source, at, until = recorded, "last-seen", None, None
        return {
            "state": state,
            # What the journal actually said, kept beside what we concluded. A
            # derivation that hides its input cannot be checked against it.
            "recorded": recorded,
            "source": source,
            "crossed_at": at,
            # The boundary that has not arrived yet, when that is what settles it.
            "until": until,
            "at": event.get("ts"),
            "session_date": event.get("session_date"),
            "next_open": event.get("next_open"),
            "next_close": event.get("next_close"),
            "observed": bool(event.get("observed")),
            "stale": stale,
            "quiet_for_s": None if latest is None else round(latest),
        }
    return None


def snapshot(*, journal_path: str, ledger_path: str, breaker_path: str) -> dict:
    """Everything the panel needs, in one read.

    One endpoint rather than several because the panel polls, and four requests that
    can disagree with each other about which cycle they describe is worse than one
    that is occasionally a few seconds old.
    """
    journal = Journal.open(journal_path)
    ledger = Ledger.load(ledger_path)
    breaker = CircuitState.load(breaker_path)
    events = list(journal.read())
    latest_patterns = _patterns_by_underlying(events)
    latest_marks = _marks_by_structure(events)
    mark_series = _mark_series(events)

    # The agent's own last marks, so the headline unrealized figure and the number
    # beside each position come from one source. Without them `build` had no marks
    # at all and reported unrealized as zero while a position it was showing read
    # -$12.50 — two numbers contradicting each other on the same screen, which is
    # worse than either being absent.
    #
    # This process still never asks the broker. The agent prices the whole book
    # every cycle and writes the result down; the snapshot is polled every five
    # seconds and reads it.
    report = pnl.build(ledger, journal, marks={
        sid: mark for sid, read in latest_marks.items()
        if (mark := _dec(read.get("mark"))) is not None
    })
    decisions = _decisions_with_positions(events)[-RECENT_DECISIONS:]
    views = {e["underlying"]: e for e in events if e.get("event") == "market_view"}
    latest_menu: dict[str, dict] = {}
    for e in events:
        if e.get("event") == "candidates":
            latest_menu[e["underlying"]] = e

    # The gate chain as configured, so the panel's family meter is drawn from what is
    # actually loaded rather than from a hard-coded 2/2/4/3/4. Adding a gate changes
    # the UI on the next request, with no second place to update.
    chain = [{"gate": g.gate_name, "family": family_of(g)} for g in ALL_GATES]
    limits = Limits.from_env()

    return _plain({
        "chain": chain,
        "families": list(FAMILIES),
        "limits": {
            "MAX_LOSS_PER_POSITION_USD": limits.max_loss_per_position_usd,
            "MAX_PORTFOLIO_RISK_PCT": limits.max_portfolio_risk_pct,
            "MAX_CORRELATED_POSITIONS": limits.max_correlated_positions,
            "MAX_UNCLASSIFIED_POSITIONS": limits.max_unclassified_positions,
            "MIN_DTE": limits.min_dte,
            "MIN_OPEN_INTEREST": limits.min_open_interest,
            "MAX_NET_DELTA": limits.max_net_delta,
            "DAILY_LOSS_LIMIT_PCT": limits.daily_loss_limit_pct,
            "MAX_ENTRIES_PER_HOUR": limits.max_entries_per_hour,
        },
        # The last bell, so the panel can ring one and can say which side of it we
        # are on. `None` until a scheduled run has written one — a `--once` run never
        # observes the closed half, and the panel should say nothing rather than
        # guess from a local clock that knows no holidays.
        "market": _last_session(events),
        # What it is doing, as opposed to what it decided. See `_activity`.
        "activity": _activity(events),
        "pass": _pass(events),
        # What a venue was charging for the macro questions the headlines argue about,
        # from the last pass that could read it. Absent rather than empty when none has
        # — "could not ask" and "nothing deep enough" are different, and the panel says
        # which.
        "macro": _macro(events),
        # When the next scan is due, so the console can count down to it rather
        # than leaving a reader to work out whether a quiet panel is waiting or
        # stopped. The cadence is the scheduler's own, from one reader.
        "cadence": {
            "interval_s": scan_interval_seconds(),
            # How quiet a healthy agent goes between passes. The console had this as
            # a fixed fifteen minutes against a cadence of thirty, so it announced a
            # stopped process for about half of every cycle.
            "silent_after_s": silent_after_seconds(),
            "pass_window_s": pass_window_seconds(),
        },
        # What each gate measured last time it ran. The counts say which gates have
        # ever bitten; these say how close the book is to each one now.
        "gate_readings": _gate_readings(events),
        # What the thinking has cost. Tokens always, money where a price is known.
        "spend": _spend(events),
        # Realized and mark-to-market over the windows a trader asks for. The two are
        # different numbers and the payload keeps them apart — see `pnl.by_period`.
        "periods": pnl.by_period(ledger, pnl.equity_series(journal),
                                 today=clock.today()),
        # What the catalyst has been reading. Untrusted publisher text: the panel
        # renders it as text, never as markup.
        "headlines": _headlines(events),
        # The universe the agent chose for itself, and everything it passed over
        # choosing it. See `_discovery`.
        "discovery": _discovery(events),
        # What it is in the middle of, so a slow stage reads as work rather than
        # as an empty screen. None when nothing has been written recently.
        "in_flight": _in_flight(events),
        # Whether the last cycle was armed. True live, False a rehearsal, None
        # nothing has scanned — and the three must not render the same.
        "armed": _armed(events),
        # The deliberation behind each proposal. See `_committees`.
        "committees": _committees(events),
        "circuit": {
            "halted": breaker.halted,
            "halt_reason": breaker.halt_reason,
            "baseline_equity": breaker.baseline_equity,
            "baseline_day": breaker.baseline_day,
            "entries_this_hour": len(breaker.entry_times),
            "describe": breaker.describe(),
        },
        "pnl": {
            "realized": report.realized_usd,
            "unrealized": report.unrealized_usd,
            "total": report.total_usd,
            "wins": report.wins,
            "losses": report.losses,
            "open": report.open_count,
            "closed": report.closed_count,
            "proposals": report.proposals,
            "passed": report.passed,
            "approved": report.approved,
            "rejected": report.rejected,
            "orders_submitted": report.orders_submitted,
            "rejections_by_gate": report.rejections_by_gate,
            "equity_start": report.equity_start,
            "equity_last": report.equity_last,
            "max_drawdown_usd": report.max_drawdown_usd,
            # Two places, because a raw ratio has twenty-eight significant figures
            # and a percentage on a screen has two. The Decimal is kept exact
            # everywhere it is computed; it is rounded once, here, at the edge.
            "max_drawdown_pct": _round(report.max_drawdown_pct, 2),
            "equity_samples": report.equity_samples,
        },
        # The curve itself, not just its length: the chart plots equity against the
        # time it was read at, so an overnight gap draws as a gap rather than as one
        # continuous session. Trimmed for the same reason the decision list is.
        "equity_curve": [
            {"t": ts, "v": value}
            for ts, value in pnl.equity_series(journal)[-EQUITY_POINTS:]
        ],
        "positions": [
            {
                "structure_id": s.structure_id, "name": s.name,
                "underlying": s.underlying, "qty": s.qty,
                "opened_at": s.opened_at, "rationale": s.rationale,
                "legs": s.legs, "entry_price": s.entry_price,
                # Which way this structure wants the underlying to go, and what the
                # chart is doing about it. Read from the latest market view rather
                # than computed here: the agent has the bars, this process must not
                # touch the broker on a route polled every five seconds.
                **_pattern_read(s, latest_patterns),
                # The agent's own most recent judgement of this position: what it is
                # worth, how long it has, and what the policy said to do about it.
                # Stamped `as_of`, because it is a cycle old rather than live.
                "read": latest_marks.get(s.structure_id),
                # And every earlier one, so the card can show a shape rather than a
                # single number. Drifting sideways and falling off a cliff reach the
                # same figure and are not the same situation.
                "marks": mark_series.get(s.structure_id, []),
            }
            for s in ledger.open_structures
        ],
        # Closed structures too. The chart of a position that already ran its course
        # — opened here, target there, closed at that point — is the one worth looking
        # at, and a view limited to open positions can never show it.
        "closed": [
            {
                "structure_id": s.structure_id, "name": s.name,
                "underlying": s.underlying, "qty": s.qty,
                "opened_at": s.opened_at, "closed_at": s.closed_at,
                "entry_price": s.entry_price, "exit_price": s.exit_price,
                "realized_usd": s.realized(), "rationale": s.rationale,
            }
            for s in sorted((x for x in ledger.structures if not x.is_open),
                            key=lambda x: x.closed_at or "", reverse=True)[:RECENT_CLOSED]
        ],
        "decisions": decisions,
        "views": list(views.values()),
        "menus": list(latest_menu.values()),
    })


@dataclass
class Paths:
    """Where the three files live. One object so the routes and the push loop agree."""

    journal: str = str(paths.RUN_JOURNAL)
    ledger: str = str(paths.LEDGER)
    breaker: str = str(paths.CIRCUIT)

    def stamp(self) -> tuple[float, ...]:
        """A cheap fingerprint of all three, for the watcher.

        Size as well as mtime: the journal is appended to, and an append inside the
        same mtime tick would otherwise be invisible until the next one.
        """
        out: list[float] = []
        for name in (self.journal, self.ledger, self.breaker):
            try:
                st = Path(name).stat()
                out += [st.st_mtime, float(st.st_size)]
            except OSError:
                out += [0.0, 0.0]
        return tuple(out)


PATHS = Paths()

app = FastAPI(title="HAL Street panel", docs_url=None, redoc_url=None)


def state() -> dict:
    return snapshot(journal_path=PATHS.journal, ledger_path=PATHS.ledger,
                    breaker_path=PATHS.breaker)


@app.get("/api/state")
async def api_state() -> JSONResponse:
    """The whole snapshot in one read. The socket pushes this same payload."""
    try:
        return JSONResponse(state())
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)


@app.get("/api/structure/{structure_id}/chart")
async def api_structure_chart(structure_id: str, timeframe: str | None = None) -> JSONResponse:
    """One structure's price history and the levels its exit policy acts on.

    The only route that reaches the broker, and it reaches it for market data alone.
    Two things keep that narrow. The symbols come from *our* ledger, resolved from a
    structure_id — the panel cannot name a contract, so this is not a general
    market-data proxy wearing a dashboard. And the client is used for one call, to one
    read-only tool; there is no order path here and no account figure is read.

    Slow by the standards of the rest of this API: it launches an MCP subprocess and
    waits on Alpaca. That is why it is its own route rather than part of the snapshot
    the panel polls — a chart nobody opened should not be on the critical path of
    every five-second update.
    """
    ledger = Ledger.load(PATHS.ledger)
    structure = structure_chart.find(ledger, structure_id)
    if structure is None:
        return JSONResponse({"error": f"no structure {structure_id!r} in the ledger"},
                            status_code=404)
    try:
        from halstreet.execution.mcp_client import AlpacaMCP

        client = AlpacaMCP.from_env()
        window = structure_chart.window_days(structure)
        bar, bucket = structure_chart.chosen(timeframe, window)
        bars = await client.get_option_bars(
            sorted(structure.legs),
            timeframe=bar,
            start=structure_chart.start_of_window(structure),
        )
    except Exception as exc:
        # Still return the structure and its levels: the lines are computed from the
        # ledger and the policy, so they are drawable with no price history at all.
        payload = structure_chart.build(structure, {}, ExitPolicy.from_env())
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(_plain(payload))
    payload = structure_chart.build(structure, bars, ExitPolicy.from_env(), bucket)
    # What was actually used, and what else could be asked for — so the panel offers
    # the real set rather than a copy of it that has to be kept in step.
    payload["timeframe"] = bar
    payload["timeframes"] = list(structure_chart.OFFERED)
    return JSONResponse(_plain(payload))


@app.get("/api/marks")
async def api_marks() -> JSONResponse:
    """Live marks for every open structure. The only other route that reaches Alpaca.

    Its own route, and not part of the snapshot, for the same reason the structure
    chart is: the snapshot is polled every five seconds and launches nothing, while
    this spawns an MCP subprocess and waits on the broker. Folding it in would put a
    round trip on the critical path of every update whether anyone was looking at a
    position or not.

    The panel calls it on a much slower cadence and falls back to the agent's own
    last mark when it fails, which is what the journal already carries.

    Narrow in the same three ways as the chart route. The symbols come from *our*
    ledger rather than from the caller, so this is not a market-data proxy wearing a
    dashboard. It reads one read-only tool. And it prices with `mark_structure` —
    the very function `evaluate_exit` uses — so the number on the screen cannot
    disagree with the number the exit policy is acting on.
    """
    ledger = Ledger.load(PATHS.ledger)
    structures = ledger.open_structures
    if not structures:
        return JSONResponse({"marks": {}, "as_of": _now()})

    symbols = sorted({sym for st in structures for sym in st.legs})
    try:
        from halstreet.execution.mcp_client import AlpacaMCP

        client = AlpacaMCP.from_env()
        payload = await client.get_option_snapshot(symbols)
    except Exception as exc:
        # The panel keeps showing the agent's last mark, labelled with its age. A
        # stale number that says so beats an empty space that looks like a bug.
        return JSONResponse({"marks": {}, "as_of": _now(),
                             "error": f"{type(exc).__name__}: {exc}"})

    chain = payload.get("snapshots", payload) if isinstance(payload, dict) else {}
    out: dict[str, Any] = {}
    for structure in structures:
        mark = mark_structure(structure, chain)
        # The legs go out either way. A structure the net refuses to price is exactly
        # the one where a person wants to see which leg has no quote, and the old
        # `{"missing": [...]}` said how many without saying which prices did arrive.
        legs = _legs_view(structure, chain)
        if not mark.complete:
            # Reported, not guessed. A mark from three of four legs is not a mark,
            # and this is the same refusal `evaluate_exit` makes.
            out[structure.structure_id] = {"missing": mark.missing[:4], "legs": legs}
            continue
        unrealized = None
        if structure.entry_price is not None:
            unrealized = ((mark.value - structure.entry_price)
                          * CONTRACT_MULTIPLIER * structure.qty)
        out[structure.structure_id] = {"mark": mark.value,
                                       "unrealized_usd": unrealized, "legs": legs}
    return JSONResponse(_plain({"marks": out, "as_of": _now()}))


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    """Push the snapshot when it changes. Never read.

    The loop below contains no receive of any kind, which is the whole safety
    argument: an incoming frame has nowhere to go. That costs the usual disconnect
    detection, so the heartbeat is load-bearing — a send to a departed client raises,
    and that is what ends the loop.
    """
    await socket.accept()
    last: tuple[float, ...] | None = None
    # The snapshot we last sent, and when. Both only so the loop can notice the one
    # thing no file will tell it about — see `_boundary_passed`.
    sent: dict | None = None
    since = datetime.now(UTC)
    idle = 0.0
    try:
        while True:
            now = PATHS.stamp()
            if now != last or _boundary_passed((sent or {}).get("market"), since):
                last = now
                idle = 0.0
                sent = state()
                since = datetime.now(UTC)
                await socket.send_json(sent)
            elif idle >= HEARTBEAT_S:
                # Not the snapshot: a tick that proves the connection is alive without
                # making the client re-render everything it already has.
                idle = 0.0
                await socket.send_json({"heartbeat": True})
            await asyncio.sleep(WATCH_S)
            idle += WATCH_S
    except Exception:  # noqa: S110 - any send failure means the client is gone
        pass
    finally:
        with contextlib.suppress(Exception):
            await socket.close()


# response_model=None: the return is a Response either way, and FastAPI would
# otherwise try to build a Pydantic model out of the union and fail at import.
@app.get("/", response_model=None)
async def index() -> FileResponse | JSONResponse:
    page = DIST / "index.html"
    if not page.exists():
        return JSONResponse(
            {"error": "panel not built", "fix": "cd apps/desktop && npm install && npm run build"},
            status_code=503)
    # Never cached. Vite emits a content-hashed bundle and names it from this file,
    # so the hash is only ever seen by a browser that fetched this file again — and
    # FileResponse sends `etag` and `last-modified` with no `Cache-Control`, which
    # browsers treat as heuristically fresh and reuse without asking. The panel then
    # goes on running whatever build was current the first time it was opened, and
    # every subsequent fix appears not to have happened.
    #
    # The assets themselves are the opposite case and are handled below: their names
    # change whenever their contents do, so they can be cached forever.
    return FileResponse(page, headers={"Cache-Control": "no-store, must-revalidate"})


class _ImmutableAssets(StaticFiles):
    """Static files whose names already encode their contents."""

    def file_response(self, *args: Any, **kwargs: Any) -> Any:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_assets() -> None:
    """Serve the bundle's hashed assets, if there is a build to serve.

    Mounted at import time when present so `serve()` stays a one-liner, and skipped
    silently when it is not: the API and the socket are useful on their own, and a
    missing build should say so on `/` rather than crash the process on startup.
    """
    assets = DIST / "assets"
    if assets.is_dir():
        # Content-hashed filenames, so a changed file is a different URL and an
        # unchanged one can be kept indefinitely. This is the half of the pair that
        # makes `no-store` on index.html cheap rather than a reload of the whole
        # bundle every time the page is opened.
        app.mount("/assets", _ImmutableAssets(directory=assets), name="assets")


_mount_assets()


def serve(host: str = "127.0.0.1", port: int = 8787, *, journal: str = str(paths.RUN_JOURNAL),
          ledger: str = str(paths.LEDGER), breaker: str = str(paths.CIRCUIT)) -> None:
    import uvicorn  # only the panel needs it, and only when it runs

    PATHS.journal, PATHS.ledger, PATHS.breaker = journal, ledger, breaker
    _mount_assets()
    # Localhost only, and not configurable to anything else from the CLI. This serves
    # live position data for a real account; binding it to 0.0.0.0 on conference wifi
    # is a mistake that should not be one flag away.
    print(f"HAL Street panel on http://{host}:{port}  (read-only, Ctrl-C to stop)")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    except KeyboardInterrupt:
        print("\npanel stopped")
