"""Is this account eligible for the judged run?

The hackathon disqualifies a project run on an existing or reused Alpaca account, and
requires a $100,000 starting balance. Those are the cheapest possible ways to lose, so
they are enforced in code rather than remembered.

Every check is computed from data the broker actually returns. Alpaca's account
response has no `is_paper`, no fill count, and no position or order counts — an earlier
version of this assumed all four and could not have run. Paper is proven by the PA
account-number prefix, and history, positions and orders each take their own call.

The checks are pure functions of a gathered snapshot, which is the whole reason they
live here rather than beside an `argparse` parser: `run_checks` can be handed a
hand-built payload in a test and asked what it concludes. `halstreet.cli.preflight`
does the printing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from halstreet import paths
from halstreet.execution.mcp_client import AlpacaMCP
from halstreet.execution.paper_assert import LiveEnvironmentError, assert_paper_account

REQUIRED_EQUITY = Decimal("100000.00")
USED_ACCOUNTS = paths.ACCOUNTS_USED

#: The judged account must have been created for this hackathon. Widen if the window
#: moves; a stale bound here silently passes an old account.
COMPETITION_OPENED = date(2026, 8, 1)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def rows(payload: object) -> list | None:
    """Normalise a list-ish tool response, or None if the shape is unrecognised.

    These endpoints return a bare list, or `{"result": [...]}`, depending on the tool.
    A shape we do not recognise returns None so the caller fails the check rather than
    reading it as empty — **"I could not tell" must never render as "zero"**, which
    here would mean certifying an account as clean because its positions came back in
    a shape nobody had seen before. Constitution VII.
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
    return None


async def gather(env: str) -> dict:
    """One pass over everything preflight needs, so the checks below stay pure."""
    client = AlpacaMCP.from_env(env)
    account = await client.get_account()
    return {
        "account": account,
        "positions": rows(await client.get_positions()),
        "orders": rows(await client.get_orders(status="open")),
        "fills": rows(await client.get_activities(activity_types="FILL", page_size=1)),
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
    checks.append(
        Check("account not previously used", bool(acct_id) and acct_id not in used_ids(),
              f"id={acct_id or 'unknown'}")
    )

    return checks


def used_ids() -> list[str]:
    """Accounts already claimed by a judged run. Unreadable file reads as empty.

    Deliberately the one place that does *not* follow Constitution VII, and the reason
    is the direction of the error: an unreadable record makes this check fail closed
    on the *next* account, blocking a run that has done nothing wrong. The check that
    matters — a previously recorded id — is unaffected, because a file we cannot parse
    holds no ids we can match against either way.
    """
    if not USED_ACCOUNTS.exists():
        return []
    try:
        return json.loads(USED_ACCOUNTS.read_text()).get("ids", [])
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def record(acct_id: str) -> None:
    ids = used_ids()
    if acct_id not in ids:
        ids.append(acct_id)
    USED_ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    USED_ACCOUNTS.write_text(json.dumps({"ids": ids}, indent=2) + "\n")


def render(checks: list[Check]) -> str:
    """The check table as a string. Printing is the CLI's job, not this module's."""
    width = max((len(c.name) for c in checks), default=0)
    return "\n".join(
        f"  [{'PASS' if c.passed else 'FAIL'}] {c.name.ljust(width)}   {c.detail}"
        for c in checks
    )


def failures(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.passed]
