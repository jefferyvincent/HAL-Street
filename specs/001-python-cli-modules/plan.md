# Plan: importable Python entrypoints

> **Owner:** Architect · **Phase:** Plan · **Spec:** ./spec.md

## Constitution Check

| Article | Bears on this? | How it is honoured |
|---|---|---|
| I. Paper only | yes | `preflight` keeps delegating to `execution/paper_assert.py`; the assertion is not reimplemented on the way past. `cli/verify.py` keeps its refusal to submit against `--env comp`. |
| II. Gates dispose | no | No gate moves and no decision path changes. |
| III. Exchange clock | yes | `chain_pick` takes the day from `clock.today()`, as the script did. Its test pins the clock rather than asking the host what day it is. |
| IV. Decimal money | yes | Strikes and marks stay `Decimal` across the move; no parse is re-typed. |
| V. Append-only journal | yes | `agent/soak.py` only reads. Nothing here writes a journal. |
| VI. Test first | **deviation** | See below. |
| VII. No false diagnostic | yes | `rows()` returning `None`, the note on unreachable quotes, and the "shape not recognised" branch are the three behaviours most at risk in a move, and each gets a test naming the failure. |
| VIII. No stray English | no | Python surface. |
| IX. Testable placement | yes | The point of the feature. Enforced afterwards by `tests/test_cli_entrypoints.py` rather than by convention. |

**Verdict:** pass with noted deviation.

**The deviation, stated plainly.** Article VI wants the failing test first. For logic
that already exists and is being *moved*, a test written first would be written against
the code in front of us and would pass before the move — testing nothing, which is the
exact failure Article VI exists to prevent. So the order here is: move the code
unchanged, then write tests that pin the behaviour, then confirm they fail against a
deliberately broken version of it.

The blast radius is bounded by requirement 7: the move may not change behaviour, and
the full suite passing before and after is the evidence. Any *new* behaviour in this
feature — `nearest()`'s tie-break, `live_marks` returning a note — is test-first with
no exception, because there is nothing to move.

## Shape

| Path | Why here |
|---|---|
| `halstreet/cli/__init__.py` | States the three-layer boundary once, where a reader of any command lands. |
| `halstreet/cli/{preflight,report,soak,panel,verify}.py` | Parser, defaults, printing. One per command. |
| `halstreet/execution/preflight.py` | The eligibility checks. Broker-adjacent and paper-assertion-adjacent; `execution/` owns that boundary. |
| `halstreet/execution/chain_pick.py` | Reading a chain payload and picking strikes. **Moves** off `verify_multileg`, and its duplicate `parse_occ` dies here — `marketdata/occ.parse` is the one parser. |
| `halstreet/telemetry/report.py` | Marking the open book. Telemetry owns P&L presentation; `pnl.py` is next door. |
| `halstreet/agent/soak.py` | Reading a run back out of its journal. It is about the agent's own lifecycle. |
| `scripts/*.py` | Four-line shims. Kept per spec question 1. |
| `start.sh` | Five branches move from paths and `scripts.` to `-m halstreet.cli.*`. |

Deleted on the way: the second `parse_occ`, and the `sys.path.insert` in `soak.py`
that existed only because the file was not in a package.

## What gets tested, and where

| Behaviour | Test file | Why there |
|---|---|---|
| Eligibility checks, and unreadable ≠ clean | `tests/execution/test_preflight.py` | Mirrors the module. |
| Chain shapes, expiry floor, strike ties | `tests/execution/test_chain_pick.py` | Pure; no broker needed to reach any of it. |
| Partial marks omitted; unreachable ≠ flat | `tests/telemetry/test_report_marks.py` | Mirrors the module. |
| Coverage table, two-run warning, argv forwarding | `tests/agent/test_soak_coverage.py` | Unit level, on strings rather than stdout. |
| The layering itself | `tests/test_cli_entrypoints.py` | Nothing else can see a shim growing a helper. |
| The method's own scaffolding | `tests/test_method.py` | A broken cross-reference in a rules file is a rule nobody can follow. |
| Harness wiring, end to end | `tests/test_soak_harness.py` | Rewritten to import the module rather than exec the file. |

## Risks

- **A silent behaviour change during the move.** Caught by the existing suite staying
  green, and by porting output strings verbatim.
- **`start.sh` and the package drifting apart** — a mode dispatching to a module that
  was renamed. `test_cli_entrypoints` imports every dispatched name.
- **The shims rotting back into scripts.** The definition and import checks fail the
  moment one grows a helper.
- **`scripts/__pycache__` shadowing.** Stale `.pyc` from the namespace-package era can
  satisfy an import that should fail. Removed as part of the move.
