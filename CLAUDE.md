# HAL Street

An autonomous options trading agent on Alpaca. The model proposes; sixteen
deterministic gates dispose. A Python agent writes an append-only journal; a React
panel reads it and never writes anything.

## Where the rules are

This file routes. It does not govern.

| You are editing | The rules are in |
|---|---|
| `src/halstreet/`, `tests/`, `scripts/` | [`src/halstreet/CLAUDE.md`](src/halstreet/CLAUDE.md) |
| `apps/desktop/src/` | [`apps/desktop/CLAUDE.md`](apps/desktop/CLAUDE.md) |
| anything, ever | [`.specify/memory/constitution.md`](.specify/memory/constitution.md) |

The two surface files are deliberately different. Python is a trading system whose
failures are silent and expensive; the panel is a read-only view whose failures are
visible and cheap. Do not import one's conventions to win an argument in the other.

## How work gets done here

Two methods, composed rather than stacked. **Spec Kit supplies the artifacts and the
phase gates — what exists and what must be true before the next step. BMAD supplies
the roles — who is thinking, and in which hat.** Neither is decorative: the phase gate
is a real check with a real verdict, and the roles are real subagents in
`.claude/agents/`.

```
  Constitution ──> Specify ──> Plan ──> Tasks ──> Story ──> Implement ──> QA
   (standing)      Analyst    Architect   SM       SM         Dev        QA
                     PM
                     │           │         │        │          │          │
                  spec.md     plan.md   tasks.md  stories/  the diff   verdict
```

| Phase | Command | Hat | Leaves behind | Gate to pass |
|---|---|---|---|---|
| Specify | `/specify` | Analyst, PM | `specs/NNN-slug/spec.md` | no open question blocks a requirement |
| Plan | `/plan` | Architect | `plan.md` | **Constitution Check** returns a verdict |
| Tasks | `/tasks` | Scrum Master | `tasks.md` | every requirement maps to a task |
| Story | `/story` | Scrum Master | `stories/NNN-*.md` | the story stands alone, no back-references |
| Implement | `/implement` | Dev | code + tests | the test failed before the code existed |
| Review | `/qa` | QA | verdict in the story | suite green, articles honoured |

Templates live in `.specify/templates/`. Specs live in `specs/`, one directory per
feature, numbered. `specs/001-python-cli-modules/` is the worked example — it is the
refactor that turned `scripts/` into importable modules, written up the way this
method expects.

### When to use it, and when not to

Full pass for anything that changes behaviour, adds a gate, moves a module boundary,
or puts a new number on the panel.

Skip to `/implement` with no ceremony for: a typo, a comment, a rename with no
callers outside the file, a test for behaviour that already exists. The method is
here to stop silent breakage in a system that trades money — it is not here to make a
one-line fix cost four documents. Say which you are doing and why.

### The two rules that survive skipping the ceremony

1. **The failing test comes first.** Always, both surfaces, no exceptions worth
   arguing for. Constitution VI.
2. **Green before done.** `pytest` and `npm test`. Reporting unfinished work as
   finished is worse than not doing it.

## Running it

```
./install.sh                 build .venv, install halstreet
./start.sh                   the scheduled loop (paper, dev account)
./start.sh test              pytest
./start.sh panel             read-only dashboard on :8787
./start.sh report            P&L, gate counts, drawdown
./start.sh soak              a session, then a coverage table
./start.sh preflight --env comp
```

The panel is served from `apps/desktop/dist`, which is a **build artifact**. Editing
`apps/desktop/src` changes nothing on `:8787` until `cd apps/desktop && npm run build`
— or run `npm run dev` on `:1420` for hot reload with the Python server left running
underneath. This has cost real debugging time; it is in the panel's rules too.
