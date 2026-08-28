#!/usr/bin/env python3
"""`./start.sh soak` — run a session, then report what it exercised.

The coverage reading is in `halstreet.agent.hippocampus.soak`; the parser and printing are in
`halstreet.cli.soak`. See src/halstreet/CLAUDE.md, rule 1 — this file used to hold the
coverage logic, and its test had to reach it through `importlib.util.spec_from_file_location`.
"""

from halstreet.cli.soak import main

if __name__ == "__main__":
    raise SystemExit(main())
