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
from datetime import UTC, datetime, timedelta, timezone
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

# Relative to now, not written down. These were absolute — a Thursday close and the
# Friday open after it — and the suite went red at 13:30 UTC on the Friday, when the
# hardcoded open became a boundary that had *also* passed and the derivation correctly
# answered "open" to a test that wanted "closed". Nothing about the panel had changed;
# the calendar had. A test whose answer depends on the hour it is run cannot tell you
# whether the code is right.
_ET = timezone(timedelta(hours=-4))
_NOW_ET = datetime.now(_ET)
#: A close that has already happened, and the next open still ahead of it.
CLOSE = (_NOW_ET - timedelta(hours=2)).isoformat(sep=" ")
OPEN = (_NOW_ET + timedelta(hours=17)).isoformat(sep=" ")


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


# --- what each gate measured ----------------------------------------------------
#
# The gates tab listed sixteen names and a rejection count, which answers "does this
# gate exist" and "has it ever bitten" — neither of which is a question anyone has
# while watching a book. The answer to the one they do have was already in the journal
# and being discarded: every gate writes its own reading beside its verdict.

def decision(**over) -> dict:
    base = {
        "event": "gate_decision", "ts": at(30), "structure": "QQQ 765/775 call spread",
        "approved": True, "rejected_by": [],
        "gates": [
            {"gate": "daily-loss-halt", "family": "circuit", "passed": True,
             "reason": "within the 5% floor of $89,817"},
            {"gate": "open-position-count", "family": "circuit", "passed": True,
             "reason": "2/20 open positions"},
        ],
    }
    return {**base, **over}


def test_each_gate_carries_the_reading_it_took():
    from halstreet.telemetry.server import _gate_readings

    readings = _gate_readings([decision()])
    assert readings["open-position-count"]["reason"] == "2/20 open positions"
    assert readings["open-position-count"]["passed"] is True
    assert readings["daily-loss-halt"]["structure"] == "QQQ 765/775 call spread"


def test_the_reading_is_the_gates_own_sentence_not_a_recomputation():
    """A panel that re-derives a limit check is one that can disagree with the thing
    it depicts, and this is the half of the system that says no."""
    from halstreet.telemetry.server import _gate_readings

    odd = decision(gates=[{"gate": "g", "passed": True, "reason": "17/20 whatever"}])
    assert _gate_readings([odd])["g"]["reason"] == "17/20 whatever"


def test_only_the_most_recent_evaluation_is_reported():
    """A reading is a measurement of a moment. A history of them is the run journal."""
    from halstreet.telemetry.server import _gate_readings

    old = decision(ts=at(9000), gates=[{"gate": "g", "passed": True, "reason": "old"}])
    new = decision(ts=at(30), gates=[{"gate": "g", "passed": True, "reason": "new"}])
    assert _gate_readings([old, new])["g"]["reason"] == "new"


def test_a_failing_gate_reports_its_reading_too():
    """The one you most want to see. A rejection with no number is just a refusal."""
    from halstreet.telemetry.server import _gate_readings

    rejected = decision(approved=False, rejected_by=["open-position-count"], gates=[
        {"gate": "open-position-count", "passed": False,
         "reason": "20/20 open positions"}])
    reading = _gate_readings([rejected])["open-position-count"]
    assert reading["passed"] is False
    assert reading["reason"] == "20/20 open positions"


def test_a_chain_that_has_never_run_reports_nothing_rather_than_zeroes():
    """Most cycles never reach the gates. Inventing a reading of 0 for every one of
    them would say the book is empty when nothing has looked."""
    from halstreet.telemetry.server import _gate_readings

    assert _gate_readings([{"event": "cycle_start", "ts": at(1)}]) == {}


@pytest.mark.parametrize("gates", [None, [], "all good", [{}], [{"reason": "no name"}]])
def test_an_unusable_gate_list_yields_nothing_rather_than_a_crash(gates):
    from halstreet.telemetry.server import _gate_readings

    assert _gate_readings([decision(gates=gates)]) == {}


def test_a_gate_with_no_reason_is_still_listed():
    """Present-with-nothing-to-say and absent are different facts: the first means the
    gate ran, and the panel draws it differently."""
    from halstreet.telemetry.server import _gate_readings

    readings = _gate_readings([decision(gates=[{"gate": "g", "passed": True}])])
    assert readings["g"]["reason"] == ""


# --- a reading taken after the close --------------------------------------------
#
# `portfolio-greek-bounds` refused a proposal at 16:44 with "no greeks for 2
# contract(s)". That is the gate working: the contracts it could not price were the
# *open position's* legs, so it could not bound the exposure the desk already carries,
# and opening more on an unmeasurable book is the thing fail-closed exists to stop.
#
# It read as a fault because the gates tab showed the reading flat, with no sign that
# the market had been shut for forty-four minutes when it was taken. A gate reading is
# a measurement of a moment, and a moment after the close is a different fact from the
# same words during the session.

def test_a_reading_taken_after_the_close_says_so():
    from halstreet.telemetry.server import _after_hours

    session = {"next_close": "2026-08-27 16:00:00-04:00"}
    assert _after_hours("2026-08-27T20:44:19+00:00", session) is True   # 16:44 ET


