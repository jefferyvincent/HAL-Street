# Tasks: brain regions inside `agent/`

> **Owner:** Scrum Master · **Phase:** Tasks · **Plan:** ./plan.md

| # | Task | Surface | Test first | Depends on |
|---|------|---------|-----------|------------|
| 1 | Pin the layout: membership, declarations, forbidden edges | python | `tests/agent/test_regions.py` | — |
| 2 | Create the four regions and move the ten modules | python | (1) | 1 |
| 3 | Write each region's `__init__.py`, including what it refuses | python | (1) | 2 |
| 4 | Rewrite every `halstreet.agent.*` import across src, tests, scripts | python | the existing 1410 | 2 |
| 5 | Repoint the path literals in tests that read modules off disk | python | the tests themselves | 4 |
| 6 | Move the `E501` per-file ignore to `cortex/llm.py` | python | `ruff check .` | 2 |
| 7 | `[P]` Update the package table in `src/halstreet/CLAUDE.md` and the README layout | python | `tests/test_method.py` | 3 |

Requirement coverage: 1 → 2 · 2 → 3 · 3 → 2 (run.py untouched) · 4 → 4,5 · 5 → 7 · 6 → 1.

## Definition of done

- [x] The test named in row 1 existed and failed first — 12 failures, no regions
- [x] `pytest` green: 1431, up 21 from 1410 by the new layout test alone
- [x] `ruff check .` clean
- [x] `python -m halstreet.agent.run --help` unchanged, `./start.sh` modes all dispatch
- [x] No new user-facing English outside `en.json` (n/a — python surface)
- [x] Spec requirements 1..6 each map to a merged task
