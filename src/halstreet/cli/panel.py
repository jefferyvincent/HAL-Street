"""Serve the read-only telemetry panel.

    ./start.sh panel            # http://127.0.0.1:8787, opened in a browser
    ./start.sh panel -- --no-browser

It opens the page for you unless there is nowhere to open it — a headless box, an SSH
session with no display, or a bundle that has not been built — in which case it says
which, because a convenience that vanishes without explanation reads as a broken one.
`$HALSTREET_NO_BROWSER` turns it off for anything run by a process manager.

The React bundle is served from `apps/desktop/dist`, so it has to be built once:

    cd apps/desktop && npm install && npm run build

For working on the panel itself, `npm run dev` puts Vite on :1420 with hot reload and
proxies /api and /ws back here — leave this process running underneath it.

Reads the same files the agent writes. It can be started, killed and restarted mid-run
without the agent noticing, and it cannot place, cancel or modify an order — see
`telemetry/server.py` for why that is deliberate.
"""

from __future__ import annotations

import argparse
import os
import threading

from halstreet import paths
from halstreet.config import ConfigError, load_env
from halstreet.telemetry import browser
from halstreet.telemetry.server import DIST, serve


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="HAL Street telemetry panel (read-only)",
        # Defaults resolve through paths.py rather than being literals here, so
        # --help has to show them or nobody can tell where a run will write.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--env", default="dev", choices=["dev", "comp"],
                   help="which credentials the structure chart reads")
    p.add_argument("--port", type=int, default=8787, help="port for the panel")
    p.add_argument("--host", default="127.0.0.1",
                   help="address to bind. The default reaches this machine only; "
                        "0.0.0.0 reaches your whole network, which prints a warning "
                        "naming what becomes visible")
    # None, not a literal, so the account can decide — the same reason the agent and
    # the report take theirs this way. `--env comp` on a panel wired to the dev
    # journal would show a rehearsal while claiming to watch the judged run, which is
    # a worse failure here than anywhere else: this screen is what a human looks at
    # to decide whether the agent is behaving.
    p.add_argument("--journal", default=None,
                   help="append-only run journal (default: follows --env)")
    p.add_argument("--ledger", default=None,
                   help="structure ledger — what the broker cannot tell us "
                        "(default: follows --env)")
    p.add_argument("--breaker", default=None,
                   help="circuit-breaker state (equity baseline, halt latch) "
                        "(default: follows --env)")
    p.add_argument("--no-browser", action="store_true",
                   help=f"do not open the panel in a browser (or set ${browser.NO_BROWSER})")
    return p


def resolve(args: argparse.Namespace) -> argparse.Namespace:
    journal, ledger, breaker = paths.for_env(args.env)
    if args.journal is None:
        args.journal = str(journal)
    if args.ledger is None:
        args.ledger = str(ledger)
    if args.breaker is None:
        args.breaker = str(breaker)
    return args


def main() -> int:
    args = resolve(build_parser().parse_args())
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
    built = (DIST / "index.html").exists()
    if not built:
        print("note: apps/desktop/dist is not built — the API and socket will serve, "
              "but / will not.\n      cd apps/desktop && npm install && npm run build")

    # Whether to open one is decided in `telemetry/browser`, not here — headless
    # boxes, SSH sessions and an unbuilt bundle are rules worth asserting, and a
    # `if os.environ.get(...)` in a CLI module is a rule nothing can reach.
    url = f"http://127.0.0.1:{args.port}"
    verdict = browser.should_open(disabled=args.no_browser, built=built,
                                  environ=os.environ)
    if verdict.open:
        # A thread, because `serve` blocks and the port is not up yet. Daemon, so
        # Ctrl-C during the wait kills the panel rather than hanging on a browser
        # that was never going to arrive.
        threading.Thread(target=browser.open_when_ready, args=(url, args.port),
                         daemon=True).start()
    else:
        # Said out loud. An absent convenience with no explanation reads as a broken
        # one, and the fix differs per reason — Constitution VII.
        print(f"note: not opening a browser ({verdict.why}). The panel is at {url}")

    # Host is deliberately not a flag: this serves live position data for a real
    # account, and binding it to 0.0.0.0 on conference wifi should not be one
    # argument away.
    serve(host=args.host, port=args.port, journal=args.journal, ledger=args.ledger,
          breaker=args.breaker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
