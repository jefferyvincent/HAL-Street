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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from halstreet import paths
from halstreet.agent.breaker import CircuitState
from halstreet.agent.ledger import Ledger
from halstreet.agent.manager import ExitPolicy
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
    decisions = [e for e in events if e.get("event") == "gate_decision"][-RECENT_DECISIONS:]
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
async def api_structure_chart(structure_id: str) -> JSONResponse:
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
        bars = await client.get_option_bars(
            sorted(structure.legs),
            timeframe=structure_chart.TIMEFRAME,
            start=structure_chart.start_of_window(structure),
        )
    except Exception as exc:
        # Still return the structure and its levels: the lines are computed from the
        # ledger and the policy, so they are drawable with no price history at all.
        payload = structure_chart.build(structure, {}, ExitPolicy.from_env())
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(_plain(payload))
    return JSONResponse(_plain(structure_chart.build(structure, bars, ExitPolicy.from_env())))


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
    return FileResponse(page)


def _mount_assets() -> None:
    """Serve the bundle's hashed assets, if there is a build to serve.

    Mounted at import time when present so `serve()` stays a one-liner, and skipped
    silently when it is not: the API and the socket are useful on their own, and a
    missing build should say so on `/` rather than crash the process on startup.
    """
    assets = DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")


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
