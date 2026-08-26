#!/usr/bin/env python3
"""Serve the read-only telemetry panel.

    ./start.sh panel            # http://127.0.0.1:8787

The React bundle is served from `apps/desktop/dist`, so it has to be built once:

    cd apps/desktop && npm install && npm run build

For working on the panel itself, `npm run dev` puts Vite on :1420 with hot reload and
proxies /api and /ws back here — leave this process running underneath it.

Reads the same files the agent writes. It can be started, killed and restarted
mid-run without the agent noticing, and it cannot place, cancel or modify an order —
see `telemetry/server.py` for why that is deliberate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from halstreet import paths
from halstreet.config import ConfigError, load_env
from halstreet.telemetry.server import DIST, serve


def main() -> int:
    p = argparse.ArgumentParser(
        description="HAL Street telemetry panel (read-only)",
        # Defaults resolve through paths.py rather than being literals here, so
        # --help has to show them or nobody can tell where a run will write.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--env", default="dev", choices=["dev", "comp"],
                   help="which credentials the structure chart reads")
    p.add_argument("--port", type=int, default=8787, help="localhost port for the panel")
    p.add_argument("--journal", default=str(paths.RUN_JOURNAL),
                   help="append-only run journal")
    p.add_argument("--ledger", default=str(paths.LEDGER),
                   help="structure ledger — what the broker cannot tell us")
    p.add_argument("--breaker", default=str(paths.CIRCUIT),
                   help="circuit-breaker state (equity baseline, halt latch)")
    args = p.parse_args()
    # The panel reads the journal, the ledger and the circuit file — none of which
    # need credentials. The one exception is the structure chart, which asks Alpaca
    # for a contract's price history, so the environment is loaded if it is there and
    # the panel runs perfectly well without it: that route degrades to drawing the
    # entry, target and stop with no price line, which is most of what it is for.
    try:
        load_env(args.env, required=False)
    except ConfigError as exc:
        print(f"note: {exc}\n      the panel will serve; structure charts will not.")

    # Said once, here, rather than left for the browser to report as a 503: the
    # process is about to start successfully and serve an API, so "it is running" and
    # "you will see something" are two different facts.
    if not (DIST / "index.html").exists():
        print("note: apps/desktop/dist is not built — the API and socket will serve, "
              "but / will not.\n      cd apps/desktop && npm install && npm run build")

    # Host is deliberately not a flag: this serves live position data for a real
    # account, and binding it to 0.0.0.0 on conference wifi should not be one
    # argument away.
    serve(port=args.port, journal=args.journal, ledger=args.ledger, breaker=args.breaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
