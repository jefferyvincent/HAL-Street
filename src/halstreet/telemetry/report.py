"""Marking the open book for the results report.

Split out of the report entrypoint because it is the one part of that command with a
decision in it: which structures get an unrealized figure, and what happens when the
quotes do not arrive. The rest — parsing flags, printing, writing exports — is
`halstreet.cli.report`.

The rule this module exists to hold: **a structure only gets a mark if every leg was
priced.** A partial mark on a spread is not a smaller number, it is a wrong one — one
leg of a vertical priced without the other reads as an outright position.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.agent.cerebellum.manager import mark_structure
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.config import ConfigError
from halstreet.execution.mcp_client import AlpacaMCP, MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError


def snapshot_chain(payload: object) -> dict:
    """The per-symbol quote map out of an option-snapshot response."""
    if isinstance(payload, dict):
        inner = payload.get("snapshots")
        return inner if isinstance(inner, dict) else payload
    return {}


def marks_from(ledger: Ledger, chain: dict) -> dict[str, Decimal]:
    """Net mark per open structure, skipping any whose legs did not all price."""
    out: dict[str, Decimal] = {}
    for structure in ledger.open_structures:
        mark = mark_structure(structure, chain)
        if mark.complete:
            out[structure.structure_id] = mark.value
    return out


async def live_marks(env: str, ledger: Ledger) -> tuple[dict[str, Decimal], str | None]:
    """Current net mark per open structure, and why it is empty if it is.

    Returns `(marks, note)`. The note is not decoration: an empty dict means either
    "nothing is open" or "the broker was unreachable", and those are different facts
    about the report that follows. Reporting the second as the first would print a
    realized-only P&L with no indication that the unrealized column is missing rather
    than zero — Constitution VII, in the place where it costs a number.
    """
    if not ledger.open_structures:
        return {}, None
    symbols = sorted({s for st in ledger.open_structures for s in st.legs})
    try:
        client = AlpacaMCP.from_env(env)
        payload = await client.get_option_snapshot(symbols)
    except (MCPError, LiveEnvironmentError, ConfigError) as exc:
        return {}, f"could not fetch quotes ({exc}); unrealized P&L omitted"
    return marks_from(ledger, snapshot_chain(payload)), None
