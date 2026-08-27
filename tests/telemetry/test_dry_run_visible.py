"""Telling a rehearsal from a trade, without correlating two records.

A dry run runs every gate and writes every record a live cycle writes, then stops
before submission. That is the right design — it is what makes a rehearsal worth
anything — and it means its journal entries are indistinguishable from a live run's.

Which is how a REJECTED written by a dry run came to be read as the broker refusing an
order. Nothing had been submitted; nothing had even been attempted. The panel simply
had no way to say so, because `dry_run` was recorded on `cycle_start` and shown
nowhere.

The unknown case has its own value throughout. A dry run that looks live invites
panic about an order that was never sent; a live run that looks like a rehearsal is
worse, and folding "we do not know" into the safe-looking one produces exactly that.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halstreet.telemetry.server import _armed, _decisions_with_positions


def at(seconds_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat()


def cycle(dry: bool | None = None, **over) -> dict:
    base = {"event": "cycle_start", "underlying": "SPY", "ts": at(60)}
    if dry is not None:
        base["dry_run"] = dry
    return {**base, **over}


def decision(**over) -> dict:
    return {"event": "gate_decision", "underlying": "SPY", "ts": at(30),
            "structure": "SPY 756/752 put credit spread", "approved": False,
            "rejected_by": ["portfolio-greek-bounds"], "gates": [], **over}


# --- is the agent armed --------------------------------------------------------

def test_a_live_cycle_reads_as_armed():
    assert _armed([cycle(dry=False)]) is True


def test_a_rehearsal_reads_as_not_armed():
    assert _armed([cycle(dry=True)]) is False


def test_nothing_scanned_yet_is_neither():
    """Not the same as a rehearsal, and must not render as one."""
    assert _armed([]) is None
    assert _armed([{"event": "session", "ts": at(10)}]) is None


def test_a_journal_from_before_the_flag_says_it_does_not_know():
    """Rather than guessing, in either direction."""
    assert _armed([cycle()]) is None


def test_the_most_recent_cycle_wins():
    """A rehearsal after a live run means the agent is no longer armed, and the
    chrome must follow rather than remembering the morning."""
    assert _armed([cycle(dry=False, ts=at(600)), cycle(dry=True, ts=at(60))]) is False
    assert _armed([cycle(dry=True, ts=at(600)), cycle(dry=False, ts=at(60))]) is True


def test_a_cycle_without_the_flag_does_not_erase_an_earlier_one():
    """`"dry_run" in event` rather than `.get`, so a record that simply does not carry
    the field is skipped instead of reading as False — which would have said ARMED."""
    assert _armed([cycle(dry=True, ts=at(600)), cycle(ts=at(60))]) is False


# --- the decision row ----------------------------------------------------------

def test_a_stamped_decision_carries_its_own_answer():
    """The agent records it on the decision now, so one record explains itself."""
    (row,) = _decisions_with_positions([decision(dry_run=True)])
    assert row["dry_run"] is True


def test_an_unstamped_decision_is_recovered_from_its_cycle():
    """Covers every record written before the flag existed — which is the whole
    journal this was found in."""
    (row,) = _decisions_with_positions([cycle(dry=True), decision()])
    assert row["dry_run"] is True


def test_a_stamped_decision_beats_the_cycle_around_it():
    """The record is the more direct evidence. If the two ever disagree, correlation
    is the one that was guessing."""
    (row,) = _decisions_with_positions([cycle(dry=False), decision(dry_run=True)])
    assert row["dry_run"] is True


def test_a_decision_with_no_recoverable_cycle_says_it_does_not_know():
    (row,) = _decisions_with_positions([decision()])
    assert row["dry_run"] is None


def test_each_decision_takes_the_cycle_it_belongs_to():
    """Not the last one in the file. A run that switches modes would otherwise
    relabel its whole history every time it changed."""
    rows = _decisions_with_positions([
        cycle(dry=False, ts=at(900)), decision(ts=at(880), structure="live one"),
        cycle(dry=True, ts=at(120)), decision(ts=at(100), structure="rehearsed one"),
    ])
    by = {r["structure"]: r["dry_run"] for r in rows}
    assert by == {"live one": False, "rehearsed one": True}


def test_a_decision_before_any_cycle_is_unknown_not_live():
    rows = _decisions_with_positions([decision(ts=at(900), structure="orphan"),
                                      cycle(dry=False, ts=at(120))])
    assert rows[0]["dry_run"] is None


@pytest.mark.parametrize("approved", [True, False])
def test_both_verdicts_are_marked(approved):
    """An APPROVED that submitted nothing is the more dangerous of the two, and a
    REJECTED that never reached a broker is the one that actually caused this."""
    (row,) = _decisions_with_positions([cycle(dry=True), decision(approved=approved)])
    assert row["dry_run"] is True


def test_a_rehearsed_approval_still_links_to_no_position():
    """It never opened one. This was already true and is worth keeping true beside
    the new flag — the two say the same thing from different directions."""
    (row,) = _decisions_with_positions([cycle(dry=True), decision(approved=True)])
    assert row["structure_id"] is None


# --- the agent writes it -------------------------------------------------------

def test_the_agent_stamps_its_own_mode_on_the_decision():
    from pathlib import Path

    source = Path("src/halstreet/agent/loop.py").read_text()
    assert "self.journal.decision(decision, dry_run=self.dry_run)" in source
