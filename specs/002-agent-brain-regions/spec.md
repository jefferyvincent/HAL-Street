# Spec: brain regions inside `agent/`

> **Owner:** Analyst → PM · **Phase:** Specify · **Status:** planned
> **Surface:** python

## Why this exists

`src/halstreet/agent/` is eleven flat modules that do four unrelated jobs. Nothing in
the layout says which: `breaker.py`, `committee.py`, `ledger.py` and `schedule.py` sit
as siblings, and a reader has to open each one to learn that they are, respectively, a
survival reflex, a reasoning stage, a memory, and a body clock.

The sibling packages already carry meaning — `gates/` is the project's thesis in a
directory name, `strategy/` and `marketdata/` say what they hold. `agent/` is the one
package where the naming stops working, and it is also the largest and the one a
reader hits first.

HAL solved this in the same problem domain with literal brain-region names —
`hal/cortex` reasons, `hal/cerebellum` runs the machinery, `hal/hippocampus`
remembers, `hal/brainstem` keeps the autonomic baseline. This codebase already borrows
from that architecture directly: `agent/committee.py` opens with "Adapted from HAL's
`cortex.committee`", and the region it came from is recorded in prose because the
directory could not say it.

## What must become true

1. Every module in `agent/` sits in the region that describes its job: `cortex/`,
   `cerebellum/`, `brainstem/`, `hippocampus/`.
2. Each region's `__init__.py` states what the region is for and what does not belong
   in it — the metaphor is load-bearing or it is decoration.
3. `python -m halstreet.agent.run` still works, unchanged. It is in `start.sh`, the
   README, and the docs.
4. No behaviour changes. Same suite, same count, green before and after.
5. `src/halstreet/CLAUDE.md`'s package table names the regions, so the rule about
   where a module goes stays answerable without reading the tree.
6. The layout is pinned by a test — a module dropped into the wrong region is a
   silent loss of the only thing this change buys.

## Out of scope

- **The sibling packages.** `gates/`, `strategy/`, `marketdata/`, `execution/`,
  `telemetry/` keep their names and their contents. `gates/` in particular: "the model
  proposes, deterministic gates dispose" is the project's central claim, and burying
  it as `cortex/rules.py` would cost more than the metaphor gains.
- **Full HAL parity.** HAL's regions are its top level. Adopting that here means
  dissolving every existing package, and was considered and declined.
- Renaming any module, or changing any function signature.

## Behaviour

Import paths change and nothing else does:

| Was | Becomes |
|---|---|
| `halstreet.agent.llm` | `halstreet.agent.cortex.llm` |
| `halstreet.agent.committee` | `halstreet.agent.cortex.committee` |
| `halstreet.agent.proposal` | `halstreet.agent.cortex.proposal` |
| `halstreet.agent.loop` | `halstreet.agent.cerebellum.loop` |
| `halstreet.agent.manager` | `halstreet.agent.cerebellum.manager` |
| `halstreet.agent.schedule` | `halstreet.agent.brainstem.schedule` |
| `halstreet.agent.lock` | `halstreet.agent.brainstem.lock` |
| `halstreet.agent.breaker` | `halstreet.agent.brainstem.breaker` |
| `halstreet.agent.ledger` | `halstreet.agent.hippocampus.ledger` |
| `halstreet.agent.soak` | `halstreet.agent.hippocampus.soak` |
| `halstreet.agent.run` | unchanged — the entrypoint |

## Open questions

| # | Question | Blocks | Answer |
|---|---|---|---|
| 1 | Where does `breaker.py` go — it is a reflex, but its state is persisted? | 1 | `brainstem/`. What it *is* decides, not what it writes: a daily-loss halt is an autonomic response that overrides deliberation. The persistence is incidental, and `ledger.py` is next door in `hippocampus/` for the case where memory is the point. |
| 2 | Does `run.py` become a region, or stay flat? | 3 | Stays flat. It is the entrypoint, and HAL's own entrypoint (`server.py`) sits outside every region for the same reason. |
| 3 | Re-export the old paths from `agent/__init__.py` so nothing breaks? | 4 | No. An alias is a second name for one thing, and this repo has already paid for that once — `verify_multileg` kept a duplicate `parse_occ` for months behind exactly that reasoning. 37 files import from `agent/`; they get updated. |

## Constitution notes

- **IX (testable placement)** — the article this serves. The regions make "where does
  this go" answerable before the code is written rather than after it is awkward.
- **VI (test first)** — deviation, same shape as spec 001 and recorded in the plan: a
  pure move has nothing to fail first. The layout test *is* written first, because it
  is new behaviour.
