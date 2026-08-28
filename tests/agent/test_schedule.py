"""The scheduler: when it runs, and more importantly when it refuses to."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from halstreet.agent.brainstem import schedule
from halstreet.agent.brainstem.schedule import MarketClock, Scheduler
from halstreet.execution.mcp_client import MCPError

NOW = datetime(2026, 8, 26, 13, 45, tzinfo=UTC)


def payload(is_open: bool, *, open_in_min=60, close_in_min=120):
    return {
        "is_open": is_open,
        "timestamp": NOW.isoformat(),
        "next_open": (NOW + timedelta(minutes=open_in_min)).isoformat(),
        "next_close": (NOW + timedelta(minutes=close_in_min)).isoformat(),
    }


class FakeClient:
    """Serves a scripted sequence of clock responses."""

    def __init__(self, *clocks, error: Exception | None = None):
        self._clocks = list(clocks)
        self.error = error
        self.calls = 0

    async def call(self, tool, args=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self._clocks.pop(0) if len(self._clocks) > 1 else self._clocks[0]


def run(scheduler, cycle, **kw):
    return asyncio.run(scheduler.run(cycle, **kw))


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """Make every sleep instant so the tests do not wait on wall-clock time."""
    async def instant(self, seconds):
        return
    monkeypatch.setattr(Scheduler, "_sleep", instant)


# --- market hours ------------------------------------------------------------------

def test_runs_while_the_market_is_open():
    ran = []
    s = Scheduler(FakeClient(payload(True)), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)

    assert run(s, cycle, max_cycles=3) == 3
    assert len(ran) == 3


def test_does_not_run_while_the_market_is_closed():
    """Scanning at 03:00 burns tokens on stale quotes and may act on them."""
    ran = []
    s = Scheduler(FakeClient(payload(False), payload(True)), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)

    run(s, cycle, max_cycles=1)
    assert len(ran) == 1          # only after it reopened
    assert s.client.calls >= 2    # it checked, waited, and checked again


def test_exits_immediately_when_told_not_to_wait():
    ran = []
    s = Scheduler(FakeClient(payload(False)), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)

    assert run(s, cycle, wait_for_open=False) == 0
    assert ran == []


def test_market_hours_come_from_the_broker_not_the_local_clock():
    """A local datetime knows nothing about holidays or early closes."""
    import inspect

    from halstreet.agent.brainstem import schedule
    source = inspect.getsource(schedule.Scheduler.run)
    assert "market_clock" in source
    assert "weekday" not in source and "hour" not in source


def test_an_unavailable_clock_does_not_licence_trading():
    ran = []
    s = Scheduler(FakeClient(error=MCPError("down")), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)

    s.request_stop("test")   # otherwise it would retry forever
    run(s, cycle)
    assert ran == []


# --- pacing --------------------------------------------------------------------------

def test_stops_at_the_close_when_asked():
    """A judged window ends at the bell, not after a fixed count."""
    ran = []
    s = Scheduler(FakeClient(payload(True, close_in_min=20)), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)

    assert run(s, cycle, until_close=True) == 1   # 20m left is under one 30m interval


def test_keeps_going_when_the_close_is_further_off_than_an_interval():
    s = Scheduler(FakeClient(payload(True, close_in_min=300)), 30, log=lambda m: None)

    async def cycle():
        return

    assert run(s, cycle, until_close=True, max_cycles=4) == 4


def test_a_stop_request_ends_the_run_after_the_current_cycle():
    ran = []
    s = Scheduler(FakeClient(payload(True)), 30, log=lambda m: None)

    async def cycle():
        ran.append(1)
        s.request_stop("test")

    assert run(s, cycle, max_cycles=10) == 1
    assert len(ran) == 1


def test_a_failing_cycle_propagates_rather_than_looping_silently():
    """run_once already swallows per-symbol errors; anything reaching here is real."""
    s = Scheduler(FakeClient(payload(True)), 30, log=lambda m: None)

    async def cycle():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run(s, cycle, max_cycles=1)


# --- clock parsing ---------------------------------------------------------------------

def test_parses_the_brokers_clock():
    c = MarketClock.parse(payload(True))
    assert c.is_open
    assert c.seconds_until_close() == pytest.approx(120 * 60)
    assert c.seconds_until_open() is None


def test_seconds_until_open_when_closed():
    c = MarketClock.parse(payload(False, open_in_min=45))
    assert c.seconds_until_open() == pytest.approx(45 * 60)


def test_tolerates_a_malformed_clock():
    c = MarketClock.parse({"is_open": True, "next_close": "not-a-date"})
    assert c.is_open and c.next_close is None
    assert c.seconds_until_close() is None


@pytest.mark.parametrize("stamp", [
    "2026-08-26T14:45:00Z",         # Zulu — what a lot of APIs send
    "2026-08-26T14:45:00+00:00",    # the same instant, spelled out
    "2026-08-26T10:45:00-04:00",    # and with a real offset, which Alpaca does send
])
def test_the_clock_parses_every_timestamp_alpaca_might_send(stamp):
    """A failed parse is silent and its consequence is not.

    `when()` swallows a ValueError and returns None, which is right — a malformed
    timestamp should not crash a run. But `next_open=None` means the scheduler has no
    time to wait until, so the failure surfaces as a process that sits there rather
    than an error anyone can see. That is the worst way for a parse bug to present,
    which is why the parse is pinned here instead of trusted.

    This exists because a lint autofix rewrote `.replace("Z", "+00:00")` into
    `.removesuffix("Z") + "+00:00"` — identical on the first case, ValueError on the
    other two. The substitution was never needed: `fromisoformat` has handled all
    three natively since 3.11, which this project requires.
    """
    clock = MarketClock.parse({"is_open": True, "next_open": stamp, "next_close": stamp})
    assert clock.next_open is not None, f"{stamp} did not parse — the scheduler would hang"
    assert clock.next_open == datetime(2026, 8, 26, 14, 45, tzinfo=UTC)


# --- the session date, adopted before anything trades ------------------------------

def test_the_scheduler_adopts_the_exchanges_date_before_running_a_cycle():
    """The date every DTE is measured from must come from the broker, not the host.

    Asserted here rather than trusted: removing the `adopt` call leaves every other
    test passing, because they all run on a machine whose calendar happens to agree
    with the exchange's. That agreement is the whole reason this bug is invisible, so
    the wiring needs a test that does not depend on it.
    """
    from halstreet import clock as session_clock

    session_clock.reset()
    try:
        # 19:30 in New York is still the 26th there, and already the 27th in UTC.
        payload = {"is_open": True,
                   "timestamp": "2026-08-26T19:30:00-04:00",
                   "next_open": "2026-08-27T09:30:00-04:00",
                   "next_close": "2026-08-26T20:00:00-04:00"}
        seen: list = []

        async def cycle():
            seen.append(session_clock.today())

        run(Scheduler(FakeClient(payload), 30, log=lambda *_: None), cycle, max_cycles=1)

        assert seen == [date(2026, 8, 26)]
        assert session_clock.source() == "broker"
        assert session_clock.fallbacks() == 0, "the host calendar was never consulted"
    finally:
        session_clock.reset()


# Note: there is deliberately no test here for "the clock errors forever". The
# scheduler retries on the interval rather than giving up — correct, since a broker
# blip is not a reason to end the session — but `max_cycles` counts *completed* cycles,
# so a clock that never answers is unbounded by it. With the autouse fixture making
# every sleep instant, such a test spins rather than fails. The date staying unadopted
# in that case is covered by `test_clock.py` instead, where it needs no scheduler.


# --- the bell ---------------------------------------------------------------------

class _Recorder:
    def __init__(self): self.events = []
    def write(self, event, **fields): self.events.append((event, fields))


def _clock(is_open: bool):
    from datetime import datetime
    return MarketClock(
        is_open=is_open,
        next_open=datetime.fromisoformat("2026-08-28T09:30:00-04:00"),
        next_close=datetime.fromisoformat("2026-08-27T16:00:00-04:00"),
        timestamp=datetime.fromisoformat("2026-08-27T10:00:00-04:00"),
    )


def _sched(journal):
    from halstreet.agent.brainstem.schedule import Scheduler
    return Scheduler(client=None, interval_minutes=30, log=lambda _: None, journal=journal)


def test_the_bell_is_written_once_per_transition_not_once_per_poll():
    """The scheduler asks the clock every interval, all night.

    Writing what it heard each time would fill an append-only file with noise and,
    worse, leave a reader unable to tell the moment the session opened from the many
    times it was already open.
    """
    j = _Recorder()
    s = _sched(j)
    for state in (True, True, True, False, False, True):
        s._note_session(_clock(state))
    assert [f["state"] for _, f in j.events] == ["open", "closed", "open"]


def test_the_first_observation_is_marked_as_arrival_not_as_a_bell():
    # A scheduler starting mid-session has no prior state, and neither does a reader
    # joining mid-file. Sounding an opening bell for it would be a lie about when.
    j = _Recorder()
    s = _sched(j)
    s._note_session(_clock(True))
    s._note_session(_clock(False))
    assert [f["observed"] for _, f in j.events] == [True, False]


def test_the_bell_carries_the_exchanges_own_date_and_the_next_boundary():
    j = _Recorder()
    _sched(j)._note_session(_clock(True))
    _, fields = j.events[0]
    assert fields["session_date"] == "2026-08-27", "the exchange's date, not the host's"
    assert fields["next_close"].startswith("2026-08-27 16:00")


def test_a_scheduler_with_no_journal_still_runs():
    # Headless is the default; the journal is an optional observer, never a
    # dependency of the loop that trades.
    from halstreet.agent.brainstem.schedule import Scheduler
    s = Scheduler(client=None, interval_minutes=30, log=lambda _: None)
    s._note_session(_clock(True))  # must not raise


# --- stopping it -------------------------------------------------------------------
#
# The first signal is graceful by design: it lets the current cycle finish so a
# half-placed structure is never left behind. But a cycle over a discovered universe
# is six committees and took 73 seconds on a live run, and for all of those seconds
# Ctrl-C looks like it did nothing at all. That is the report — "ctrl c does nothing"
# — and the answer is not to make the first one abrupt.

def test_the_first_signal_is_still_graceful():
    """A cycle interrupted mid-submission is the failure this politeness prevents."""
    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    s.request_stop("SIGINT")
    assert s.stopping is True
    assert s.should_exit_now is False


def test_a_second_signal_asks_to_stop_now():
    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    s.request_stop("SIGINT")
    s.request_stop("SIGINT")
    assert s.should_exit_now is True


def test_the_first_signal_says_how_to_stop_now():
    """Otherwise the wait is indistinguishable from the signal being ignored.

    Which is exactly how it was read: a minute of silence after Ctrl-C, and nothing
    on screen saying the request had landed or how to insist.
    """
    said = []
    s = Scheduler(FakeClient({"is_open": True}), 30, log=said.append)
    s.request_stop("SIGINT")
    assert any("again" in line.lower() for line in said)


def test_the_second_signal_says_it_is_not_waiting():
    said = []
    s = Scheduler(FakeClient({"is_open": True}), 30, log=said.append)
    s.request_stop("SIGINT")
    s.request_stop("SIGINT")
    assert any("not waiting" in line.lower() or "now" in line.lower()
               for line in said[1:])


def test_a_third_signal_does_not_start_repeating_itself():
    said = []
    s = Scheduler(FakeClient({"is_open": True}), 30, log=said.append,
                  abort=lambda: None)
    for _ in range(5):
        s.request_stop("SIGINT")
    assert len(said) == 3, "one line per state, not one per keypress"


# --- and actually leaving ----------------------------------------------------------
#
# Cancelling the cycle was as far as the second press went, and it was not far enough.
# The committee's model calls run on `asyncio.to_thread`; a thread cannot be cancelled,
# so `asyncio.run` joined whichever call was still in flight on its way out. Measured
# on a probe: a cancelled cycle sat for the full twenty seconds of its worker before
# the process ended, answering nothing. From a terminal that is indistinguishable from
# a wedged process, and it is what "ctrl c does nothing, it gets locked" was.

def test_a_third_signal_leaves_without_waiting_for_anything():
    left = []
    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None,
                  abort=lambda: left.append(1))
    s.request_stop("SIGINT")
    s.request_stop("SIGINT")
    assert left == [], "twice is still a request — the cycle is being cancelled"
    s.request_stop("SIGINT")
    assert left == [1]


def test_a_third_signal_says_what_it_is_abandoning():
    """Leaving quietly and hanging look the same from outside. One of them says so."""
    said = []
    s = Scheduler(FakeClient({"is_open": True}), 30, log=said.append,
                  abort=lambda: None)
    for _ in range(3):
        s.request_stop("SIGINT")
    assert "leaving" in said[-1].lower() or "abandon" in said[-1].lower()


def test_hard_exit_is_not_a_polite_exit():
    """`os._exit`, because skipping the interpreter's shutdown is the entire point."""
    codes = []
    real = schedule.os._exit
    schedule.os._exit = codes.append
    try:
        schedule.hard_exit()
    finally:
        schedule.os._exit = real
    assert codes == [schedule.INTERRUPTED]


