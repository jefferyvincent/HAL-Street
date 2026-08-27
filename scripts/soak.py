#!/usr/bin/env python3
"""Run the agent across a whole session and report what the run actually exercised.

    ./start.sh soak -- --submit          # a live session, paper account
    ./start.sh soak -- --hours 2         # a shorter window
    ./start.sh soak                      # dry run: scans and proposes, submits nothing

`tests/agent/test_soak.py` covers the same lifecycle offline and runs in a second, so
this is not here to prove the code paths work. It is here for the two things a stub
broker cannot answer:

  · whether Alpaca actually fills a closing multi-leg order, and how long it takes
  · whether `filled_avg_price` on a real order means what we read it to mean

Everything else it does is bookkeeping: run the scheduler for a window, then read the
journal back and say which lifecycle events fired and which did not. A soak that
reports "no errors" without saying what it never reached is a soak that proves very
little — the point is the coverage line at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from halstreet import paths
from halstreet.telemetry.journal import Journal

#: The events that only a sequence can produce. These are the reason to run this at
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


def report(journal_path: str) -> int:
    seen, missing = coverage(journal_path)
    width = max(len(n) for n in LIFECYCLE)
    print("\n--- what this run reached ---")
    for name, what in LIFECYCLE.items():
        n = seen.get(name, 0)
        mark = "  " if n else "!!"
        print(f"  {mark} {name.ljust(width)}  {n:>4}   {what}")

    closes = [e for e in Journal.open(journal_path).read()
              if e.get("event") == "order" and e.get("intent") == "close"]
    filled = [e for e in closes if e.get("filled_avg_price") not in (None, "")]
    print(f"\n  closing orders: {len(closes)} submitted, "
          f"{len(filled)} carried a fill price in the response")

    if missing:
        # Not a failure. Some of these only fire on a losing day or a broken book, and
        # a session that never diverged is a session that went well. Named anyway,
        # because "the soak passed" must not be read as "everything was exercised".
        print("\n  NOT reached this run: " + ", ".join(missing))
        print("  Those paths remain covered only by tests/agent/test_soak.py.")
    return 0


async def main_async(args: argparse.Namespace) -> int:
    if args.report_only:
        return report(args.journal)

    from halstreet.agent.run import build_parser
    from halstreet.agent.run import main_async as run_agent

    # Forwarded, not merely reported on. These defaulted to the same path, so the
    # mismatch was invisible until someone passed --journal to keep a session's record
    # separate: the agent went on writing the default file and `report` read the one
    # that had been asked for, so a soak that placed orders all day reported every
    # lifecycle event as never reached — or, worse, reported a previous run's coverage
    # as if it were this one's.
    argv = ["--until-close", "--env", args.env, "--journal", args.journal]
    if args.submit:
        argv.append("--submit")
    if args.committee is not None:
        argv.append("--committee" if args.committee else "--no-committee")
    print(f"soak: {' '.join(argv)}  (journal {args.journal})")
    code = await run_agent(build_parser().parse_args(argv))
    report(args.journal)
    return code


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--env", default="dev", choices=["dev", "comp"])
    p.add_argument("--submit", action="store_true",
                   help="place approved orders (paper). Without it nothing is submitted "
                        "and the exit path is never reached.")
    p.add_argument("--committee", action=argparse.BooleanOptionalAction, default=None,
                   help="force the committee path on or off for this soak; the default "
                        "is whatever a real run would do, which is the point of a soak")
    p.add_argument("--journal", default=None,
                   help="run journal; defaults to the one for --env")
    p.add_argument("--report-only", action="store_true",
                   help="read an existing journal and print the coverage table")
    args = p.parse_args()
    if args.journal is None:
        args.journal = str(paths.for_env(args.env)[0])
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
