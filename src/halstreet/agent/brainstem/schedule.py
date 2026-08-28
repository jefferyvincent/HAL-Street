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

**Stopping is deliberate.** `--until-close` ends at the bell rather than running to a
count, which is what a judged window actually wants. SIGINT and SIGTERM finish the
current cycle and shut down cleanly rather than abandoning a half-submitted order.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
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


class Scheduler:
    """Repeats a coroutine on a cadence, only while the market is open."""

    def __init__(self, client: AlpacaMCP, interval_minutes: int, *,
                 log: Callable[[str], None] = print,
                 journal: Any = None,
                 max_sleep_seconds: float = 900.0) -> None:
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

    def request_stop(self, reason: str = "signal") -> None:
        if not self._stop.is_set():
            self.log(f"stop requested ({reason}); finishing the current cycle")
            self._stop.set()

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

    async def run(self, cycle: Callable[[], Awaitable[None]], *,
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
            await cycle()
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
            await self._sleep(wait)

        return completed