def test_hard_exit_flushes_before_it_goes():
    """os._exit does not, so anything still buffered would be lost on the way out."""
    order = []
    real_exit, real_flush = schedule.os._exit, schedule.sys.stdout.flush
    schedule.os._exit = lambda code: order.append("exit")
    schedule.sys.stdout.flush = lambda: order.append("flush")
    try:
        schedule.hard_exit()
    finally:
        schedule.os._exit, schedule.sys.stdout.flush = real_exit, real_flush
    assert order[0] == "flush" and order[-1] == "exit"


#: Run in a subprocess because the defect is a property of interpreter shutdown, and
#: nothing inside one process can observe its own failure to end.
_ESCAPE = """
import asyncio, time
from halstreet.agent.brainstem import schedule

async def main():
    task = asyncio.ensure_future(asyncio.to_thread(time.sleep, 20))
    await asyncio.sleep(0.1)
    task.cancel()                      # the second Ctrl-C, in effect
    schedule.hard_exit()

asyncio.run(main())
print("returned through the interpreter")
"""


def test_hard_exit_escapes_a_worker_thread_that_cannot_be_cancelled():
    """The reason it exists. A plain return here waits out the whole 20s sleep."""
    started = time.monotonic()
    proc = subprocess.run(  # noqa: S603 - this interpreter, a literal above
        [sys.executable, "-c", _ESCAPE], capture_output=True, text=True, timeout=30)
    assert proc.returncode == schedule.INTERRUPTED
    assert "returned through the interpreter" not in proc.stdout
    assert time.monotonic() - started < 10, "it waited for the worker thread"


