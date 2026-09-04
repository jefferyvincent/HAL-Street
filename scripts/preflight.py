#!/usr/bin/env python3
"""`./start.sh preflight` — is this account eligible for the judged run?

The checks are in `halstreet.execution.preflight`; the parser and printing are in
`halstreet.cli.preflight`. See src/halstreet/CLAUDE.md, rule 1.
"""

from halstreet.cli.preflight import main

if __name__ == "__main__":
    raise SystemExit(main())
