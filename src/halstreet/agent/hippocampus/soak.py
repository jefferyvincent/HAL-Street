"""What a soak run actually exercised, read back out of its journal.

The soak drives the real agent against a real paper account for a session; this module
is the part that reads the record afterwards and says which lifecycle events fired and
which did not. A soak that reports "no errors" without saying what it never reached
proves very little — the coverage table at the end is the point of the exercise.

Pure functions over a journal path, so `tests/agent/test_soak_coverage.py` can write
five events to a temp file and assert on the answer. The session itself, the argv it
builds for the agent and the printing all live in `halstreet.cli.soak`.
"""

from __future__ import annotations

from collections import Counter

from halstreet.telemetry.journal import Journal

#: The events that only a sequence can produce. These are the reason to run a soak at
#: all, and each one is a claim in the write-up that would otherwise be untested.
LIFECYCLE = {
    "cycle_start": "a scan began",
    "market_view": "bias and regime computed from bars",
    "candidates": "structures built and ranked",
    "proposal": "the model answered",
    "committee": "catalyst, debate and judge ran",
    "gate_decision": "the chain evaluated a proposal",
    "order": "an order was submitted",
    "fill_correction": "a limit was replaced by a real fill",
    "exit_decision": "an open structure was judged",
    "divergence": "the ledger and the broker disagreed",
    "halt": "the breaker latched",
    "error": "something failed and was recorded",
}


def coverage(journal_path: str) -> tuple[Counter, list[str]]:
    seen = Counter(e.get("event") for e in Journal.open(journal_path).read())
    missing = [name for name in LIFECYCLE if not seen.get(name)]
    return seen, missing


def runs_in(journal_path: str) -> list[str]:
    """Distinct agent runs that wrote to this file, oldest first."""
    out: list[str] = []
    for event in Journal.open(journal_path).read():
        run = str(event.get("run") or "")
        if run and run not in out:
            out.append(run)
    return out


def closing_orders(journal_path: str) -> tuple[int, int]:
    """(submitted, carried a fill price) — the one thing a stub broker cannot answer."""
    closes = [e for e in Journal.open(journal_path).read()
              if e.get("event") == "order" and e.get("intent") == "close"]
    filled = [e for e in closes if e.get("filled_avg_price") not in (None, "")]
    return len(closes), len(filled)


def render(journal_path: str) -> str:
    """The coverage report as a string, warnings included."""
    seen, missing = coverage(journal_path)
    runs = runs_in(journal_path)
    out: list[str] = []

    if len(runs) > 1:
        # The table below counts events, and it cannot tell whose. Two soaks once
        # shared a journal for an hour — one of them a version behind — and the
        # coverage read as a single clean session. A soak whose only output is this
        # table must not present two runs as one.
        out += [
            f"\n!! this journal was written by {len(runs)} runs: {', '.join(runs)}",
            "   The table below counts all of them together. Re-run against a fresh",
            "   --journal for a session you intend to cite.",
        ]

    width = max(len(n) for n in LIFECYCLE)
    out.append("\n--- what this run reached ---")
    for name, what in LIFECYCLE.items():
        n = seen.get(name, 0)
        mark = "  " if n else "!!"
        out.append(f"  {mark} {name.ljust(width)}  {n:>4}   {what}")

    submitted, filled = closing_orders(journal_path)
    out.append(f"\n  closing orders: {submitted} submitted, "
               f"{filled} carried a fill price in the response")

    if missing:
        # Not a failure. Some of these only fire on a losing day or a broken book, and
        # a session that never diverged is a session that went well. Named anyway,
        # because "the soak passed" must not be read as "everything was exercised".
        out.append("\n  NOT reached this run: " + ", ".join(missing))
        out.append("  Those paths remain covered only by tests/agent/test_soak.py.")
    return "\n".join(out)


def agent_argv(*, env: str, journal: str, submit: bool, committee: bool | None) -> list[str]:
    """The argv the soak hands the agent.

    Forwarded, not merely reported on. `--journal` defaulted to the same path on both
    sides, so a mismatch was invisible until someone passed one to keep a session's
    record separate: the agent went on writing the default file while the coverage
    read the one that had been asked for. A soak that placed orders all day then
    reported every lifecycle event as never reached — or, worse, reported a previous
    run's coverage as if it were this one's.
    """
    argv = ["--until-close", "--env", env, "--journal", journal]
    if submit:
        argv.append("--submit")
    if committee is not None:
        argv.append("--committee" if committee else "--no-committee")
    return argv
