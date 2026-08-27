"""Whether the agent is mid-cycle, and how the panel is told.

Most cycles produce no gate decision, so a panel keyed on outcomes looks asleep while
the agent works. The committee tab had the sharpest version: its slowest stage is
three model calls deep, and between "nothing here yet" and a finished card there was
a minute of blank screen that reads as a broken tab.

Nothing reports "I am busy". This is derived from the last record written plus a
clock, which can be wrong in exactly one direction — a process killed mid-cycle looks
busy until the ceiling passes — and these tests are mostly about that direction.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from halstreet.telemetry.server import IN_FLIGHT_S, _age, _in_flight


def at(seconds_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


def test_the_stage_is_the_last_thing_the_agent_wrote():
    flight = _in_flight([
        {"event": "cycle_start", "ts": at(20), "underlying": "SPY"},
        {"event": "committee", "ts": at(4), "underlying": "SPY"},
    ])
    assert flight["event"] == "committee"
    assert flight["underlying"] == "SPY"
    assert flight["stage"] == "writing the proposal"


def test_a_stage_that_has_said_nothing_for_minutes_is_not_in_progress():
    """A killed process must stop looking busy on its own.

    The failure mode this guards is the worst kind of status light: one that says the
    opposite of what is true and never changes.
    """
    assert _in_flight([{"event": "committee", "ts": at(IN_FLIGHT_S + 1)}]) is None


def test_the_ceiling_is_short_because_a_cycle_is_short():
    assert IN_FLIGHT_S <= 300, "a stale spinner is worse than no spinner"


def test_events_that_end_a_cycle_are_not_stages():
    """An order or a gate decision means the work is done, not that it is happening."""
    for done in ("order", "gate_decision", "exit_decision", "session", "error"):
        assert _in_flight([{"event": done, "ts": at(1)}]) is None, done


def test_a_considered_pass_reads_as_idle_rather_than_stuck_at_the_gates():
    """The common case, and the one that made `proposal` a bad stage to report.

    Most cycles end in a pass. `proposal` is the last thing they write, so calling it
    a stage would light the panel amber for minutes on an agent doing nothing — and
    the gates it would claim to be waiting on are deterministic and take microseconds.
    """
    assert _in_flight([{"event": "proposal", "ts": at(1),
                        "underlying": "SPY", "passed": True}]) is None


def test_a_finished_cycle_reads_as_idle_even_though_its_stages_are_recent():
    """The last record wins. Walking back past it to find a stage would never stop."""
    assert _in_flight([
        {"event": "committee", "ts": at(9), "underlying": "QQQ"},
        {"event": "proposal", "ts": at(8), "underlying": "QQQ"},
        {"event": "gate_decision", "ts": at(7), "underlying": "QQQ"},
        {"event": "order", "ts": at(6), "underlying": "QQQ"},
    ]) is None


def test_an_empty_journal_is_idle_rather_than_an_error():
    assert _in_flight([]) is None


@pytest.mark.parametrize("ts", [None, "", "not-a-time", 17, {"ts": 1}])
def test_an_unreadable_timestamp_is_idle_rather_than_a_crash(ts):
    """This route is polled every five seconds. A raise here empties the whole panel."""
    assert _in_flight([{"event": "committee", "ts": ts}]) is None
    assert _age(ts) is None


def test_a_naive_timestamp_does_not_raise():
    """The same defect that took down the news reader: subtracting an aware datetime
    from a naive one raises `TypeError`, and it raised from outside the guard."""
    assert _age("2026-08-27T16:00:00") is None


def test_the_underlying_is_empty_rather_than_missing_when_a_stage_has_none():
    flight = _in_flight([{"event": "cycle_start", "ts": at(1)}])
    assert flight["underlying"] == ""


def test_it_is_in_the_snapshot_the_panel_reads(tmp_path):
    """A derivation nothing serves is a derivation nobody sees."""
    from halstreet.telemetry.server import snapshot

    journal = tmp_path / "j.jsonl"
    journal.write_text(json.dumps(
        {"event": "committee", "ts": at(2), "underlying": "IWM"}) + "\n")
    state = snapshot(journal_path=str(journal), ledger_path=str(tmp_path / "l.json"),
                     breaker_path=str(tmp_path / "c.json"))
    assert state["in_flight"]["underlying"] == "IWM"


# --- the session badge ----------------------------------------------------------
#
# A session record reports a *crossing*, not a live reading. When the agent exits
# mid-session nothing writes the close, and the badge went on asserting OPEN into the
# evening — the soak stopped at 15:40 and the panel said the market was open at 16:10.
#
# The first fix hedged: it showed the last-seen state with a question mark. That was
# the wrong answer to a question with a right one. The record already carries the
# broker's own `next_close`, that time has passed, and "closed" is a statement the
# panel is entitled to make.

CLOSE = "2026-08-27 16:00:00-04:00"
OPEN = "2026-08-28 09:30:00-04:00"


def session(**over) -> dict:
    base = {"event": "session", "state": "open", "ts": at(20_000),
            "next_open": OPEN, "next_close": CLOSE, "observed": True}
    return {**base, **over}


def test_a_close_nobody_recorded_is_still_a_close():
    """The bug the user reported: the market shut at 16:00 and the badge said OPEN.

    Nothing was running to write it down. The broker had published when it would
    happen, and that time had passed.
    """
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(), {"event": "cycle_start", "ts": at(1800)}])
    assert market["state"] == "closed"
    assert market["source"] == "boundary"
    assert market["crossed_at"] == CLOSE


def test_the_record_it_was_derived_from_is_kept_beside_it():
    """A derivation that hides its input cannot be checked against it."""
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(), {"event": "cycle_start", "ts": at(1800)}])
    assert market["recorded"] == "open"
    assert market["state"] == "closed"


def test_a_boundary_still_in_the_future_leaves_the_record_alone():
    """Mid-session: the close has not happened, and inventing one would be worse than
    the bug this replaced."""
    from halstreet.telemetry.server import _last_session

    ahead = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    market = _last_session([session(next_open=ahead, next_close=ahead),
                            {"event": "cycle_start", "ts": at(5)}])
    assert market["state"] == "open"
    assert market["source"] == "observed"


def test_the_later_boundary_wins_so_it_survives_a_weekend():
    """On Saturday the Friday close is the last thing that happened; on Monday morning
    it is the Monday open. Taking whichever key happens to parse first would flip the
    badge to whatever the dictionary order was."""
    from halstreet.telemetry.server import _last_session

    past_open = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    past_close = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    market = _last_session([session(state="closed", next_open=past_open,
                                    next_close=past_close)])
    assert market["state"] == "closed", "the close is the more recent of the two"

    market = _last_session([session(state="closed", next_open=past_close,
                                    next_close=past_open)])
    assert market["state"] == "open", "and now the open is"


def test_with_no_boundary_and_nothing_writing_the_panel_says_it_does_not_know():
    """The one case that is genuinely unknown, and the only one that hedges."""
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(next_open=None, next_close=None),
                            {"event": "cycle_start", "ts": at(20_000)}])
    assert market["source"] == "last-seen"
    assert market["state"] == "open", "still reported — it is what was last seen"


def test_with_no_boundary_but_an_agent_running_the_record_stands():
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(next_open=None, next_close=None),
                            {"event": "cycle_start", "ts": at(5)}])
    assert market["source"] == "observed"
    assert market["stale"] is False


@pytest.mark.parametrize("bad", [None, "", "tomorrow", 17, "2026-13-99"])
def test_an_unreadable_boundary_is_ignored_rather_than_fatal(bad):
    """This route is polled every five seconds. A raise here empties the whole panel."""
    from halstreet.telemetry.server import _last_session, _when

    assert _when(bad) is None
    market = _last_session([session(next_open=bad, next_close=bad),
                            {"event": "cycle_start", "ts": at(5)}])
    assert market["state"] == "open"


def test_a_boundary_with_no_offset_is_refused():
    """`2026-08-27 16:00:00` could be any of twenty-four moments. Alpaca sends the
    offset; a bare timestamp is not the broker's answer and must not be treated as one."""
    from halstreet.telemetry.server import _when

    assert _when("2026-08-27 16:00:00") is None


