"""What a soak says it reached, read back out of a journal.

The coverage table is the entire output of a soak run — a session that reports "no
errors" without saying which lifecycle events never fired proves very little. This
lived in `scripts/soak.py`, where the only test that could reach it had to load the
file through `importlib.util.spec_from_file_location` and could not assert on the
table at all.

The multi-run warning below is the one with a story: two soaks shared a journal for an
hour, one of them a version behind, and the coverage read as a single clean session.
"""

from __future__ import annotations

import json

import pytest

from halstreet.agent.hippocampus import soak


def _journal(tmp_path, *events):
    path = tmp_path / "run.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return str(path)


def test_an_empty_journal_reaches_nothing_and_says_so(tmp_path):
    path = _journal(tmp_path)
    seen, missing = soak.coverage(path)
    assert not seen
    assert missing == list(soak.LIFECYCLE)
    assert "NOT reached this run" in soak.render(path)


def test_events_are_counted_and_the_rest_reported_missing(tmp_path):
    path = _journal(tmp_path,
                    {"event": "cycle_start", "run": "r1"},
                    {"event": "cycle_start", "run": "r1"},
                    {"event": "proposal", "run": "r1"})
    seen, missing = soak.coverage(path)
    assert seen["cycle_start"] == 2
    assert seen["proposal"] == 1
    assert "cycle_start" not in missing
    assert "halt" in missing


def test_a_fully_exercised_run_reports_nothing_missing(tmp_path):
    path = _journal(tmp_path, *({"event": name, "run": "r1"} for name in soak.LIFECYCLE))
    _, missing = soak.coverage(path)
    assert missing == []
    assert "NOT reached this run" not in soak.render(path)


def test_an_unknown_event_does_not_appear_in_the_table(tmp_path):
    # The table is the lifecycle, not whatever the journal happens to hold. A new
    # event type is added here deliberately or it is not claimed as coverage.
    path = _journal(tmp_path, {"event": "something_new", "run": "r1"})
    assert "something_new" not in soak.render(path)


# --- whose run is this? -------------------------------------------------------


def test_runs_are_listed_once_each_in_the_order_they_appear(tmp_path):
    path = _journal(tmp_path,
                    {"event": "cycle_start", "run": "r1"},
                    {"event": "cycle_start", "run": "r2"},
                    {"event": "proposal", "run": "r1"})
    assert soak.runs_in(path) == ["r1", "r2"]


def test_events_with_no_run_id_are_not_counted_as_a_run(tmp_path):
    path = _journal(tmp_path, {"event": "cycle_start"}, {"event": "proposal", "run": ""})
    assert soak.runs_in(path) == []


def test_two_runs_in_one_journal_are_announced_before_the_table(tmp_path):
    """The table counts events and cannot tell whose.

    Presented as one session, a soak that was really two — one of them a version
    behind — reads as clean coverage of code that never ran.
    """
    path = _journal(tmp_path,
                    {"event": "cycle_start", "run": "r1"},
                    {"event": "order", "run": "r2"})
    text = soak.render(path)
    assert "written by 2 runs" in text
    assert "r1, r2" in text
    assert text.index("written by 2 runs") < text.index("what this run reached")


def test_a_single_run_gets_no_warning(tmp_path):
    path = _journal(tmp_path, {"event": "cycle_start", "run": "r1"})
    assert "written by" not in soak.render(path)


# --- the closing-order line ---------------------------------------------------


def test_closing_orders_counts_only_closes_and_only_real_fill_prices(tmp_path):
    """The one question a stub broker cannot answer, which is why a soak exists.

    An opening order is not evidence about closing fills, and a close whose response
    carried no `filled_avg_price` is not evidence that the price came back.
    """
    path = _journal(tmp_path,
                    {"event": "order", "intent": "open", "filled_avg_price": "1.20"},
                    {"event": "order", "intent": "close", "filled_avg_price": "0.40"},
                    {"event": "order", "intent": "close", "filled_avg_price": ""},
                    {"event": "order", "intent": "close"})
    assert soak.closing_orders(path) == (3, 1)
    assert "3 submitted, 1 carried a fill price" in soak.render(path)


# --- the argv handed to the agent ---------------------------------------------


def test_the_journal_is_forwarded_to_the_agent_not_merely_reported_on():
    """The defect this function was extracted to make visible.

    Both sides defaulted to the same path, so the mismatch stayed invisible until
    someone passed --journal to keep a session's record separate: the agent went on
    writing the default file while the coverage read the requested one, and a soak
    that placed orders all day reported every event as never reached.
    """
    argv = soak.agent_argv(env="dev", journal="var/journal/session.jsonl",
                           submit=True, committee=None)
    assert "--journal" in argv
    assert argv[argv.index("--journal") + 1] == "var/journal/session.jsonl"


def test_a_soak_always_runs_to_the_close():
    assert "--until-close" in soak.agent_argv(env="dev", journal="j", submit=False,
                                              committee=None)


def test_nothing_is_submitted_unless_asked():
    assert "--submit" not in soak.agent_argv(env="dev", journal="j", submit=False,
                                             committee=None)
    assert "--submit" in soak.agent_argv(env="dev", journal="j", submit=True,
                                         committee=None)


@pytest.mark.parametrize("committee,expected", [
    (None, None),                    # whatever a real run would do — the point of a soak
    (True, "--committee"),
    (False, "--no-committee"),
])
def test_the_committee_is_only_forced_when_asked(committee, expected):
    argv = soak.agent_argv(env="dev", journal="j", submit=False, committee=committee)
    if expected is None:
        assert not any(a.endswith("committee") for a in argv)
    else:
        assert expected in argv
