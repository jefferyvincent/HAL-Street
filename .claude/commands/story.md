---
description: Shard a task into a self-contained BMAD story (Scrum Master hat)
argument-hint: <spec dir> <task number>
---

Shard task **$ARGUMENTS** into a story.

Scrum Master hat, and this is BMAD's contribution to the method, so honour its one
rule: **the story carries its own context.** Whoever picks it up gets this page and
the repo, and nothing else. No "see the plan", no "as discussed above". Lift what is
needed out of the spec and paste it in — duplication is the point here.

Write `specs/<spec dir>/stories/<task number>-<slug>.md` from
`.specify/templates/story-template.md`:

- **Context** — the failure this addresses, in its own words.
- **Acceptance criteria** — observable, testable, each falsifiable by a named input.
- **Files** — path and what changes in it.
- **Test first** — the exact test to write, named as a behaviour, and what it asserts
  before any implementation exists.
- **QA review** — leave it empty. Dev does not fill this in; `/qa` does.

Read the surface's `CLAUDE.md` and inline the rules that bear on these files, so the
Dev does not have to go looking.