def test_staleness_is_measured_from_the_journal_not_from_the_record():
    """A market that opened at 09:30 is a nine-hour-old record at 18:30 and a
    perfectly current one at 14:00. What makes it stale is silence everywhere else."""
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(next_open=None, next_close=None, ts=at(30_000)),
                            {"event": "committee", "ts": at(10)}])
    assert market["stale"] is False


def test_a_journal_with_no_session_record_has_nothing_to_report():
    from halstreet.telemetry.server import _last_session

    assert _last_session([{"event": "cycle_start", "ts": at(1)}]) is None


def test_an_unreadable_last_timestamp_reads_as_stale_rather_than_current():
    """Fail toward withdrawing the claim. An unreadable clock is not evidence that
    the market is open."""
    from halstreet.telemetry.server import _last_session

    market = _last_session([session(next_open=None, next_close=None),
                            {"event": "cycle_start", "ts": "not-a-time"}])
    assert market["stale"] is True
    assert market["source"] == "last-seen"


def test_nothing_here_knows_where_the_exchange_is():
    """The whole reason this reads the broker's boundaries instead of a calendar.

    New York, daylight saving, half-days and holidays are not knowledge this process
    should hold — `clock.py` says so at length, and a timezone table here would be a
    second claim about the world to keep in sync with the first.
    """
    source = Path("src/halstreet/telemetry/server.py").read_text()
    for banned in ("ZoneInfo", "America/New_York", "pytz", "timedelta(hours=-4)"):
        assert banned not in source, banned
