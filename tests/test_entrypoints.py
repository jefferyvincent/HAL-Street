"""`start.sh` and `install.sh` — the two files a person meets before any Python runs.

Both had the same defect in different forms: a check that could not tell a broken
environment from a missing feature, and said the wrong one confidently.

`start.sh` reported "The agent loop isn't built yet (halstreet.agent.run does not
exist)" on a machine where it plainly did exist, because the import was run with
stderr discarded and *any* failure printed that line. `install.sh` reused a stale
virtualenv and surfaced the mismatch as "No module named pip".

A diagnostic that can state something false about the codebase is worse than none:
the first sends a reader through the source looking for code that is already there,
and the second hides a one-command fix behind a puzzle.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "start.sh"
INSTALL = ROOT / "install.sh"


@pytest.mark.parametrize("script", [START, INSTALL])
def test_the_shell_entrypoints_parse(script):
    # They are the first thing that runs and the last thing anything tests.
    # A fixed argv with an absolute interpreter; nothing here comes from input.
    bash = shutil.which("bash") or "/bin/bash"
    done = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)  # noqa: S603
    assert done.returncode == 0, done.stderr


def test_start_never_claims_a_built_feature_is_unbuilt():
    """The exact false statement, so it cannot come back.

    The loop, the panel, the report and the soak all exist and all have tests. Any
    "isn't built yet" branch left in here is scaffolding outliving its subject, and
    the failure mode is not a stale message — it is a true-sounding lie told to
    whoever is trying to run the thing.
    """
    # Executable lines only. The comment above the replacement quotes the old
    # message in order to explain why it went — the same reason the write-up's gate
    # count check reads claims rather than words. A comment cannot mislead a user;
    # only something that prints can.
    code = "\n".join(line for line in START.read_text().splitlines()
                      if not line.strip().startswith("#"))
    for phrase in ("isn't built yet", "does not exist", "not implemented yet"):
        assert phrase not in code, f"start.sh still tells a user something {phrase!r}"


def test_no_import_check_discards_the_error_it_is_checking_for():
    """`2>/dev/null` on an import check is what made the message wrong.

    With the error thrown away there is nothing left to distinguish "the package is
    not installed" from "a dependency is missing" from "the module has a syntax
    error", so whatever the branch prints is a guess presented as a diagnosis.
    """
    for line in START.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "-c 'import" in stripped or '-c "import' in stripped:
            assert "2>/dev/null" not in stripped, \
                f"an import check that hides its own error: {stripped}"


def test_start_checks_the_environment_once_for_every_mode():
    # Every mode shells into .venv/bin/python, so a venv that cannot import the
    # package fails a different way for each one. Checked before the dispatch.
    text = START.read_text()
    check = text.index("cannot import halstreet")
    dispatch = text.index('case "$MODE" in')
    assert check < dispatch, "the environment check must run before the mode dispatch"


def test_the_failure_names_the_command_that_fixes_it():
    text = START.read_text()
    section = text[text.index("cannot import halstreet"):text.index('case "$MODE" in')]
    assert "./install.sh" in section
    assert "No module named" in section, "it must distinguish the kinds of failure"


def test_install_verifies_a_virtualenv_before_reusing_it():
    """A venv is not portable, and `-x .venv/bin/python` does not know that.

    It goes stale when the repo moves between machines, when the distro upgrades
    Python underneath it, or when it was built by a different interpreter than the
    one on PATH today — all of which used to surface as a missing pip module three
    lines later.
    """
    text = INSTALL.read_text()
    assert "venv_ok()" in text, "no health check is defined"
    # Defined is not enough — it has to gate the reuse. A mutation that changed
    # `elif venv_ok; then` to `elif true; then` left the function sitting there,
    # unreferenced, and an earlier version of this test passed it happily.
    assert re.search(r"^\s*(el)?if\s+venv_ok\s*;", text, re.MULTILINE), \
        "venv_ok is defined but nothing calls it"
    reuse = text.index("Reusing existing .venv")
    assert text.index("venv_ok()") < reuse, "the check must exist before the reuse"
    # It must actually compare versions, not merely run the interpreter.
    assert "$PYMM" in text[text.index("venv_ok()"):reuse]
    # And a failed check must rebuild rather than carry on.
    after = text[reuse:text.index("rm -rf .venv")]
    assert "unusable" in after, "a failing check must say so"


def test_install_refuses_to_delete_a_virtualenv_that_is_in_use():
    """Rebuilding kills a soak mid-session, or the panel, or a scheduled agent.

    The guard checks argv[0] rather than the whole command line: these are launched
    relative (`.venv/bin/python scripts/soak.py`), so a pattern anchored to $PWD
    matches nothing, while `pgrep -f .venv/bin/python` matches every shell whose
    command *text* mentions the path — the installer's own subshell included.
    """
    text = INSTALL.read_text()
    guard = text[text.index("rm -rf .venv") - 2000:text.index("rm -rf .venv")]
    assert "cmdline" in guard, "the guard must read argv[0], not match a command line"
    assert "/proc/$pid/cwd" in guard or "$proc/cwd" in guard, \
        "and confirm the process belongs to this checkout"
    assert "exit 1" in guard, "it must stop, not warn and carry on"


def test_every_mode_start_advertises_is_one_it_can_dispatch():
    """The help text and the dispatch must agree.

    A mode named in the usage block and missing from the `case` is the same class of
    lie as the one this file exists for: it sends someone to type a command that
    cannot work.
    """
    text = START.read_text()
    advertised = set(re.findall(r"^#\s+\./start\.sh (\w+)", text, re.MULTILINE))
    body = text[text.index('case "$MODE" in'):]
    dispatched = set(re.findall(r"^\s{2}(\w+)\)", body, re.MULTILINE))
    assert advertised, "the usage block names no modes"
    assert advertised <= dispatched, f"advertised but undispatchable: {advertised - dispatched}"

    # And each branch must actually run something. A phrase list ("isn't built yet",
    # "not implemented") is the wrong shape for this: it catches the wording that
    # happened to be used and nothing else — a mutation reading "is not built yet"
    # walked straight through an earlier version of this test. What is checkable is
    # the property itself, which is that every advertised mode reaches a command.
    # Every *dispatched* mode, not just the advertised ones. `loop` is the default —
    # bare `./start.sh` — so it never appears in the usage block, and an earlier
    # version of this check iterated the advertised set and skipped precisely the
    # branch that carried the bug. Three separate refuse-to-dispatch mutations walked
    # through it untouched.
    for mode in sorted(dispatched):
        branch = re.search(rf"^\s{{2}}{mode}\)(.*?)^\s{{4}};;", body, re.MULTILINE | re.DOTALL)
        assert branch, f"{mode} has no branch body"
        assert re.search(r"^\s*run\s+\S", branch.group(1), re.MULTILINE), \
            f"./start.sh {mode} dispatches but its branch runs nothing"


def test_the_in_use_guard_survives_a_process_exiting_while_it_looks():
    """The guard walks every PID on the machine, so this race is not exotic.

    A process that exits between the `/proc/[0-9]*` glob and the read leaves a path
    that no longer exists. The read was written as

        argv0="$(tr '\\0' '\\n' < "$proc/cmdline" 2>/dev/null | head -1)"

    where `2>/dev/null` silences *tr*, and the thing that fails is the **shell's own
    input redirection** — reported by bash, not by tr, and fatal under `set -e`. Ports
    8792-8798 held six panels for a day and a half; clearing them and re-running was
    enough to lose the race, and the installer died with

        ./install.sh: line 106: /proc/3878315/cmdline: No such file or directory

    on a machine where nothing was wrong. Worse than a false refusal: the message
    names a PID the reader cannot look up, so it describes a state that no longer
    exists — Constitution VII.

    The real line is extracted and executed here rather than pattern-matched, because
    what matters is that it *survives*, not how it is spelled.
    """
    import re

    line = next((ln for ln in INSTALL.read_text().splitlines()
                 if "cmdline" in ln and "argv0=" in ln), None)
    assert line, "the guard no longer reads cmdline this way — this test has drifted"

    # `set -e` and friends exactly as install.sh runs, against a path that is gone.
    # Absolute interpreter and a script built only from this repo's own file — the
    # same shape, and the same reason, as `test_the_shell_entrypoints_parse` above.
    script = f'set -euo pipefail\nproc=/proc/nonexistent-{"0" * 6}\n{line.strip()}\necho SURVIVED'
    bash = shutil.which("bash") or "/bin/bash"
    done = subprocess.run([bash, "-c", script], capture_output=True, text=True)  # noqa: S603

    assert "SURVIVED" in done.stdout, (
        f"the guard aborts when a process exits mid-walk: {done.stderr.strip()}")
    assert not re.search(r"No such file", done.stderr), (
        f"and it must not print the vanished path: {done.stderr.strip()}")
