"""`scripts/soak.py` — the harness, not the agent it drives.

Thin enough to look obviously correct, which is why the one thing it does wrong went
unnoticed: it reported on a journal it had not asked the agent to write.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "soak_script", Path(__file__).resolve().parents[1] / "scripts" / "soak.py")
soak = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(soak)


def _argv(**over):
    """The argv the harness builds for the agent, without running anything."""
    args = argparse.Namespace(env="dev", submit=False, committee=None,
                              journal="var/journal/run.jsonl", report_only=False)
    for k, v in over.items():
        setattr(args, k, v)

    captured = {}

    async def fake_run(parsed):
        captured["parsed"] = parsed
        return 0

    from halstreet.agent import run as run_mod
    real_main, real_report = run_mod.main_async, soak.report
    run_mod.main_async = fake_run
    soak.report = lambda path: captured.setdefault("reported", path) and 0
    try:
        asyncio.run(soak.main_async(args))
    finally:
        run_mod.main_async, soak.report = real_main, real_report
    return captured


def test_the_agent_writes_the_journal_the_report_reads(tmp_path):
    """The bug: `--journal` was reported on and never forwarded.

    Both defaulted to the same path, so the mismatch was invisible until someone
    passed the flag to keep a session's record separate. Then the agent went on
    writing `var/journal/run.jsonl` while `report` read the file that had been asked
    for — and a soak that placed orders all day printed every lifecycle event as
    never reached. The failure mode is worse than an error: with a file left over
    from an earlier run, it reports that run's coverage as if it were this one's.
    """
    asked_for = str(tmp_path / "session.jsonl")
    got = _argv(journal=asked_for)
    assert got["parsed"].journal == asked_for, "the agent must write it"
    assert got["reported"] == asked_for, "the report must read it"


def test_the_default_is_still_the_real_journal():
    got = _argv()
    assert got["parsed"].journal == got["reported"] == "var/journal/run.jsonl"


def test_a_soak_always_runs_to_the_close():
    # A soak that stopped after one cycle would not reach the events it exists for:
    # a fill correction, an exit decision and a divergence all need a *later* cycle.
    assert _argv()["parsed"].until_close is True


@pytest.mark.parametrize(("flag", "want"), [(None, None), (True, True), (False, False)])
def test_the_committee_choice_is_passed_through_in_all_three_states(flag, want):
    # Including "said nothing", which must reach the agent as "said nothing" so the
    # environment decides. A soak is meant to exercise what a real run would do.
    assert _argv(committee=flag)["parsed"].committee is want


def test_submission_is_off_unless_asked_for():
    assert _argv().get("parsed").submit is False
    assert _argv(submit=True)["parsed"].submit is True


def test_every_lifecycle_event_the_report_names_is_one_the_agent_writes():
    """The coverage table is only meaningful if its names match the journal's.

    A typo here reads as "never reached" forever, which is indistinguishable from the
    thing the soak exists to detect — and the table is the soak's entire output.

    The AST rather than a grep: two of these events are written in multi-line calls
    with the name on its own line, and a line-oriented search reported them missing.
    """
    import ast

    written: set[str] = set()
    for path in Path("src/halstreet").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in ("write", "error"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                written.add(node.args[0].value)
    # `error` and the other named helpers write a fixed event name of their own.
    from halstreet.telemetry.journal import Journal
    written |= {m for m in dir(Journal) if not m.startswith("_")}

    unknown = {name for name in soak.LIFECYCLE if name not in written}
    assert not unknown, f"the report names events nothing writes: {unknown}"


def test_the_report_covers_the_events_that_only_a_sequence_produces():
    # The reason the harness exists. Each of these needs a *later* cycle than the one
    # that created its precondition, so no unit test reaches them and their absence
    # from a run is the finding.
    assert {"fill_correction", "exit_decision", "divergence", "halt"} <= set(soak.LIFECYCLE)
