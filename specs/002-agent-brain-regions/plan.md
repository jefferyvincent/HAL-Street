# Plan: brain regions inside `agent/`

> **Owner:** Architect · **Phase:** Plan · **Spec:** ./spec.md

## Constitution Check

| Article | Bears on this? | How it is honoured |
|---|---|---|
| I. Paper only | no | No path to the broker changes. `execution/` is untouched. |
| II. Gates dispose | yes | `gates/` stays at top level and stays the name. The regions are a statement about the agent's internals, not about who decides an order. |
| III. Exchange clock | yes | `schedule.py` moves into `brainstem/` and keeps taking its time from `clock`, which stays where it is — a body clock that reads the exchange, not the host. |
| IV. Decimal money | no | No arithmetic moves. |
| V. Append-only journal | yes | `hippocampus/` holds what is remembered, and `ledger.py` is the module that reconstructs what the broker's netted positions cannot say. `telemetry/journal.py` stays put: it is the record the panel reads, not the agent's own recall. |
| VI. Test first | **deviation** | See below. |
| VII. No false diagnostic | yes | A region `__init__.py` that describes a job the module does not do is a diagnostic that states something false about the code. Hence requirements 2 and 6 together: the prose says what belongs, and a test holds it to that. |
| VIII. No stray English | no | Python surface. |
| IX. Testable placement | yes | The point of the feature. |

**Verdict:** pass with noted deviation.

**The deviation.** Ten of the eleven modules are moved unchanged, and a test written
first against moved code would pass before the move — the exact failure Article VI
exists to prevent. So: move, then confirm the suite is green at the same count, which
is the evidence that nothing changed.

The one piece of genuinely new behaviour — `tests/agent/test_regions.py`, which pins
that every module is in a region and every region declares itself — is test-first with
no exception, because there is nothing to move.

## Shape

Four regions, chosen by what a module *is* rather than what it touches:

| Region | Holds | The question it answers | Does not hold |
|---|---|---|---|
| `cortex/` | `llm.py`, `committee.py`, `proposal.py` | what should we do? | anything deterministic that decides an order — that is `gates/` |
| `cerebellum/` | `loop.py`, `manager.py` | how is the sequence run? | the reasoning it invokes, or the rhythm it runs on |
| `brainstem/` | `schedule.py`, `lock.py`, `breaker.py` | should we be running at all? | anything that reasons; these three override deliberation rather than take part in it |
| `hippocampus/` | `ledger.py`, `soak.py` | what happened, and what are we holding? | the panel's view of the record — that is `telemetry/` |

`run.py` stays flat: it is the entrypoint, and HAL keeps `server.py` outside every
region for the same reason.

The `cortex/` and `brainstem/` names are also the two that explain a pairing the flat
layout hid. `breaker.py` sits beside `lock.py` because both are reflexes that stop the
organism — one on a drawdown, one on a second process — and neither consults anything.
`proposal.py` sits beside `llm.py` because the schema is the narrow opening the model
speaks through, not a separate concern.

## What gets tested, and where

| Behaviour | Test file | Why there |
|---|---|---|
| Every agent module is in a region; no strays | `tests/agent/test_regions.py` | New. The only thing that can see a file dropped in the wrong place. |
| Every region declares what it is for | `tests/agent/test_regions.py` | An undocumented region is the metaphor decaying into folders. |
| Regions do not reach across each other in the wrong direction | `tests/agent/test_regions.py` | `brainstem/` importing `cortex/` would mean a reflex that waits for deliberation. |
| The entrypoint path is unchanged | `tests/test_cli_entrypoints.py` | Already asserts every module `start.sh` dispatches to is importable. |
| Nothing else changed | the existing 1410 | Same tests, same count, green before and after. |

## Risks

- **A stale `__pycache__` satisfying an old import path**, hiding a missed rewrite.
  Cleared as part of the move.
- **A region docstring that drifts** from what the region holds — the same rot as a
  stale diagnostic. `test_regions.py` pins the membership; the prose is reviewed with
  it.
- **The metaphor being stretched** by the next module that does not fit any region.
  That is the signal to add a region or to question the module, and the `__init__.py`
  files say what does *not* belong precisely so that argument has somewhere to start.
