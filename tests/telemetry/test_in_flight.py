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

def test_a_session_record_goes_stale_when_nothing_is_writing():
    """Seen live: the soak stopped at 15:40 and the badge still said OPEN at 16:10.

    The record is a report of a crossing, not a live reading. With no agent running
    there is nothing left to write the close, so "open" means "open when we last
    looked" and the panel has to be able to say which.
    """
    from halstreet.telemetry.server import SESSION_STALE_S, _last_session

    quiet = _last_session([
        {"event": "session", "state": "open", "ts": at(20_000)},
        {"event": "cycle_start", "ts": at(SESSION_STALE_S + 60)},
    ])
    assert quiet["state"] == "open", "still reported — it is what was last seen"
    assert quiet["stale"] is True, "but no longer asserted"


def test_a_running_agent_keeps_its_session_record_current():
    from halstreet.telemetry.server import _last_session

    live = _last_session([
        {"event": "session", "state": "open", "ts": at(20_000)},
        {"event": "cycle_start", "ts": at(4)},
    ])
    assert live["stale"] is False


def test_staleness_is_measured_from_the_journal_not_from_the_record():
    """A market that opened at 09:30 is a nine-hour-old record at 18:30 and a
    perfectly current one at 14:00. What makes it stale is silence everywhere else."""
    from halstreet.telemetry.server import _last_session

    old_record_busy_agent = _last_session([
        {"event": "session", "state": "open", "ts": at(30_000)},
        {"event": "committee", "ts": at(10)},
    ])
    assert old_record_busy_agent["stale"] is False


def test_a_journal_with_no_session_record_has_nothing_to_stamp():
    from halstreet.telemetry.server import _last_session

    assert _last_session([{"event": "cycle_start", "ts": at(1)}]) is None


def test_an_unreadable_last_timestamp_reads_as_stale_rather_than_current():
    """Fail toward withdrawing the claim. An unreadable clock is not evidence that
    the market is open."""
    from halstreet.telemetry.server import _last_session

    assert _last_session([
        {"event": "session", "state": "open", "ts": at(100)},
        {"event": "cycle_start", "ts": "not-a-time"},
    ])["stale"] is True
