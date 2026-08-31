"""Running on a cadence, and knowing when not to.

The competition scores an autonomous agent over a live window, so the loop has to run
itself. `SCAN_INTERVAL_MINUTES` sat in `.env` unread until this module existed, which
made the README's claim that the agent "runs unattended on a schedule" untrue.

The interesting part is not the sleeping, it is the not-running:

**Market hours come from the broker, not the clock.** `get_clock` knows about holidays,
half days, and early closes; a local `datetime` does not. An agent that scans at 03:00
burns tokens on stale quotes and may act on them.

**A cycle that overruns its interval must not stack.** Scans are spaced from the end of
the previous one, so a slow cycle delays the next rather than starting a second one
alongside it — two concurrent scans would double-submit against the same account.

**Stopping is deliberate, and then it is not.** `--until-close` ends at the bell rather
than running to a count, which is what a judged window actually wants. Ctrl-C is three
states rather than one: the first finishes the current cycle, because a scan
interrupted between the gate chain and the broker is how a structure ends up half
placed; the second cancels that cycle; the third leaves the process outright. Each
says which it is doing, because a wait nobody announced is indistinguishable from a
signal nobody received.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from halstreet import clock as session_clock
from halstreet.execution.mcp_client import AlpacaMCP, MCPError

TOOL_CLOCK = "get_clock"


@dataclass(frozen=True)
class MarketClock:
    """The broker's own view of the session."""

    is_open: bool
    next_open: datetime | None
    next_close: datetime | None
    timestamp: datetime | None

    @classmethod
    def parse(cls, payload: dict) -> MarketClock:
        def when(key: str) -> datetime | None:
            raw = payload.get(key)
            if not raw:
                return None
            try:
                return datetime.fromisoformat(str(raw))
            except ValueError:
                return None

        return cls(
            is_open=bool(payload.get("is_open")),
            next_open=when("next_open"),
            next_close=when("next_close"),
            timestamp=when("timestamp"),
        )

    @property
    def session_date(self) -> date | None:
        """The exchange's calendar date, straight from the broker.

        Alpaca reports its timestamp in exchange-local time with the offset attached,
        so this needs no timezone database and no knowledge of where the exchange is.
        """
        return self.timestamp.date() if self.timestamp else None

    def seconds_until_open(self) -> float | None:
        if self.is_open or self.next_open is None:
            return None
        now = self.timestamp or datetime.now(UTC)
        return max(0.0, (self.next_open - now).total_seconds())

    def seconds_until_close(self) -> float | None:
        if not self.is_open or self.next_close is None:
            return None
        now = self.timestamp or datetime.now(UTC)
        return max(0.0, (self.next_close - now).total_seconds())


async def market_clock(client: AlpacaMCP) -> MarketClock:
    return MarketClock.parse(await client.call(TOOL_CLOCK))


#: How often the abandon-watcher checks. Short enough that a second Ctrl-C feels
#: immediate, long enough to be free while a 73-second cycle runs.
_STOP_POLL_SECONDS = 0.05

#: The cadence when nothing says otherwise. Half an hour, matching `.env.example`.
DEFAULT_INTERVAL_MINUTES = 30


def scan_interval_seconds(source: dict[str, str] | None = None) -> int:
    """How often a scan is meant to run, from the environment.

    One reader, because two would be two defaults. `run.py` had the only copy and the
    panel wanted the same number to say when the next scan is due; a second
    `int(os.environ.get(...) or 30)` somewhere else is a claim about the cadence that
    can drift from the one the scheduler actually uses.

    An unreadable or non-positive value falls back rather than raising. The panel asks
    this on every request and a misconfigured .env should not empty a dashboard.
    """
    raw = (source if source is not None else os.environ).get("SCAN_INTERVAL_MINUTES")
    try:
        minutes = int(str(raw))
    except (TypeError, ValueError):
        minutes = DEFAULT_INTERVAL_MINUTES
    return max(1, minutes) * 60


