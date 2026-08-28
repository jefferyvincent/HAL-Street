# Tasks: importable Python entrypoints

> **Owner:** Scrum Master · **Phase:** Tasks · **Plan:** ./plan.md

Ordered so each task leaves the suite green. `[P]` marks tasks with no shared file and
no ordering dependency.

| # | Task | Surface | Test first | Depends on |
|---|------|---------|-----------|------------|
| 1 | Extract the eligibility checks to `execution/preflight.py` | python | `tests/execution/test_preflight.py` | — |
| 2 | Extract chain reading to `execution/chain_pick.py`, on `occ.parse` | python | `tests/execution/test_chain_pick.py` | — |
| 3 | Extract marking to `telemetry/report.py`, returning `(marks, note)` | python | `tests/telemetry/test_report_marks.py` | — |
| 4 | Extract the coverage table to `agent/soak.py`, returning a string | python | `tests/agent/test_soak_coverage.py` | — |
| 5 | Add `halstreet/cli/` with one entrypoint per command | python | `tests/test_cli_entrypoints.py` | 1–4 |
| 6 | Reduce `scripts/*.py` to shims; drop `__pycache__` | python | `tests/test_cli_entrypoints.py` | 5 |
| 7 | Point `start.sh` at `-m halstreet.cli.*` | python | `tests/test_cli_entrypoints.py` | 5 |
| 8 | Rewrite the soak harness test to import rather than exec | python | `tests/test_soak_harness.py` | 4, 5 |
| 9 | `[P]` Pin the method scaffolding | both | `tests/test_method.py` | — |

Requirement coverage: 1 → 5,7 · 2 → 6 · 3 → 1,2,3,4 · 4 → 5 · 5 → 7 · 6 → 2 · 7 → 5,6,7.

## Definition of done

- [x] The test named in each row exists
- [x] `pytest` green
- [x] `ruff check .` clean
- [x] No new user-facing English outside `en.json` (n/a — python surface)
- [x] Spec requirements 1..7 each map to a merged task
