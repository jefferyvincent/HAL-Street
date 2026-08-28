---
description: Write the spec for a feature (Spec Kit phase 1, Analyst + PM hats)
argument-hint: <what you want built>
---

Write a spec for: **$ARGUMENTS**

Wear the Analyst hat first, then the PM hat. Read
`.specify/memory/constitution.md` and the surface's `CLAUDE.md` before you write a
line — the constitution decides what is even permissible to specify.

1. Decide the surface: `python`, `ux`, or `both`. If both, the spec has two Behaviour
   sections and they do not share requirements.
2. Pick the next number: `ls specs/` and increment. Create
   `specs/NNN-kebab-slug/spec.md` from `.specify/templates/spec-template.md`.
3. Fill it in. The rules that actually matter:
   - **Name the failure before the feature.** If you cannot say what is wrong today
     and what it costs, stop and say so — that is a preference, not a spec.
   - Requirements are numbered and observable. A test must be pointable at each.
   - **Out of scope is not optional.** It is what stops the plan growing later.
   - Cover the empty, null, unreadable and stale cases. Constitution VII: "I could
     not tell" is never "zero".
   - For `ux`, describe what the reader sees, by string key, never by English literal.
4. Log every real ambiguity in Open Questions. Do not invent an answer to look
   finished — an unanswered question that blocks a requirement stops this going to
   Plan.

Do not write code, a plan, or tasks. Do not touch `src/`. Output the path, the
requirement list, and any question that needs the user.
