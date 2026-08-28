#!/usr/bin/env python3
"""`./start.sh report` — P&L, gate counts, drawdown.

The marking logic is in `halstreet.telemetry.report`; the parser and printing are in
`halstreet.cli.report`. See src/halstreet/CLAUDE.md, rule 1.
"""

from halstreet.cli.report import main

if __name__ == "__main__":
    raise SystemExit(main())
