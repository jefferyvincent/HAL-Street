"""Print or export the run's results.

    ./start.sh report                      # summary to stdout
    ./start.sh report -- --export out/     # summary.json, positions.csv, results.txt

Marks open positions against live quotes when the broker is reachable, so unrealized
P&L is real rather than omitted. If it is not reachable the report still prints —
realized P&L and every gate count come from files on disk and need no network.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

from halstreet import paths
from halstreet.agent.ledger import Ledger
from halstreet.agent.manager import mark_structure
from halstreet.config import ConfigError, load_env
from halstreet.execution.mcp_client import AlpacaMCP, MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError
from halstreet.telemetry import pnl
from halstreet.telemetry.journal import Journal


async def live_marks(env: str, ledger: Ledger) -> dict[str, Decimal]:
    """Current net mark per open structure, or {} if quotes are unavailable."""
    open_structures = ledger.open_structures
    if not open_structures:
        return {}
    symbols = sorted({s for st in open_structures for s in st.legs})
    try:
        client = AlpacaMCP.from_env(env)
        payload = await client.get_option_snapshot(symbols)
    except (MCPError, LiveEnvironmentError, ConfigError) as exc:
        print(f"note: could not fetch quotes ({exc}); unrealized P&L omitted\n",
              file=sys.stderr)
        return {}
    chain = payload.get("snapshots", payload) if isinstance(payload, dict) else {}

    out: dict[str, Decimal] = {}
    for structure in open_structures:
        mark = mark_structure(structure, chain)
        if mark.complete:
            out[structure.structure_id] = mark.value
    return out


async def main_async(args: argparse.Namespace) -> int:
    try:
        load_env(args.env, required=False)
    except ConfigError as exc:
        print(f"config: {exc}")
        return 1

    ledger = Ledger.load(args.ledger)
    journal = Journal.open(args.journal)
    marks = {} if args.offline else await live_marks(args.env, ledger)

    report = pnl.build(ledger, journal, marks=marks)
    if args.writeup:
        # Paste-ready. The last section of docs/WRITEUP.md is the one a judge reads
        # first and the one most likely to be mistyped from a scrolled terminal.
        print(pnl.writeup_results(report, window=args.window))
        return 0
    print(pnl.render(report))

    if args.export:
        paths = pnl.write_exports(report, args.export)
        print("\nwrote:")
        for label, path in paths.items():
            print(f"  {label:5} {path}")
    return 0


def main() -> int:
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
    args = p.parse_args()
    journal, ledger, _ = paths.for_env(args.env)
    if args.journal is None:
        args.journal = str(journal)
    if args.ledger is None:
        args.ledger = str(ledger)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
