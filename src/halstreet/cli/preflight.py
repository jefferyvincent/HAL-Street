"""Preflight checks for the judged competition run.

    ./start.sh preflight --env comp        # or: python -m halstreet.cli.preflight

Exits non-zero on any failure. Wire this into the scheduler so the agent physically
cannot start a judged run against a dirty account.

The checks themselves are in `halstreet.execution.preflight`, where they can be handed
a payload and asked what they conclude.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from halstreet.config import ConfigError, load_env
from halstreet.execution import preflight
from halstreet.execution.mcp_client import MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError


async def main_async(args: argparse.Namespace) -> int:
    try:
        load_env(args.env)
    except ConfigError as exc:
        print(f"  [FAIL] {exc}")
        return 1

    try:
        snap = await preflight.gather(args.env)
    except (LiveEnvironmentError, MCPError, ConfigError) as exc:
        print(f"  [FAIL] could not read the account: {exc}")
        return 1

    checks = preflight.run_checks(snap)
    print(preflight.render(checks))

    failed = preflight.failures(checks)
    if failed:
        print(f"\n{len(failed)} check(s) failed — this account is not eligible for the judged run.")
        return 1

    if args.env != "comp":
        print("\nAll checks pass. Not recording — only a --env comp run claims an account.")
        return 0

    print("\nAccount is clean. Recording it as used.")
    preflight.record(str(snap["account"]["id"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", default="comp", choices=["dev", "comp"])
    return p


def main() -> int:
    return asyncio.run(main_async(build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
