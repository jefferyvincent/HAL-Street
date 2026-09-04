# Spec: importable Python entrypoints

> **Owner:** Analyst → PM · **Phase:** Specify · **Status:** planned
> **Surface:** python

## Why this exists

Five commands lived as loose files under `scripts/`, and each one had grown logic that
nothing could reach. `scripts/` has no `__init__.py`; `./start.sh` reached two of them
by path and three through an implicit namespace package, which worked only because the
launcher happens to `cd` to the repo root first.

The cost was not theoretical:

- **`scripts/soak.py`** held the coverage table — the soak's entire output, and the
  thing a write-up claim rests on. Its test had to load the file through
  `importlib.util.spec_from_file_location`, and could not assert on the table at all.
- **`scripts/preflight.py`** held the six checks that decide whether an account is
  eligible for the judged run, including the one that distinguishes "no open
  positions" from "I could not read the positions". None of them had a test.
- **`scripts/verify_multileg.py`** carried its own `parse_occ`, under a comment saying
  the real one "should be ported into `marketdata/`". The port landed as
  `marketdata/occ.py`. The copy stayed, parsing symbols its own way.
- **`scripts/report.py`** held the rule that a structure is only marked when every leg
  priced — a partial mark on a vertical is not a smaller number, it is a different
  trade — with nothing asserting it.

## What must become true

1. Every command is an importable module under `src/halstreet/`, reachable as
   `python -m halstreet.cli.<name>`.
2. A file under `scripts/` contains no function or class definition, imports only its
   `halstreet.cli` module, and calls its `main()`.
3. Every decision extracted from a script has a test that fails if the decision
   changes.
4. No module outside `halstreet/cli/` (and the loop's own entrypoint) parses arguments
   or prints; a module that produces text returns a string.
5. `./start.sh` dispatches every mode to a named module, and no mode reaches a file by
   path.
6. There is exactly one OCC parser in the codebase.
7. Every command a user can type today still works, with the same flags and defaults.

## Out of scope

- Changing what any command *does*. This is a move, not a redesign; output text is
  preserved verbatim where it was already correct.
- `install.sh` and `start.sh`'s own diagnostics, which already have
  `tests/test_entrypoints.py`.
- The panel's build step. It is a real trap, but it belongs to the other surface.
- Adding new commands.

## Behaviour

**Preflight** returns a list of checks and a rendered table. An account whose
positions or fill history came back in an unrecognised shape **fails** the relevant
check with detail `unreadable`; it does not pass as empty.

**Soak** returns the coverage table as a string, including the two-runs warning when a
journal was written by more than one run, and the closing-order line. The unknown
event is not counted; an unstamped record is not a run.

**Report** returns `(marks, note)`. A structure missing any leg quote is absent from
`marks` rather than partially marked. An unreachable broker returns `({}, note)` and an
empty book returns `({}, None)` — those are different facts and the caller prints the
difference.

**Chain reading** returns `[]` only for a shape it does not recognise, and the caller
prints the payload's type and keys rather than reporting "no contracts listed".

## Open questions

| # | Question | Blocks | Answer |
|---|---|---|---|
| 1 | Keep `scripts/*.py` at all, or point `start.sh` straight at the modules? | 2, 7 | Keep them as shims. They are in the README, in `docs/`, and in muscle memory; a four-line file that says where the code went costs nothing and breaks nobody. |
| 2 | Does the whole of `verify_multileg`'s `run()` move? | 1 | No. It is broker calls and printing end to end — a `cli/` module by definition. Only the pure chain reading moves to a domain package. |

## Constitution notes

- **IX (testable placement)** is the article this feature exists to satisfy.
- **VII (no false diagnostic)** governs the preflight and chain-reading behaviour above,
  and is now pinned by tests rather than by care.
- **VI (test first)** is honoured for the new tests and *deviated from* for the ported
  logic — recorded in the plan, not waved through.
