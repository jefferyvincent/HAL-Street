---
description: Break a plan into ordered, independently-green tasks (Spec Kit phase 3, Scrum Master hat)
argument-hint: <spec dir, e.g. 001-python-cli-modules>
---

Break `specs/$ARGUMENTS/plan.md` into tasks.

Scrum Master hat. Write `specs/$ARGUMENTS/tasks.md` from
`.specify/templates/tasks-template.md`.

The ordering rule that decides everything else: **each task leaves the suite green.**
A task that needs the next one to compile is two halves of one task — merge them. A
task that touches six files is usually three tasks.

Each row carries the test to write *first* (Constitution VI), the surface, and its
dependencies. Mark `[P]` only where there is no shared file and no ordering
dependency — a wrong `[P]` costs more than a missing one.

Then check coverage both directions and state the result:

- every numbered spec requirement maps to at least one task
- every task traces back to a requirement — a task that does not is scope you are
  adding on your own authority, so cut it or send it back to the spec

Fill in the Definition of done. Do not write code.
