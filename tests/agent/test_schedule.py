"""The scheduler: when it runs, and more importantly when it refuses to."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest

from halstreet.agent.schedule import MarketClock, Scheduler
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

    from halstreet.agent import schedule
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
    from halstreet.agent.schedule import Scheduler
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
    from halstreet.agent.schedule import Scheduler
    s = Scheduler(client=None, interval_minutes=30, log=lambda _: None)
    s._note_session(_clock(True))  # must not raise