def test_a_reading_taken_during_the_session_does_not():
    from halstreet.telemetry.server import _after_hours

    session = {"next_close": "2026-08-27 16:00:00-04:00"}
    assert _after_hours("2026-08-27T16:40:24+00:00", session) is False  # 12:40 ET


def test_the_boundary_itself_counts_as_closed():
    """The close is the moment quoting stops, not the last moment it works."""
    from halstreet.telemetry.server import _after_hours

    session = {"next_close": "2026-08-27 16:00:00-04:00"}
    assert _after_hours("2026-08-27T20:00:00+00:00", session) is True


@pytest.mark.parametrize("session", [None, {}, {"next_close": None},
                                     {"next_close": "whenever"},
                                     {"next_close": "2026-08-27 16:00:00"}])
def test_without_a_usable_close_it_does_not_guess(session):
    """`None`, not `False`. "We cannot tell" and "the market was open" are different
    claims, and the louder one must not be the default."""
    from halstreet.telemetry.server import _after_hours

    assert _after_hours("2026-08-27T20:44:19+00:00", session) is None


@pytest.mark.parametrize("ts", [None, "", "not-a-time", 17])
def test_an_unreadable_reading_time_does_not_guess_either(ts):
    from halstreet.telemetry.server import _after_hours

    assert _after_hours(ts, {"next_close": "2026-08-27 16:00:00-04:00"}) is None


def test_the_gate_readings_carry_it():
    """So the tab can say it beside the reading rather than leaving the reader to
    work out that 16:44 is after four o'clock."""
    from halstreet.telemetry.server import _gate_readings

    events = [
        {"event": "session", "state": "open", "ts": at(30_000),
         "next_close": "2026-08-27 16:00:00-04:00"},
        {"event": "gate_decision", "ts": "2026-08-27T20:44:19+00:00",
         "structure": "SPY put credit spread", "approved": False,
         "gates": [{"gate": "portfolio-greek-bounds", "passed": False,
                    "reason": "no greeks for 2 contract(s)"}]},
    ]
    reading = _gate_readings(events)["portfolio-greek-bounds"]
    assert reading["after_hours"] is True
    assert reading["passed"] is False


def test_a_journal_with_no_session_leaves_the_readings_unlabelled():
    from halstreet.telemetry.server import _gate_readings

    events = [{"event": "gate_decision", "ts": at(30), "structure": "s",
               "gates": [{"gate": "g", "passed": True, "reason": "fine"}]}]
    assert _gate_readings(events)["g"]["after_hours"] is None


# --- inside the committee ----------------------------------------------------------
#
# "deliberating" covered the whole of it: four model calls, roughly a minute, one
# unchanging word. That is a spinner, not a status — it says the agent is alive and
# nothing else, and the report was that the tab showed old history while the
# interesting part was happening.

def test_the_catalyst_finishing_says_the_debate_is_running():
    flight = _in_flight([
        {"event": "candidates", "ts": at(30), "underlying": "NVDA"},
        {"event": "committee_stage", "stage": "catalyst", "ts": at(3),
         "underlying": "NVDA", "lean": "bullish", "confidence": 0.62},
    ])
    assert flight["underlying"] == "NVDA"
    assert "bull" in flight["stage"].lower() and "bear" in flight["stage"].lower()


def test_the_debate_finishing_says_the_judge_is_deciding():
    flight = _in_flight([
        {"event": "committee_stage", "stage": "debate", "ts": at(2), "underlying": "NVDA"},
    ])
    assert "judge" in flight["stage"].lower()


def test_a_stage_record_the_panel_does_not_know_is_not_a_stage():
    """Forward compatibility in the safe direction: an unknown stage claims nothing."""
    assert _in_flight([
        {"event": "committee_stage", "stage": "rebuttal", "ts": at(2), "underlying": "NVDA"},
    ]) is None


def test_the_stages_already_finished_travel_with_the_one_running():
    """So the live card can fill in as it goes instead of appearing whole at the end."""
    flight = _in_flight([
        {"event": "cycle_start", "ts": at(40), "underlying": "NVDA"},
        {"event": "candidates", "ts": at(35), "underlying": "NVDA"},
        {"event": "committee_stage", "stage": "catalyst", "ts": at(20),
         "underlying": "NVDA", "lean": "bullish", "confidence": 0.62},
        {"event": "committee_stage", "stage": "debate", "ts": at(2), "underlying": "NVDA"},
    ])
    assert flight["done"] == ["catalyst", "debate"]
    assert flight["lean"] == "bullish"
    assert flight["confidence"] == 0.62


def test_the_previous_underlyings_stages_do_not_follow_the_next_one():
    """The agent works the universe one name at a time, and the journal is one file.

    Without the guard the live card would open on AMD already showing NVDA's catalyst
    read — a fabricated read, attributed to the wrong name, on the one surface whose
    whole job is to say what is happening now.
    """
    flight = _in_flight([
        {"event": "committee_stage", "stage": "catalyst", "ts": at(50),
         "underlying": "NVDA", "lean": "bullish", "confidence": 0.62},
        {"event": "committee", "ts": at(40), "underlying": "NVDA"},
        {"event": "cycle_start", "ts": at(20), "underlying": "AMD"},
        {"event": "candidates", "ts": at(3), "underlying": "AMD"},
    ])
    assert flight["underlying"] == "AMD"
    assert flight["done"] == []
    assert flight["lean"] is None
