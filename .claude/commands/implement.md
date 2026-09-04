---
description: Implement one story, test first (Dev hat)
argument-hint: <path to story file>
---

Implement the story at **$ARGUMENTS**.

Dev hat. Read the story, then the `CLAUDE.md` for the surface it touches. You should
not need the plan — if you do, the story failed its own rule and is worth saying so.

The order is not negotiable, and it is the same on both surfaces:

1. **Write the failing test** the story names. Name the behaviour, not the function.
   Say *why* in a docstring or comment wherever the answer is non-obvious.
2. **Run it. Watch it fail.** `pytest <file>` or `npm test`. Report what the failure
   said. A test that passed before the code existed was testing nothing, and this step
   is how you find out in ten seconds instead of in review.
3. **Write the smallest code that passes it.** Not the general version. Not the one
   that also handles next quarter.
4. **Run the whole suite.** `pytest` and, if you touched the panel, `npm test`.
5. `ruff check .` for Python.

Then tick the acceptance criteria in the story file — actually tick them, in the file.

Rules that trip people on this repo specifically:

- Python: `scripts/` is argparse and print. The decision goes in a package under
  `src/halstreet/`. Money is `Decimal`, dates come from `clock`, and "I could not
  tell" is never `0`.
- Panel: logic in a hook or `lib/`, markup in the component, strings in `en.json` →
  `constants/strings.ts` → `useStrings()`. And the panel on `:8787` is a build
  artifact — `npm run build`, or your change is only real on `:1420`.

If the suite is not green, the story is not done. Say so plainly rather than
reporting around it.
