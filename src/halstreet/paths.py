"""Where the agent's mutable state lives.

Runtime data used to sit beside the source: `journal/` and `halstreet.log` in the
repository root, and their locations spelled out as default strings in fourteen
different `add_argument` calls. Both are the same mistake in two forms — state mixed
in with code, and one fact written down in many places, where it can only ever drift.

So there is `var/`, the Unix name for variable program state, holding everything the
agent writes and nothing a human does. One line in `.gitignore` covers it, `rm -rf
var/` is a complete reset, and a deployment that wants state somewhere else — a
mounted volume, a tmpfs, a directory per competition run — sets `HALSTREET_VAR` and
every path below follows.

Nothing here creates a directory. Writers already do that at the point of writing,
which is the only place that knows whether a write is actually about to happen.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Root of everything the agent writes. Override with HALSTREET_VAR.
VAR = Path(os.environ.get("HALSTREET_VAR") or "var")

JOURNAL_DIR = VAR / "journal"
LOG_DIR = VAR / "log"
#: Fetched data that can always be re-fetched. Safe to delete at any time.
CACHE_DIR = VAR / "cache"

#: Append-only record of every cycle, view, menu, proposal, verdict, order and fill.
RUN_JOURNAL = JOURNAL_DIR / "run.jsonl"

#: Structures the agent believes it holds — the broker cannot tell us this.
LEDGER = JOURNAL_DIR / "ledger.json"

#: The circuit breaker's latch, which must survive a restart to mean anything.
CIRCUIT = JOURNAL_DIR / "circuit.json"

#: Competition accounts already claimed, so a second judged run cannot reuse one.
ACCOUNTS_USED = JOURNAL_DIR / "accounts-used.json"

#: Where ./start.sh tees its output.
AGENT_LOG = LOG_DIR / "halstreet.log"

__all__ = ["ACCOUNTS_USED", "AGENT_LOG", "CACHE_DIR", "CIRCUIT", "JOURNAL_DIR",
           "LEDGER", "LOG_DIR", "RUN_JOURNAL", "VAR"]