def test_stopping_now_ends_the_run_without_another_cycle():
    ran = []

    async def cycle():
        ran.append(1)
        s.request_stop("SIGINT")
        s.request_stop("SIGINT")

    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    run(s, cycle, max_cycles=5)
    assert len(ran) == 1


def test_a_second_signal_abandons_the_cycle_that_is_running():
    """The point of the second press, and the only part that needed new machinery.

    The first press already skips the sleep; what it cannot do is shorten the cycle
    already in flight, which is where all 73 of those seconds are.
    """
    reached_the_end = []

    async def slow_cycle():
        s.request_stop("SIGINT")
        s.request_stop("SIGINT")
        await asyncio.sleep(30)          # the committee, in effect
        reached_the_end.append(1)

    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    run(s, slow_cycle, max_cycles=1)
    assert reached_the_end == [], "the cycle should have been cut short"


def test_a_cancelled_cycle_is_not_counted_as_completed():
    """It did not finish, and a coverage table that says otherwise is a false record."""
    async def slow_cycle():
        s.request_stop("SIGINT")
        s.request_stop("SIGINT")
        await asyncio.sleep(30)

    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    assert run(s, slow_cycle, max_cycles=1) == 0


def test_one_signal_still_lets_the_cycle_finish():
    """The graceful path must survive the addition of the abrupt one."""
    finished = []

    async def cycle():
        s.request_stop("SIGINT")
        await asyncio.sleep(0)
        finished.append(1)

    s = Scheduler(FakeClient({"is_open": True}), 30, log=lambda *_: None)
    assert run(s, cycle, max_cycles=3) == 1
    assert finished == [1]


# --- the cadence, read once --------------------------------------------------------
#
# `run.py` held the only copy and the panel wanted the same number to say when a scan
# is next due. A second `int(os.environ.get(...) or 30)` is a second claim about the
# cadence, free to drift from the one the scheduler is actually keeping.

def test_the_cadence_comes_from_the_environment():
    assert schedule.scan_interval_seconds({"SCAN_INTERVAL_MINUTES": "5"}) == 300


def test_an_unset_cadence_falls_back_rather_than_raising():
    assert schedule.scan_interval_seconds({}) == schedule.DEFAULT_INTERVAL_MINUTES * 60


@pytest.mark.parametrize("bad", ["", "soon", "5.5", None])
def test_an_unreadable_cadence_falls_back_too(bad):
    """The panel asks this on every request. A misconfigured .env must not empty it."""
    assert schedule.scan_interval_seconds({"SCAN_INTERVAL_MINUTES": bad}) \
        == schedule.DEFAULT_INTERVAL_MINUTES * 60


def test_a_cadence_of_zero_is_still_a_cadence():
    """Same floor the scheduler itself applies. A zero-second loop is not a schedule."""
    assert schedule.scan_interval_seconds({"SCAN_INTERVAL_MINUTES": "0"}) == 60
