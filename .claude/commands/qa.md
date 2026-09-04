---
description: Review an implemented story against the constitution and the diff (QA hat)
argument-hint: <path to story file>
---

Review the implementation of **$ARGUMENTS**.

QA hat. You are not the Dev and you do not take their word for anything. Read the
story, then read the actual diff (`git diff`, `git diff --staged`), then the tests.

Fill in the QA review section *in the story file* and record a verdict.

Check, in this order:

1. **Did the test fail first?** Do not assume. Confirm the test asserts behaviour that
   the pre-change code could not have satisfied — a test written around existing code
   passes forever and proves nothing.
2. **Do the acceptance criteria hold?** Each one, against the diff, not against the
   summary.
3. **The constitution articles the plan named** — are they honoured in the code, or
   only in the plan? Article VII is the one most often claimed and least often done:
   find a payload shape, a parse failure or a missing quote in this diff and check
   whether it can report "I could not tell", or whether it renders as zero.
4. **Edge cases**: empty, null, zero, sign, boundary. Name one the tests miss, or say
   plainly that none is missing.
5. **Placement**: is anything here awkward to test? That is the design telling you the
   logic is in the wrong file — a rule in a component, a decision in `cli/`, a
   calculation behind a broker stub.
6. **Suite green**: run it. `pytest`, and `npm test` if the panel moved.

Verdict is `approved` or `changes requested — <what>`. Be specific and be fair: name
the file and line, and say what would satisfy you. Do not request changes for style
the surface's `CLAUDE.md` does not ask for.
