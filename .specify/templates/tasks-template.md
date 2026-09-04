# Tasks: <feature>

> **Owner:** Scrum Master · **Phase:** Tasks · **Plan:** ./plan.md

Ordered so that each task leaves the suite green. A task that requires the next one to
compile is two halves of one task.

`[P]` marks tasks with no shared file and no ordering dependency — safe to run in
parallel.

| # | Task | Surface | Test first | Depends on |
|---|------|---------|-----------|------------|
| 1 | | python/ux | tests/… | — |

## Definition of done

- [ ] The test named in each row exists and failed before its code did
- [ ] `pytest` green (python) / `npm test` green (ux)
- [ ] `ruff check .` clean (python)
- [ ] No new user-facing English outside `en.json` (ux)
- [ ] Spec requirements 1..n each map to a merged task
