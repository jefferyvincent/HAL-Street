"""One agent per journal.

Two agents ran against this account for three hours. Both wrote well-formed
records to the same file, neither errored, and the coverage table added them
together into one plausible session. The only symptom was a scan cadence
alternating 13m39s and 16m22s, which no single thirty-minute scheduler can
produce — and which nobody is watching for.

The stale one was the dangerous half: it was running code from before two fixes
made that morning, so half the journal was a previous version's behaviour
presented as the current agent's. A judged run is a claim about what *this* code
did.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from halstreet.agent.brainstem.lock import AlreadyRunning, JournalLock

ROOT = Path(__file__).resolve().parents[2]


def test_a_second_agent_cannot_take_a_held_journal(tmp_path):
    first = JournalLock(tmp_path / "run.jsonl")
    first.acquire()
    with pytest.raises(AlreadyRunning):
        JournalLock(tmp_path / "run.jsonl").acquire()
    first.release()


def test_the_lock_is_free_once_the_holder_lets_go(tmp_path):
    first = JournalLock(tmp_path / "run.jsonl")
    first.acquire()
    first.release()
    JournalLock(tmp_path / "run.jsonl").acquire()  # must not raise


def test_two_journals_do_not_block_each_other(tmp_path):
    # The dev and comp accounts have separate journals and are meant to be runnable
    # side by side; the lock is per record, not global.
    JournalLock(tmp_path / "run.jsonl").acquire()
    JournalLock(tmp_path / "comp-run.jsonl").acquire()  # must not raise


def test_the_refusal_says_who_holds_it(tmp_path):
    first = JournalLock(tmp_path / "run.jsonl")
    first.acquire()
    with pytest.raises(AlreadyRunning) as caught:
        JournalLock(tmp_path / "run.jsonl").acquire()
    message = str(caught.value)
    assert "Held by pid" in message
    # The hint that would have saved three hours: `ps` showed one process, and that
    # looked conclusive. It was a sandbox's private PID namespace.
    assert "PID namespace" in message
    first.release()


def test_the_lock_file_describes_its_owner_and_nobody_else(tmp_path):
    lock = JournalLock(tmp_path / "run.jsonl")
    lock.acquire()
    held = json.loads((tmp_path / "run.jsonl.lock").read_text())
    assert held["pid"] > 0 and held["started"]
    second = lock
    lock.release()

    second.release()


def test_the_lock_file_is_rewritten_and_not_written_over(tmp_path):
    """Truncated on every acquire, so it never carries a previous holder's tail.

    Without it a shorter record written over a longer one leaves trailing bytes, the
    JSON no longer parses, and the refusal degrades to "The holder left no details"
    — losing exactly the information someone needs at the moment two agents are
    fighting over an account.

    An earlier version of this test compared the pid to the previous holder's and
    passed either way, because both holders were this same pytest process.
    """
    path = tmp_path / "run.jsonl.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": 999999, "started": "x" * 4000, "argv0": "old"}))

    lock = JournalLock(tmp_path / "run.jsonl")
    lock.acquire()
    text = path.read_text()
    assert json.loads(text)["pid"] != 999999, "the previous record must be gone"
    assert text.count("\n") == 1, f"trailing bytes survived: {len(text)} chars"
    lock.release()


def test_a_dead_holder_leaves_nothing_to_clean_up(tmp_path):
    """The reason for `flock` over a pidfile.

    A pidfile has to be believed: after a kill -9 it names a process that is gone,
    and every reader then needs a liveness check that is itself racy. The kernel
    drops an flock when the holder dies, however it dies.
    """
    path = tmp_path / "run.jsonl"
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "from halstreet.agent.brainstem.lock import JournalLock\n"
        f"JournalLock({str(path)!r}).acquire()\n"
        "import os; os._exit(9)\n"
    )
    # sys.executable and a literal script; nothing here comes from input.
    subprocess.run([sys.executable, "-c", code], check=False, timeout=30)  # noqa: S603
    JournalLock(path).acquire()  # must not raise


def test_the_agent_refuses_to_start_against_a_held_journal(tmp_path):
    """End to end, and before the broker is opened.

    Checked first because the cost of the second agent is not that it fails — it
    is that it succeeds, quietly, against the same account.
    """
    held = JournalLock(tmp_path / "run.jsonl")
    held.acquire()
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "halstreet.agent.run", "--once", "--dry-run",
         "--journal", str(tmp_path / "run.jsonl"), "--universe", "SPY"],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )
    held.release()
    assert done.returncode == 1
    assert "BLOCKED" in done.stdout
    assert "already holds" in done.stdout
    assert not (tmp_path / "run.jsonl").exists(), "it must not have written a thing"
