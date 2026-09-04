#!/usr/bin/env python3
"""`./start.sh scorecard` — mark the strategy engines against the tape.

The scoring rules are in `halstreet.telemetry.scorecard`; the parser and printing are
in `halstreet.cli.scorecard`. See src/halstreet/CLAUDE.md, rule 1.
"""

from halstreet.cli.scorecard import main

if __name__ == "__main__":
    raise SystemExit(main())
