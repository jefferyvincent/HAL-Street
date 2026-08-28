"""Command-line entrypoints: argument parsing, defaults, and printing.

One module per command, each exposing `main() -> int`. `scripts/<name>.py` is a
four-line shim onto the matching module here, and `start.sh` dispatches to
`python -m halstreet.cli.<name>`.

The boundary this package exists to hold — see `src/halstreet/CLAUDE.md`, rule 1:

    scripts/x.py          argv and an exit code
    halstreet/cli/x.py    parser, defaults, printing        <- you are here
    halstreet/<domain>/   the decision, pure where possible

A module in here does not decide anything a test would want to assert. Rendering
happens in the domain module and returns a string; this package prints it. That split
is what lets the coverage table, the preflight verdict and the P&L report be tested
without capturing stdout, and it is why these files stay this short.
"""
