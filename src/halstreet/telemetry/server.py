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
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from halstreet import paths
from halstreet.agent.breaker import CircuitState
from halstreet.agent.ledger import Ledger
from halstreet.agent.manager import (
    CONTRACT_MULTIPLIER,
    ExitPolicy,
    mark_legs,
    mark_structure,
)
from halstreet.gates import ALL_GATES
from halstreet.gates.base import FAMILIES, Limits, family_of
from halstreet.strategy.exposure import agrees, exposure_of
from halstreet.telemetry import pnl, structure_chart
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
            "reflection": event.get("reflection") or [],
            "tokens": event.get("tokens") or {},
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
    stage = _STAGE.get(str(event.get("event")))
    if stage is None:
        # The last thing written finished something. Walking further back to find a
        # stage would report one forever: every completed cycle has four of them
        # sitting just behind its outcome.
        return None
    started = _age(event.get("ts"))
    if started is None or started > IN_FLIGHT_S:
        return None
    return {"stage": stage, "event": event.get("event"),
            "underlying": event.get("underlying") or "", "since": event.get("ts")}


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
                    "structure_id": opened.get("structure_id") if opened else None})
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


def _last_session(events: list[dict]) -> dict | None:
    """The most recent session transition the scheduler wrote down.

    `observed` distinguishes a bell that rang from the state the scheduler found on
    startup — the difference between a sound and a label, for anything downstream
    that makes noise about it.
    """
    for event in reversed(events):
        if event.get("event") == "session":
            return {
                "state": event.get("state"),
                "at": event.get("ts"),
                "session_date": event.get("session_date"),
                "next_open": event.get("next_open"),
                "next_close": event.get("next_close"),
                "observed": bool(event.get("observed")),
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
        # What it is in the middle of, so a slow stage reads as work rather than
        # as an empty screen. None when nothing has been written recently.
        "in_flight": _in_flight(events),
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
    idle = 0.0
    try:
        while True:
            now = PATHS.stamp()
            if now != last:
                last = now
                idle = 0.0
                await socket.send_json(state())
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
