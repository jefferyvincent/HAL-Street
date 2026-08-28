"""The session date, which is the exchange's and not this machine's.

Nine `date.today()` calls answered a question about the market by reading the host's
calendar. They agree most of the time, which is what made it dangerous: run the agent
on a UTC box after 8pm New York and every DTE is off by one, the DTE floor admits
contracts a day nearer expiry than it believes, and the breaker thinks a new session
started mid-afternoon. Nothing errors — the numbers are quietly wrong, and only outside
US business hours, which is exactly when nobody is watching.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from halstreet import clock
from halstreet.agent.brainstem.schedule import MarketClock

ET = timezone(timedelta(hours=-4))


@pytest.fixture(autouse=True)
def clean():
    clock.reset()
    yield
    clock.reset()


def broker_at(stamp: str) -> MarketClock:
    return MarketClock.parse({"is_open": True, "timestamp": stamp})


# --- the broker is the authority ---------------------------------------------------

def test_the_session_date_comes_from_the_exchanges_own_clock():
    """No timezone database, no hardcoded venue.

    Alpaca reports its timestamp in exchange-local time with the offset attached, so
    the date falls out of the value itself. A `ZoneInfo("America/New_York")` here would
    be a second claim about the world to keep in sync with the broker's.
    """
    assert broker_at("2026-08-26T17:19:17-04:00").session_date == date(2026, 8, 26)
    clock.adopt(broker_at("2026-08-26T17:19:17-04:00"))
    assert clock.today() == date(2026, 8, 26)
    assert clock.source() == "broker"


def test_the_hosts_calendar_does_not_override_the_exchanges():
    """The case the bug actually needs: a machine a day ahead of the market.

    23:30 UTC on the 26th is 19:30 in New York — still the 26th there. A host in UTC+2
    would already call it the 27th, and every DTE computed from it would be short by a
    day.
    """
    clock.adopt(broker_at("2026-08-26T19:30:00-04:00"))
    assert clock.today() == date(2026, 8, 26)


def test_a_clock_with_no_timestamp_is_not_adopted():
    assert clock.adopt(MarketClock.parse({"is_open": True})) is None
    assert clock.source() == "unset"


def test_a_raw_payload_works_as_well_as_a_parsed_clock():
    """So a caller does not have to reach into the scheduler's types to set the date."""
    assert clock.adopt({"timestamp": "2026-08-26T17:19:17-04:00"}) == date(2026, 8, 26)


@pytest.mark.parametrize("junk", [{}, {"timestamp": ""}, {"timestamp": "not a time"}, None, 7])
def test_nothing_unusable_is_adopted(junk):
    assert clock.adopt(junk) is None
    assert clock.source() == "unset"


# --- the fallback is counted, never silent ----------------------------------------

def test_falling_back_to_the_host_calendar_is_recorded():
    """A fallback that hides is worse than no fallback.

    A run that computed a DTE from the machine's calendar must not be indistinguishable
    in the record from one that asked the exchange.
    """
    assert clock.fallbacks() == 0
    # Comparing against the host calendar is the point of this test: with nothing
    # adopted, that is exactly what the fallback must return.
    assert clock.today() == date.today()  # noqa: DTZ011
    assert clock.today() == date.today()  # noqa: DTZ011
    assert clock.fallbacks() == 2
    assert "unset" in clock.describe()


def test_adopting_stops_the_fallback_and_keeps_the_count():
    clock.today()                       # one fallback, before the broker answered
    clock.adopt(broker_at("2026-08-26T10:00:00-04:00"))
    clock.today()
    clock.today()
    assert clock.fallbacks() == 1, "adopted answers must not be counted as fallbacks"
    assert "1 fallback(s)" in clock.describe()


def test_a_later_clock_replaces_an_earlier_one():
    """The session rolls over while the process keeps running."""
    clock.adopt(broker_at("2026-08-26T19:30:00-04:00"))
    clock.adopt(broker_at("2026-08-27T09:31:00-04:00"))
    assert clock.today() == date(2026, 8, 27)


# --- nothing in the trading path reads the host calendar directly ------------------

def test_no_module_calls_date_today_behind_the_clocks_back():
    """The property that makes the rest of this meaningful.

    One `date.today()` may exist — the documented fallback inside `clock` itself.
    Anywhere else is a module that has quietly gone back to asking the machine.
    """
    import pathlib

    root = pathlib.Path(clock.__file__).parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "clock.py":
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if "date.today()" in code:
                offenders.append(f"{path.relative_to(root)}:{n}")
    assert not offenders, f"these read the host calendar directly: {offenders}"


def test_utcnow_is_not_a_substitute_either():
    """UTC is not the exchange either — it is just a different wrong answer.

    Between 20:00 and 00:00 New York time, UTC is already tomorrow.
    """
    et_evening = datetime(2026, 8, 26, 20, 30, tzinfo=ET)
    assert et_evening.date() == date(2026, 8, 26)
    assert et_evening.astimezone(UTC).date() == date(2026, 8, 27)
