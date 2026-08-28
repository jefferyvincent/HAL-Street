"""Run the agent across a whole session and report what the run actually exercised.

    ./start.sh soak -- --submit          # a live session, paper account
    ./start.sh soak -- --hours 2         # a shorter window
    ./start.sh soak                      # dry run: scans and proposes, submits nothing

`tests/agent/test_soak.py` covers the same lifecycle offline and runs in a second, so
this is not here to prove the code paths work. It is here for the two things a stub
broker cannot answer:

  · whether Alpaca actually fills a closing multi-leg order, and how long it takes
  · whether `filled_avg_price` on a real order means what we read it to mean

Everything else is bookkeeping, and it lives in `halstreet.agent.hippocampus.soak`: run the
scheduler for a window, then read the journal back and say which lifecycle events
fired and which did not.
"""

from __future__ import annotations

import argparse
import asyncio

from halstreet import paths
from halstreet.agent.hippocampus import soak


async def main_async(args: argparse.Namespace) -> int:
    if args.report_only:
        print(soak.render(args.journal))
        return 0

    from halstreet.agent.run import build_parser as agent_parser
    from halstreet.agent.run import main_async as run_agent

    argv = soak.agent_argv(env=args.env, journal=args.journal,
                           submit=args.submit, committee=args.committee)
    print(f"soak: {' '.join(argv)}  (journal {args.journal})")
    code = await run_agent(agent_parser().parse_args(argv))
    print(soak.render(args.journal))
    return code


def build_parser() -> argparse.ArgumentParser:
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
    return p


def resolve(args: argparse.Namespace) -> argparse.Namespace:
    if args.journal is None:
        args.journal = str(paths.for_env(args.env)[0])
    return args


def main() -> int:
    return asyncio.run(main_async(resolve(build_parser().parse_args())))


if __name__ == "__main__":
    raise SystemExit(main())
