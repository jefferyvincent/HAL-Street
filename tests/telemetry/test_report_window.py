"""Which records a report is computed over, and what it claims about them.

Two defects, both in the judged deliverable rather than in the trading path, and both
of the kind that produce a confident wrong number rather than an error.

The Results section of `docs/WRITEUP.md` opens by promising the figures are generated
from the journal rather than typed. A judge reads that and stops checking, which is
exactly why the generator must not be able to state something the data does not say.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet import paths
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.telemetry import pnl
from halstreet.telemetry.journal import Journal


def _journal(tmp_path, *records, name="run.jsonl"):
    j = Journal.open(tmp_path / name)
    for event, fields in records:
        j.write(event, **fields)
    return j


def _cycles(*dates, equity="100000"):
    return [("cycle_start", {"underlying": "SPY", "session_date": d,
                             "equity": Decimal(equity)}) for d in dates]


# --- the account the record belongs to ------------------------------------------------

def test_the_two_accounts_do_not_share_a_journal_or_a_ledger():
    """The dev/comp split was, until now, only about which credentials were read.

    Both accounts appended to the same `run.jsonl` and the same `ledger.json`, and
    every figure the report produces is computed over whole files. So a judged run
    would have folded a rehearsal into its own numbers silently — and the worst line
    is `Equity: X -> Y`, which would have taken X from a dev cycle and Y from the
    competition account: two different accounts averaged into one claim.

    `config.py` already makes the credentials structurally separate rather than
    merely discouraged. This is that argument applied to the record.
    """
    dev = paths.for_env("dev")
    comp = paths.for_env("comp")
    assert not set(dev) & set(comp), "a comp run must not open a file a dev run opens"
    assert all("comp" in p.name for p in comp)


def test_dev_keeps_the_original_filenames():
    # Existing history stays where it is; nothing has to be migrated.
    assert paths.for_env("dev") == (paths.RUN_JOURNAL, paths.LEDGER, paths.CIRCUIT)


@pytest.mark.parametrize("env", ["dev", "comp"])
def test_the_agents_paths_follow_the_account_unless_told_otherwise(env):
    from halstreet.agent.run import build_parser, resolve_paths
    args = resolve_paths(build_parser().parse_args(["--env", env]))
    want = paths.for_env(env)
    assert (args.journal, args.ledger, args.breaker) == tuple(str(p) for p in want)


def test_an_explicit_path_still_wins_and_only_for_itself():
    # `default=None` is what makes "unset" distinguishable from "set to the dev path".
    # With a literal default a comp run could not be given its own files without the
    # caller naming all three every time.
    from halstreet.agent.run import build_parser, resolve_paths
    args = resolve_paths(build_parser().parse_args(
        ["--env", "comp", "--journal", "/somewhere/else.jsonl"]))
    assert args.journal == "/somewhere/else.jsonl"
    assert args.ledger == str(paths.for_env("comp")[1]), "the others still follow --env"


# --- the window the report covers ---------------------------------------------------------

def test_the_window_is_measured_from_the_journal_not_asserted_by_the_caller(tmp_path):
    """`--window` was a label, interpolated into "Window traded:" and filtering nothing.

    Every figure below that line is computed over the whole file, so the flag let a
    judged window's dates sit above numbers covering every session ever recorded —
    stated as fact, in the one section that promises its numbers are generated.
    """
    journal = _journal(tmp_path, *_cycles("2026-09-01", "2026-09-02", "2026-09-03"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    assert report.sessions == ("2026-09-01", "2026-09-02", "2026-09-03")
    assert report.window == "2026-09-01 to 2026-09-03"
    assert "2026-09-01 to 2026-09-03" in pnl.writeup_results(report)


def test_a_single_session_is_stated_as_one_date_not_a_range(tmp_path):
    journal = _journal(tmp_path, *_cycles("2026-09-01", "2026-09-01"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    assert report.window == "2026-09-01"


def test_a_label_that_contradicts_the_data_is_reported_not_printed_as_fact(tmp_path):
    # The failure this is for: the numbers cover August, the label claims September,
    # and the old code printed the label.
    journal = _journal(tmp_path, *_cycles("2026-08-26"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    line = pnl.writeup_results(report, window="2026-09-01 to 2026-09-30").splitlines()[0]
    assert "2026-08-26" in line
    assert "does not match" in line
    assert line.index("2026-08-26") < line.index("2026-09-01"), \
        "the measured window leads; the label is the correction"


def test_a_label_consistent_with_the_data_is_kept_as_a_description(tmp_path):
    # It is allowed to say something the dates cannot: which account, which rehearsal.
    journal = _journal(tmp_path, *_cycles("2026-08-26"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    line = pnl.writeup_results(report, window="dev rehearsal, 2026-08-26").splitlines()[0]
    assert "dev rehearsal" in line and "does not match" not in line


def test_a_label_that_merely_restates_the_dates_is_not_repeated(tmp_path):
    journal = _journal(tmp_path, *_cycles("2026-08-26"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    line = pnl.writeup_results(report, window="2026-08-26").splitlines()[0]
    assert line.count("2026-08-26") == 1


def test_a_label_with_no_dates_in_it_makes_no_checkable_claim(tmp_path):
    # "week one" asserts nothing a journal can contradict. The check is for a label
    # naming dates the data does not contain, not for parsing English.
    journal = _journal(tmp_path, *_cycles("2026-08-26"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    assert "does not match" not in pnl.writeup_results(report, window="week one")


def test_an_overlapping_label_is_accepted(tmp_path):
    # A judged window stated as a month, with the agent having traded three days of
    # it, is a true description. Only a disjoint claim is wrong.
    journal = _journal(tmp_path, *_cycles("2026-09-10", "2026-09-11"))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"), journal)
    assert "does not match" not in pnl.writeup_results(
        report, window="2026-09-01 to 2026-09-30")


def test_an_empty_journal_states_no_window_rather_than_a_false_one(tmp_path):
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"),
                       Journal.open(tmp_path / "empty.jsonl"))
    assert report.window == ""
    assert "_not stated_" in pnl.writeup_results(report)


def test_the_session_date_is_preferred_over_the_timestamp(tmp_path):
    """The exchange's date, not the host's, when the record carries one.

    They differ for a cycle running after 20:00 ET, when UTC has already rolled over
    — and a session attributed to the wrong day is how a window claim goes wrong by
    one at each end.
    """
    journal = _journal(tmp_path, ("cycle_start", {
        "underlying": "SPY", "session_date": "2026-09-01",
        "ts": "2026-09-02T01:30:00+00:00", "equity": Decimal(100000)}))
    assert pnl.sessions_covered(journal) == ("2026-09-01",)


def test_a_record_written_before_session_date_existed_still_dates_correctly(tmp_path):
    journal = _journal(tmp_path, ("cycle_start", {"underlying": "SPY",
                                                  "equity": Decimal(100000)}))
    covered = pnl.sessions_covered(journal)
    assert len(covered) == 1 and len(covered[0]) == 10


# --- whose figures are these -----------------------------------------------------

def test_the_results_block_states_when_more_than_one_run_is_behind_it(tmp_path):
    """A restart mid-window is ordinary. Two agents at once is not.

    Both look identical in a file that does not record who wrote each line, and the
    difference matters in the one section a judge reads first.
    """
    from halstreet.telemetry.journal import Journal

    a = Journal.open(tmp_path / "run.jsonl")
    b = Journal.open(tmp_path / "run.jsonl")
    for j in (a, b):
        j.write("cycle_start", underlying="SPY", session_date="2026-09-01",
                equity=Decimal(100000))

    report = pnl.build(Ledger.load(tmp_path / "ledger.json"),
                       Journal.open(tmp_path / "run.jsonl"))
    assert report.runs == (a.run_id, b.run_id)
    assert "Agent runs in this window:** 2" in pnl.writeup_results(report)


def test_a_single_run_is_not_announced(tmp_path):
    # Stated only when it is worth stating; otherwise it is a line of noise above
    # the numbers a judge came to read.
    from halstreet.telemetry.journal import Journal

    j = Journal.open(tmp_path / "run.jsonl")
    j.write("cycle_start", underlying="SPY", session_date="2026-09-01",
            equity=Decimal(100000))
    report = pnl.build(Ledger.load(tmp_path / "ledger.json"),
                       Journal.open(tmp_path / "run.jsonl"))
    assert len(report.runs) == 1
    assert "Agent runs in this window" not in pnl.writeup_results(report)
