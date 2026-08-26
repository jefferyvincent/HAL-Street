"""Preflight checks for the judged competition run.

The hackathon disqualifies projects run on an existing or reused Alpaca account, and
requires a $100,000 starting balance. Those are the cheapest possible ways to lose, so
they get enforced in code rather than remembered.

Usage:
    ./start.sh preflight --env comp        # or: python -m scripts.preflight --env comp

Exits non-zero on any failure. Wire this into the scheduler so the agent physically
cannot start a judged run against a dirty account.

Every check is computed from data the broker actually returns. Alpaca's account
response has no `is_paper`, no fill count, and no position or order counts — an
earlier version of this file assumed all four and could not have run. Paper is proven
by the PA account-number prefix, and history, positions and orders each take their own
call.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from halstreet import paths
from halstreet.config import ConfigError, load_env
from halstreet.execution.mcp_client import AlpacaMCP, MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError, assert_paper_account

REQUIRED_EQUITY = Decimal("100000.00")
USED_ACCOUNTS = paths.ACCOUNTS_USED

# The judged account must have been created for this hackathon. Widen if the window
# moves; a stale bound here silently passes an old account.
COMPETITION_OPENED = date(2026, 8, 1)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _rows(payload: object) -> list:
    """Normalise a list-ish tool response.

    These endpoints return a bare list, or {"result": [...]}, depending on the tool.
    A shape we do not recognise returns None so the caller can fail the check rather
    than read it as empty — "I could not tell" must never render as "zero".
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("result", "orders", "positions", "activities", "data"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return inner
        if not payload:
            return []
    return None  # type: ignore[return-value]


async def gather(env: str) -> dict:
    """One pass over everything preflight needs, so the checks below stay pure."""
    client = AlpacaMCP.from_env(env)
    account = await client.get_account()
    return {
        "account": account,
        "positions": _rows(await client.get_positions()),
        "orders": _rows(await client.get_orders(status="open")),
        "fills": _rows(await client.get_activities(activity_types="FILL", page_size=1)),
    }


def run_checks(snap: dict) -> list[Check]:
    acct = snap["account"]
    checks: list[Check] = []

    # 1. Paper. Delegated to the same assertion the order path uses, so preflight and
    #    execution can never disagree about what counts as proof.
    try:
        assert_paper_account(acct)
        checks.append(Check("paper environment", True, acct.get("account_number", "?")))
    except LiveEnvironmentError as exc:
        checks.append(Check("paper environment", False, str(exc)))

    # 2. Starting balance, to the cent.
    equity = _decimal(acct.get("equity"))
    checks.append(
        Check(
            "starting equity is $100,000",
            equity == REQUIRED_EQUITY,
            f"equity={equity if equity is not None else acct.get('equity', 'unreadable')}",
        )
    )

    # 3. Never traded. An account with fills is not fresh, whatever its balance says.
    fills = snap["fills"]
    checks.append(
        Check(
            "no trade history",
            fills is not None and len(fills) == 0,
            "unreadable" if fills is None else f"{len(fills)} fill(s) found",
        )
    )

    # 4. Nothing open.
    positions, orders = snap["positions"], snap["orders"]
    readable = positions is not None and orders is not None
    checks.append(
        Check(
            "no open positions or orders",
            readable and not positions and not orders,
            "unreadable"
            if not readable
            else f"positions={len(positions)} orders={len(orders)}",
        )
    )

    # 5. Created inside the competition window.
    raw_created = acct.get("created_at")
    created = None
    if raw_created:
        try:
            created = datetime.fromisoformat(str(raw_created)).date()
        except ValueError:
            created = None
    checks.append(
        Check(
            "account created for this competition",
            created is not None and created >= COMPETITION_OPENED,
            f"created={created or raw_created or 'unknown'} (window opens {COMPETITION_OPENED})",
        )
    )

    # 6. Not previously used. The record is what you point at if anyone asks.
    acct_id = str(acct.get("id") or "")
    previously: list[str] = []
    if USED_ACCOUNTS.exists():
        try:
            previously = json.loads(USED_ACCOUNTS.read_text()).get("ids", [])
        except (json.JSONDecodeError, OSError):
            previously = []
    checks.append(
        Check("account not previously used", bool(acct_id) and acct_id not in previously,
              f"id={acct_id or 'unknown'}")
    )

    return checks


def record(acct_id: str) -> None:
    USED_ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    if USED_ACCOUNTS.exists():
        try:
            ids = json.loads(USED_ACCOUNTS.read_text()).get("ids", [])
        except (json.JSONDecodeError, OSError):
            ids = []
    if acct_id not in ids:
        ids.append(acct_id)
    USED_ACCOUNTS.write_text(json.dumps({"ids": ids}, indent=2) + "\n")


async def main_async(args: argparse.Namespace) -> int:
    try:
        load_env(args.env)
    except ConfigError as exc:
        print(f"  [FAIL] {exc}")
        return 1

    try:
        snap = await gather(args.env)
    except (LiveEnvironmentError, MCPError, ConfigError) as exc:
        print(f"  [FAIL] could not read the account: {exc}")
        return 1

    checks = run_checks(snap)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name.ljust(width)}   {c.detail}")

    failed = [c for c in checks if not c.passed]
    if failed:
        print(f"\n{len(failed)} check(s) failed — this account is not eligible for the judged run.")
        return 1

    if args.env != "comp":
        print("\nAll checks pass. Not recording — only a --env comp run claims an account.")
        return 0

    print("\nAccount is clean. Recording it as used.")
    record(str(snap["account"]["id"]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="comp", choices=["dev", "comp"])
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