#: How long one pass may take, at most, for the purpose of judging silence.
#:
#: Six discovered names is four model calls each and a judge with a long tail; the
#: longest measured pass was a little over two minutes. Five is generous on purpose —
#: this is the slack in an alarm, and an alarm that cries wolf is worse than one that
#: is late.
PASS_ALLOWANCE_S = 5 * 60

#: How often the between-scan job runs while the scheduler waits.
#:
#: One minute, because it exists to chase a fill and a limit the book has
#: moved away from is worth less every minute it rests. Short enough to be
#: prompt; long enough that a whole interval of them is a handful of quote
#: requests, not a poll.
BETWEEN_SECONDS = 60.0


def silent_after_seconds(source: dict[str, str] | None = None) -> int:
    """How quiet the journal may go, mid-session, before something is wrong.

    Derived from the cadence rather than fixed, because the cadence is configurable
    and this is a claim about it. Between passes the scheduler writes nothing at all —
    it logs to stdout and sleeps — so a thirty-minute cadence is about twenty-eight
    minutes of silence from an agent working perfectly. The console called that a
    stopped process at fifteen minutes: a false alarm for roughly half of every cycle,
    on the one banner whose entire job is to be believed.

    One interval plus a pass, so a slow afternoon does not read as a dead agent.
    """
    return scan_interval_seconds(source) + PASS_ALLOWANCE_S


