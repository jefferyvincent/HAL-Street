#!/usr/bin/env python3
"""`./start.sh verify` — verify multi-leg orders end to end against a live chain.

Chain reading and strike selection are in `halstreet.execution.chain_pick`, tested
offline; the broker calls and printing are in `halstreet.cli.verify`. See
src/halstreet/CLAUDE.md, rule 1.
"""

from halstreet.cli.verify import main

if __name__ == "__main__":
    raise SystemExit(main())
