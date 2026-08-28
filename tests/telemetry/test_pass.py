"""The scan the agent is on, symbol by symbol.

The panel could say what the agent was doing *right now* and what it had decided
*eventually*, and nothing in between. A pass over six discovered names is a minute or
two of work in which five of them are already settled and one is mid-committee, and
none of that shape was anywhere — so watching the agent meant watching one amber word
and waiting for cards to appear.

`_pass` is the shape: one row per name in the current scan, and how far each got.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from halstreet.telemetry.server import _pass


def at(seconds_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


def start(sym: str, ago: float, spot: str = "100.00") -> dict:
    return {"event": "cycle_start", "ts": at(ago), "underlying": sym, "spot": spot}


def test_a_journal_with_no_scan_has_no_pass():
    assert _pass([]) is None
    assert _pass([{"event": "session", "ts": at(5), "state": "open"}]) is None


def test_one_row_per_name_in_the_order_they_were_scanned():
    """Scan order, not outcome order. It is a queue being worked through."""
    got = _pass([start("SPY", 60), start("QQQ", 40), start("NVDA", 20)])
    assert [r["underlying"] for r in got["rows"]] == ["SPY", "QQQ", "NVDA"]


def test_the_previous_scan_is_not_part_of_this_one():
    """Half an hour apart by default. Two passes in one table is two mornings."""
    got = _pass([start("SPY", 4000), start("QQQ", 30)])
    assert [r["underlying"] for r in got["rows"]] == ["QQQ"]


def test_a_name_that_built_nothing_says_so_and_stops_there():
    """The common case, and the one that reads as a hang. The loop returns before the
    committee when the menu is empty — no deliberation is missing, there was nothing
    to deliberate about."""
    got = _pass([start("SPY", 30),
                 {"event": "candidates", "ts": at(28), "underlying": "SPY", "count": 0}])
    row = got["rows"][0]
    assert row["menu"] == 0
    assert row["committee"] is None
    assert row["outcome"] == "no menu"


def test_a_considered_pass_is_not_a_failure():
    got = _pass([start("SPY", 30),
                 {"event": "candidates", "ts": at(28), "underlying": "SPY", "count": 6},
                 {"event": "proposal", "ts": at(10), "underlying": "SPY",
                  "ok": False, "passed": True, "rationale": "friction eats it"}])
    row = got["rows"][0]
    assert row["menu"] == 6
    assert row["outcome"] == "passed"
    assert row["gates"] is None, "nothing was proposed, so nothing was gated"


def test_a_gated_proposal_carries_the_verdict_and_who_refused_it():
    got = _pass([start("SPY", 40),
                 {"event": "candidates", "ts": at(38), "underlying": "SPY", "count": 6},
                 {"event": "proposal", "ts": at(20), "underlying": "SPY", "ok": True},
                 {"event": "gate_decision", "ts": at(10), "underlying": "SPY",
                  "approved": False, "rejected_by": ["max-loss", "correlated-exposure"]}])
    row = got["rows"][0]
    assert row["gates"] == "rejected"
    assert row["rejected_by"] == ["max-loss", "correlated-exposure"]
    assert row["outcome"] == "rejected"


def test_a_submitted_order_is_the_end_of_the_line():
    got = _pass([start("SPY", 40),
                 {"event": "candidates", "ts": at(38), "underlying": "SPY", "count": 6},
                 {"event": "proposal", "ts": at(30), "underlying": "SPY", "ok": True},
                 {"event": "gate_decision", "ts": at(20), "underlying": "SPY",
                  "approved": True, "rejected_by": []},
                 {"event": "order", "ts": at(10), "submitted": True,
                  "structure": "SPY 700/690 put credit spread"}])
    assert got["rows"][0]["outcome"] == "submitted"


def test_an_approved_rehearsal_is_not_a_submitted_order():
    """A dry run gates and journals exactly as a live cycle does and stops before
    submission. Reporting it as submitted is the failure the whole dry-run label
    exists to prevent."""
    got = _pass([start("SPY", 40),
                 {"event": "candidates", "ts": at(38), "underlying": "SPY", "count": 6},
                 {"event": "proposal", "ts": at(30), "underlying": "SPY", "ok": True},
                 {"event": "gate_decision", "ts": at(20), "underlying": "SPY",
                  "approved": True, "rejected_by": []},
                 {"event": "order", "ts": at(10), "submitted": False,
                  "error": "dry run", "structure": "SPY 700/690 put credit spread"}])
    assert got["rows"][0]["outcome"] == "approved"


def test_the_name_being_worked_on_is_the_one_still_running():
    """Everything before it in the queue is settled; it is the only live row."""
    got = _pass([start("SPY", 60),
                 {"event": "candidates", "ts": at(58), "underlying": "SPY", "count": 0},
                 start("NVDA", 30),
                 {"event": "candidates", "ts": at(25), "underlying": "NVDA", "count": 4}])
    assert [r["running"] for r in got["rows"]] == [False, True]
    assert got["rows"][1]["outcome"] == "running"


def test_a_finished_scan_has_nothing_running():
    got = _pass([start("SPY", 30),
                 {"event": "candidates", "ts": at(28), "underlying": "SPY", "count": 0},
                 {"event": "session", "ts": at(5), "state": "open"}])
    assert got["rows"][0]["running"] is False


def test_an_error_on_a_name_is_reported_rather_than_swallowed():
    """A broker that would not answer for one symbol is not the same as a quiet one."""
    got = _pass([start("SPY", 30),
                 {"event": "error", "ts": at(20), "underlying": "SPY",
                  "detail": "chain unavailable"}])
    row = got["rows"][0]
    assert row["outcome"] == "error"
    assert "chain unavailable" in (row["error"] or "")


def test_another_names_events_do_not_land_on_this_row():
    """One journal, one name at a time. This is the mistake that makes a table lie."""
    got = _pass([start("SPY", 60),
                 start("NVDA", 40),
                 {"event": "candidates", "ts": at(35), "underlying": "NVDA", "count": 9}])
    assert got["rows"][0]["menu"] is None
    assert got["rows"][1]["menu"] == 9
