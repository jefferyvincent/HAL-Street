"""Print or export the run's results.

    ./start.sh report                      # summary to stdout
    ./start.sh report -- --export out/     # summary.json, positions.csv, results.txt

Marks open positions against live quotes when the broker is reachable, so unrealized
P&L is real rather than omitted. If it is not reachable the report still prints —
realized P&L and every gate count come from files on disk and need no network — and
says so, because an omitted column and a zero column are different facts.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from halstreet import paths
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.config import ConfigError, load_env
from halstreet.telemetry import pnl
from halstreet.telemetry import report as report_mod
from halstreet.telemetry.journal import Journal


async def main_async(args: argparse.Namespace) -> int:
    try:
        load_env(args.env, required=False)
    except ConfigError as exc:
        print(f"config: {exc}")
        return 1

    ledger = Ledger.load(args.ledger)
    journal = Journal.open(args.journal)

    marks = {}
    if not args.offline:
        marks, note = await report_mod.live_marks(args.env, ledger)
        if note:
            print(f"note: {note}\n", file=sys.stderr)

    built = pnl.build(ledger, journal, marks=marks)
    if args.writeup:
        # Paste-ready. The last section of docs/WRITEUP.md is the one a judge reads
        # first and the one most likely to be mistyped from a scrolled terminal.
        print(pnl.writeup_results(built, window=args.window))
        return 0
    print(pnl.render(built))

    if args.export:
        written = pnl.write_exports(built, args.export)
        print("\nwrote:")
        for label, path in written.items():
            print(f"  {label:5} {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        # Defaults resolve through paths.py rather than being literals here, so
        # --help has to show them or nobody can tell where a run will write.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--env", default="dev", choices=["dev", "comp"])
    # Unset follows the account, like the agent's own paths — a report run with
    # --env comp that read the dev journal would put a rehearsal's numbers under a
    # judged window's heading, and say nothing about it.
    p.add_argument("--journal", default=None, help="append-only run journal "
                                                   "(default: follows --env)")
    p.add_argument("--ledger", default=None, help="structure ledger — what the broker "
                                                  "cannot tell us (default: follows --env)")
    p.add_argument("--export", default="", help="directory to write exports into")
    p.add_argument("--writeup", action="store_true",
                   help="emit the Results section of docs/WRITEUP.md as markdown")
    p.add_argument("--window", default="",
                   help="window description for --writeup, e.g. '2026-09-01 to 2026-09-30'")
    p.add_argument("--offline", action="store_true",
                   help="skip live quotes; realized P&L and gate counts only")
    return p


def resolve(args: argparse.Namespace) -> argparse.Namespace:
    """Fill the paths that follow --env. Separated so a test can check the wiring."""
    journal, ledger, _ = paths.for_env(args.env)
    if args.journal is None:
        args.journal = str(journal)
    if args.ledger is None:
        args.ledger = str(ledger)
    return args


def main() -> int:
    return asyncio.run(main_async(resolve(build_parser().parse_args())))


if __name__ == "__main__":
    sys.exit(main())