def pass_window_seconds(source: dict[str, str] | None = None) -> int:
    """How far apart two records can be and still belong to the same scan.

    A pass is minutes; passes are one cadence apart. Half the cadence sits between
    those with room on both sides — and it has to *be* half the cadence rather than a
    fixed ten minutes, which is right at thirty and would merge two consecutive passes
    into one at five.

    Capped at twice the pass allowance, because beyond a pass's own length a wider
    window only risks catching the pass before it.

    Not floored. A floor at the pass allowance is self-defeating at short cadences —
    it would make the window as wide as the gap it is supposed to measure. Set a
    cadence shorter than a pass takes and a slow pass may split across two tables;
    that is a real consequence of scans overlapping, which the scheduler already
    refuses to do and says so when a cycle overruns its interval.
    """
    return min(scan_interval_seconds(source) // 2, PASS_ALLOWANCE_S * 2)


#: 128 + SIGINT, the shell's own convention for a process a signal ended.
INTERRUPTED = 130


def hard_exit(code: int = INTERRUPTED) -> None:
    """Leave now, without waiting for threads nobody can cancel.

    `os._exit`, deliberately. The committee's four model calls run on
    `asyncio.to_thread`, and a thread cannot be cancelled — so cancelling the cycle
    frees the coroutine awaiting the call while the call itself carries on. Returning
    normally then hands control to `asyncio.run`, whose last act is to join the
    default executor. Measured on a probe: a cancelled cycle sat a further twenty
    seconds, printing nothing and answering nothing, before the process ended. That is
    not a slow shutdown, it is a terminal that looks wedged, and further Ctrl-C did
    nothing because the handler by then had nothing left to set.

    Nothing durable is lost by leaving this way, and that is a property of the design
    rather than a hope. The journal flushes each record as it is appended, so there is
    no buffer to lose. The lock is an `flock`, which the kernel drops when the holder
    dies however it dies — there is no stale file to clean up. And every cycle
    reconciles the ledger against the broker's own positions before it proposes
    anything, so an order that landed without being written down surfaces as a
    divergence on the next run rather than vanishing.

    What is lost is anything sitting in stdio, which is why that goes first.
    """
    with contextlib.suppress(Exception):
        sys.stdout.flush()
    with contextlib.suppress(Exception):
        sys.stderr.flush()
    os._exit(code)


class Scheduler:
    """Repeats a coroutine on a cadence, only while the market is open."""

    def __init__(self, client: AlpacaMCP, interval_minutes: int, *,
                 log: Callable[[str], None] = print,
                 journal: Any = None,
                 max_sleep_seconds: float = 900.0,
                 abort: Callable[[], None] = hard_exit) -> None:
        self.client = client
        self.interval = max(1, interval_minutes) * 60
        self.log = log
        # Optional, so the scheduler still runs headless in tests. When it is here,
        # the open/closed transition is written down — the loop only ever runs while
        # the market is open, so this is the one place that observes the *closed*
        # half at all, and nothing downstream could otherwise tell a session that
        # ended from an agent that stopped.
        self.journal = journal
        self._was_open: bool | None = None
        # Never sleep longer than this in one go, so a stop signal is acted on promptly
        # even when the next open is fifteen hours away.
        self.max_sleep = max_sleep_seconds
        self._stop = asyncio.Event()
        # Set by a second stop request. The first is a request to finish; this one
        # is a request to stop waiting for that.
        self._stop_now = False
        # The third. Injectable only so a test can watch it being reached — every
        # caller in this repository takes the default, and the default does not
        # return.
        self._abort = abort
        self._aborted = False

    def _note_session(self, clock: MarketClock) -> None:
        """Journal the bell, once, when the broker's answer changes.

        On the transition only. Written every poll it would be noise in an
        append-only file — the scheduler asks the clock every interval all night —
        and a reader could not tell the moment the session opened from the many
        times it was observed already open.

        The first observation counts as a transition, because a reader joining
        mid-file has no prior state either.
        """
        if self.journal is None or clock.is_open == self._was_open:
            return
        first, self._was_open = self._was_open is None, clock.is_open
        self.journal.write(
            "session",
            state="open" if clock.is_open else "closed",
            session_date=clock.session_date.isoformat() if clock.session_date else None,
            next_open=str(clock.next_open) if clock.next_open else None,
            next_close=str(clock.next_close) if clock.next_close else None,
            # So a consumer can tell "the bell just rang" from "this is where we came
            # in" — the difference between ringing it and drawing it greyed out.
            observed=first,
        )

    @property
    def stopping(self) -> bool:
        """A stop has been asked for; the current cycle is being allowed to finish."""
        return self._stop.is_set()

    @property
    def should_exit_now(self) -> bool:
        """Asked twice. Do not start anything further and do not wait."""
        return self._stop_now

    def request_stop(self, reason: str = "signal") -> None:
        """First call is graceful. Second means now.

        Graceful first, because a cycle interrupted between the gate chain and the
        broker is how a structure ends up half-placed, and nothing downstream can tell
        that from a structure that was never placed.

        But a cycle over a discovered universe is six committees — 73 seconds on a
        live run — and for all of those seconds a polite stop is indistinguishable
        from a signal nobody received. So the wait is *said*, with the way to insist,
        and insisting works.
        """
        if not self._stop.is_set():
            self.log(f"stop requested ({reason}); finishing the current cycle "
                     "— Ctrl-C again to stop now")
            self._stop.set()
        elif not self._stop_now:
            self.log("stopping now; not waiting for the cycle to finish")
            self._stop_now = True
        elif not self._aborted:
            # The second press cancels the cycle, which frees the coroutines and not
            # the worker threads underneath them — see `hard_exit`. Somebody pressing
            # a third time is telling us the difference is not visible from where they
            # are sitting, and they are right.
            self.log("leaving now, abandoning work still in flight")
            self._aborted = True
            self._abort()
        # A fourth press says nothing. One line per state, not one per keypress — a
        # wall of repeats is how someone concludes it is wedged.

    def install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows, or a loop that will not take handlers. Ctrl-C still raises.
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.request_stop, sig.name)

    async def _sleep(self, seconds: float) -> None:
        """Sleep, but wake immediately on a stop request."""
        remaining = seconds
        while remaining > 0 and not self._stop.is_set():
            chunk = min(remaining, self.max_sleep)
            # A timeout is the ordinary case: it means the chunk elapsed with no stop.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=chunk)
            remaining -= chunk

    async def _wait(self, seconds: float,
                    between: Callable[[], Awaitable[None]] | None,
                    every: float = BETWEEN_SECONDS) -> None:
        """Sleep, minding the working orders as it goes.

        A limit the book has moved away from is not something to discover half an hour
        later — the whole reason the order exists is that the structure was judged
        worth having, and the interval it spends unfilled is the interval in which that
        judgement decays.

        `between` is deliberately the lesser job: it tends what is already at the
        broker and may not scan, propose or open anything. So its failures are logged
        and swallowed. A round trip that errors while minding an order must not take
        down the loop that would have opened the next one.
        """
        if between is None:
            await self._sleep(seconds)
            return
        remaining = seconds
        while remaining > 0 and not self._stop.is_set():
            chunk = min(remaining, every)
            await self._sleep(chunk)
            remaining -= chunk
            if self._stop.is_set():
                return
            try:
                await between()
            except Exception as exc:
                self.log(f"between scans: {type(exc).__name__}: {exc}")

    async def run_cycle(self, cycle: Callable[[], Awaitable[None]]) -> bool:
        """Run one cycle, abandoning it if a second stop arrives. True if it finished.

        Cancellation lands at the cycle's next `await`, which can be inside an order
        submission — the exact case the graceful first press exists to protect. That
        is a real cost and it is accepted here for two reasons: somebody pressing
        Ctrl-C twice has asked for it plainly, and an agent that cannot be stopped is
        the worse failure. The safety net is already in place either way — every
        cycle reconciles the ledger against the broker's own positions before it
        proposes anything, so an order that landed without being recorded shows up as
        a divergence on the next run rather than being lost.
        """
        task = asyncio.ensure_future(cycle())
        stop_now = asyncio.ensure_future(self._wait_for_stop_now())
        try:
            done, _ = await asyncio.wait({task, stop_now},
                                         return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                task.result()          # re-raise whatever the cycle raised
                return True
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return False
        finally:
            stop_now.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stop_now

    async def _wait_for_stop_now(self) -> None:
        """Resolve once a second stop request has arrived."""
        while not self._stop_now:
            await asyncio.sleep(_STOP_POLL_SECONDS)

    async def run(self, cycle: Callable[[], Awaitable[None]], *,
                  between: Callable[[], Awaitable[None]] | None = None,
                  max_cycles: int | None = None, until_close: bool = False,
                  wait_for_open: bool = True) -> int:
        """Run `cycle` on the interval. Returns how many cycles actually ran."""
        completed = 0
        while not self._stop.is_set():
            if max_cycles is not None and completed >= max_cycles:
                break

            try:
                clock = await market_clock(self.client)
            except MCPError as exc:
                # Not knowing whether the market is open is not a licence to trade.
                self.log(f"clock unavailable ({exc}); waiting {self.interval / 60:.0f}m")
                await self._sleep(self.interval)
                continue

            # The exchange's date, from the exchange. Adopted before the cycle runs
            # so every DTE, every expiry check and the breaker's daily baseline are
            # measured against the market's calendar rather than this host's.
            session_clock.adopt(clock)
            self._note_session(clock)

            if not clock.is_open:
                if not wait_for_open:
                    self.log("market closed; exiting")
                    break
                delay = clock.seconds_until_open() or self.interval
                self.log(
                    f"market closed — next open {clock.next_open}, "
                    f"sleeping {delay / 60:.0f}m"
                )
                await self._sleep(delay + 5)
                continue

            started = asyncio.get_running_loop().time()
            if not await self.run_cycle(cycle):
                # Abandoned by a second stop request. Not counted: it did not finish,
                # and a coverage table that says otherwise is a false record.
                break
            completed += 1
            elapsed = asyncio.get_running_loop().time() - started

            if until_close:
                remaining = clock.seconds_until_close()
                if remaining is not None and remaining <= self.interval:
                    self.log(
                        f"{remaining / 60:.0f}m to the close, under one interval — stopping"
                    )
                    break

            # Space from the end of the cycle, not the start: a slow cycle delays the
            # next one rather than starting a second alongside it.
            wait = max(0.0, self.interval - elapsed)
            if wait and not self._stop.is_set():
                self.log(f"cycle took {elapsed:.0f}s; next scan in {wait / 60:.0f}m")
            await self._wait(wait, between)

        return completed
