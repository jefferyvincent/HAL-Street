# Story 4: the coverage table becomes a function that returns a string

> **Owner:** Dev · Reviewed by QA · **Tasks:** ../tasks.md#4

## Context

The soak's entire output is a table saying which lifecycle events a session reached.
It is the evidence behind several claims in `docs/WRITEUP.md`, and it had no test —
because it lived in `scripts/soak.py`, which is not importable. The test that did
exist reached the file through `importlib.util.spec_from_file_location` and asserted
only on the argv the harness builds.

Two failures in that table have already happened and neither announced itself:

- Two soaks shared one journal for an hour, one of them a version behind. The table
  counts events and cannot tell whose, so it read as a single clean session.
- `--journal` was reported on but never forwarded to the agent. The agent wrote the
  default file, the report read the requested one, and a soak that placed orders all
  day printed every event as never reached.

## Acceptance criteria

- [x] `coverage(path)` returns `(Counter, missing)` over the lifecycle names only
- [x] `render(path)` returns the table as a **string**; nothing in the module prints
- [x] A journal with more than one `run` id is announced *before* the table
- [x] A single run produces no warning — the ordinary case stays quiet
- [x] An event with no `run` id is not counted as a run, and an unstamped legacy
      journal reports zero runs rather than a warning
- [x] `closing_orders(path)` counts closes only, and only those carrying a fill price
- [x] `agent_argv(...)` forwards `--journal` and `--until-close`; `--submit` and the
      committee flags appear only when asked
- [x] An event name the lifecycle does not know does not appear in the table

## Files

| Path | What changes |
|---|---|
| `src/halstreet/agent/hippocampus/soak.py` | New. `LIFECYCLE`, `coverage`, `runs_in`, `closing_orders`, `render`, `agent_argv`. |
| `src/halstreet/cli/soak.py` | New. Parser, `resolve()`, and the two `print` calls. |
| `scripts/soak.py` | Reduced to a shim; loses its `sys.path.insert`. |
| `tests/agent/test_soak_coverage.py` | New. |
| `tests/test_soak_harness.py` | Imports the module; keeps every existing assertion. |

## Test first

`tests/agent/test_soak_coverage.py::test_two_runs_in_one_journal_are_announced_before_the_table`
— write a journal with two `run` ids, assert the warning appears in the returned
string and that its index precedes the table heading. It cannot pass while the
function prints instead of returning, which is the design change this story is for.

## QA review

- [x] The test failed first — `render` did not exist; the ported `report()` printed and
      returned `0`, so every assertion on a returned string failed
- [x] Constitution V honoured: this module only reads the journal
- [x] Constitution VII honoured: an unstamped record reports zero runs rather than
      guessing one, and an unknown event is not silently folded into the table
- [x] Edge cases: empty journal, single run, unstamped run, unknown event, close with
      an empty-string fill price
- [x] No diagnostic here can state something false — the two-run warning names the run
      ids it found rather than asserting a count it inferred

**Verdict:** approved
