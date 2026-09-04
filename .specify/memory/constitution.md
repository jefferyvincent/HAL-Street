# Constitution

The rules that outrank a spec, a plan, a story, and whoever is in a hurry. Spec Kit
calls this the constitution; BMAD's checklists defer to it. A plan that violates an
article here is rejected at the Constitution Check — the article is not amended to
accommodate the plan.

Amendments are a commit of their own, with the reason in the message. Every article
below is enforced by a test; if you cannot point at the test, it is a preference, not
an article, and it does not belong in this file.

---

## I. Paper only, proven rather than declared

No code path may reach a live brokerage account. The proof is the account-number
prefix Alpaca actually returns, not a config flag that says `paper` — see
`execution/paper_assert.py`, which the order path and `preflight` both call so they
cannot disagree about what counts as proof.

*Enforced by:* `tests/execution/test_paper_assert.py`, and `start.sh` refuses an `AK…`
credential before Python starts.

## II. The model proposes, deterministic gates dispose

An LLM never decides whether an order is placed. It produces a proposal; the 16 gates
in `gates/` accept or reject it, and every one of them is a pure function of the
proposal and injected state. A gate may not call the network, read the wall clock, or
consult a model.

New risk logic goes in a gate. It does not go in a prompt.

*Enforced by:* `tests/gates/` — every gate has a paired test that proves it *rejects*,
and `tests/test_writeup.py` pins the count against the chain.

## III. Ask the exchange what day it is

`clock.today()` and `clock.now()`, never `date.today()` or `datetime.now()`, anywhere a
decision about the market is made. The host's calendar is a fact about where a server
is plugged in; DTE, session rollover and force-close windows are facts about the
exchange.

*Enforced by:* ruff `DTZ`, and `tests/test_clock.py`.

## IV. Money is `Decimal`

Prices, strikes, credits, equity and P&L are `Decimal` from the moment they are parsed
to the moment they are rendered. A `float` in a money path is a defect even when the
arithmetic happens to come out right.

## V. The journal is append-only, and says who wrote it

`telemetry/journal.py` appends; nothing rewrites or deletes. Every event carries its
`run` id, because a table that silently merges two runs is worse than no table — see
the multi-run warning in the soak coverage report for the day that cost.

## VI. Test first, and watch it fail

Write the failing test, run it, watch it fail, then write the smallest code that
passes it. A test written afterwards tests what the code does, which is the one thing
you already knew.

Name the behaviour, not the function. State *why* in a comment wherever the answer is
non-obvious — for a lot of this system the tests are the only specification of what
the numbers mean.

`pytest` and `npm test` must both be green before any piece of work is called done.
Not skipped, not xfailed, not "failing for an unrelated reason".

## VII. A diagnostic may not state something false

This project has been bitten twice by a message that confidently described a codebase
that did not exist — `start.sh` reporting a built feature as unbuilt, `install.sh`
reporting a stale venv as a missing pip. An error path that guesses is worse than one
that says "I could not tell".

Corollary, and it is load-bearing across the whole panel: **"I could not read it" must
never render as "zero"**.

*Enforced by:* `tests/test_entrypoints.py`.

## VIII. No user-facing English outside the string table

Applies to `apps/desktop`. Every label, empty state, unit, tooltip and error string
lives in `src/locales/en.json`, reaches the markup through `constants/strings.ts`, and
is read with `useStrings()`. `src/lib/` holds no English at all — a word spelled there
is a translation hole no locale file can reach.

*Enforced by:* the rules in `apps/desktop/CLAUDE.md`, and the locale-shape tests.

## IX. Logic lives where a test can reach it without ceremony

Python: importable modules under `src/halstreet/`. A file under `scripts/` is an
argument parser and a `print`, nothing else.

TypeScript: pure functions in `src/lib/`, decisions in `src/hooks/`, markup in
`components/` and `views/`.

Both surfaces have the same tell: **if something is awkward to test, that is the
design telling you the logic is in the wrong file.** Move it down; do not mock around
it.

*Enforced by:* `tests/test_cli_entrypoints.py` on the Python side, and rules 1–2 of
`apps/desktop/CLAUDE.md` on the other.

## X. The two surfaces have different rules, on purpose

`src/halstreet/CLAUDE.md` governs Python. `apps/desktop/CLAUDE.md` governs the panel.
This document is the only thing both obey, and neither borrows the other's conventions
to settle an argument.

They differ because their failures differ. A wrong number in the trading path is
silent, expensive, and discovered days later from a journal; a wrong number on the
panel is visible to whoever is looking at it, and costs a rebuild. That asymmetry is
why one surface bans a float in a money path and the other bans an English word in a
component, and why importing either rule into the other's file produces ceremony
rather than safety.

*Enforced by:* `tests/test_method.py`, which pins that both files exist, that the root
router names them, and that every pointer between them resolves.
