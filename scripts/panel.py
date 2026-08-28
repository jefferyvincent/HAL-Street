#!/usr/bin/env python3
"""`./start.sh panel` — serve the read-only telemetry panel.

Argument parsing and everything else lives in `halstreet.cli.panel`, where a test can
import it. See src/halstreet/CLAUDE.md, rule 1, for why this file is four lines.
"""

from halstreet.cli.panel import main

if __name__ == "__main__":
    raise SystemExit(main())
