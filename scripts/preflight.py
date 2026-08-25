"""Preflight checks for the judged competition run.

The hackathon disqualifies projects run on an existing or reused Alpaca account, and requires a
$100,000 starting balance. Those are the cheapest possible ways to lose, so they get enforced in
code rather than remembered.

Usage:
    python -m scripts.preflight --env comp

Exits non-zero on any failure. Wire this into the scheduler so the agent physically cannot start
a judged run against a dirty account.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

REQUIRED_EQUITY = Decimal("100000.00")
USED_ACCOUNTS = Path("journal/accounts-used.json")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def load_account(env: str) -> dict:
    """Fetch account state through the Alpaca MCP client.

    TODO: replace with the real MCP call once execution/mcp_client.py lands. Keep this the ONLY
    place preflight touches the broker so the checks below stay pure and testable.
    """
    from halstreet.execution.mcp_client import AlpacaMCP  # noqa: PLC0415

    return AlpacaMCP.from_env(env).get_account_snapshot()


def run_checks(acct: dict) -> list[Check]:
    checks: list[Check] = []

    is_paper = bool(acct.get("is_paper"))
    checks.append(Check("paper environment", is_paper, acct.get("endpoint", "unknown")))

    equity = Decimal(str(acct.get("equity", "0")))
    checks.append(
        Check("starting equity is $100,000", equity == REQUIRED_EQUITY, f"equity={equity}")
    )

    fills = int(acct.get("fill_count", -1))
    checks.append(Check("no trade history", fills == 0, f"fills={fills}"))

    positions = int(acct.get("open_positions", -1))
    orders = int(acct.get("open_orders", -1))
    checks.append(
        Check(
            "no open positions or orders",
            positions == 0 and orders == 0,
            f"positions={positions} orders={orders}",
        )
    )

    acct_id = acct.get("id", "")
    previously_used: list[str] = []
    if USED_ACCOUNTS.exists():
        previously_used = json.loads(USED_ACCOUNTS.read_text()).get("ids", [])
    checks.append(
        Check("account not previously used", acct_id not in previously_used, f"id={acct_id}")
    )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="comp", choices=["dev", "comp"])
    args = parser.parse_args()

    acct = load_account(args.env)
    checks = run_checks(acct)

    width = max(len(c.name) for c in checks)
    for c in checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.name.ljust(width)}   {c.detail}")

    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"\n{len(failed)} check(s) failed — this account is not eligible for the judged run.")
        return 1

    print("\nAccount is clean. Recording it as used.")
    USED_ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    ids = json.loads(USED_ACCOUNTS.read_text()).get("ids", []) if USED_ACCOUNTS.exists() else []
    if acct["id"] not in ids:
        ids.append(acct["id"])
    USED_ACCOUNTS.write_text(json.dumps({"ids": ids}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
