---
description: Turn a spec into an architecture plan and run the Constitution Check (Spec Kit phase 2, Architect hat)
argument-hint: <spec dir, e.g. 001-python-cli-modules>
---

Plan the implementation of `specs/$ARGUMENTS/spec.md`.

Architect hat. Read the spec, `.specify/memory/constitution.md`, and the `CLAUDE.md`
for every surface the spec touches. Then read the code the spec names — the plan is
worthless if it guesses at what is already there.

Write `specs/$ARGUMENTS/plan.md` from `.specify/templates/plan-template.md`.

**Run the Constitution Check first, and record a real verdict.** Walk every article,
say whether it bears on this feature, and if it does, how the plan honours it. An
article marked "n/a" with no sentence is a check that did not happen. A deviation
needs a recorded reason and a test that pins its blast radius; "faster this way" is
not a reason. If the verdict is `blocked`, stop and say what would unblock it — do
not redesign the constitution to fit the plan.

Then:

- **Shape** — every module, hook or file this touches, and one line on why that is
  the right home. Name what *moves*, not only what is added.
- **What gets tested, and where** — a row per behaviour, written before any code
  exists. A behaviour with no natural home means the shape is wrong; fix the shape.
- **Risks** — what could be silently wrong after this ships, and what would catch it.

If the spec has an unanswered question that blocks a requirement, refuse to plan that
requirement and say which.

Do not write implementation code. Do not write tasks.
