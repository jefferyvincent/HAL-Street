# src/halstreet — rules

This is a trading system. Its failure mode is not a broken layout; it is a number that
is quietly wrong on a Tuesday afternoon while nobody is looking. Every rule below
exists because that already happened, or because it was one commit away.

The panel next door has its own rules and they are not these. Do not carry a
convention across the boundary to settle an argument.

Everything here sits under [the constitution](../../.specify/memory/constitution.md),
which outranks it.

---

## 1. `scripts/` parses arguments. `src/halstreet/` decides things.

A file under `scripts/` may contain: an `argparse` parser, a `print`, an
`asyncio.run`, and an exit code. Nothing else. Every one of them is four lines long
and delegates to `halstreet.cli.<name>`.

The reason is not tidiness. `scripts/soak.py` once held the coverage logic, and the
test that covered it had to do this:

```python
_spec = importlib.util.spec_from_file_location("soak_script", ROOT / "scripts" / "soak.py")
soak = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(soak)
```

Three lines of import machinery to reach a function, because the function was not in
a package. That ceremony is the design telling you where the code belongs.

The layering, and it goes one way only:

```
scripts/x.py          argv, exit code                    (no logic, no imports beyond one)
halstreet/cli/x.py    parser, defaults, printing         (no domain decisions)
halstreet/<domain>/   the decision, pure where possible  (no argparse, no print)
```

A domain module never imports from `cli/`. A `cli/` module never contains a rule you
would want to assert. If you are about to write `if` inside `cli/` about anything
other than a flag, the thing you want is a function in the domain package.

**Printing is a `cli/` concern, and rendering is not printing.** `pnl.render()`
returns a string; `cli/report.py` prints it. That split is what lets a test assert on
the report without capturing stdout.

## 2. Where a module goes

| Package | Holds | Never |
|---|---|---|
| `agent/` | the agent itself, split into brain regions — see below | anything a gate needs |
| `gates/` | the sixteen accept/reject rules | network, wall clock, an LLM |
| `execution/` | broker boundary, order construction, paper assertion | strategy opinion |
| `marketdata/` | chains, symbols, news, events, patterns | a decision about a trade |
| `strategy/` | candidate structures, scoring, regime, maths | I/O of any kind |
| `telemetry/` | journal, P&L, pricing, the panel's server | anything the agent depends on |
| `cli/` | argparse and printing for each entrypoint | domain decisions |

Two tells that you have the wrong package: the import list points somewhere else, or
the test you want to write has to build a broker to reach a pure calculation.

### Inside `agent/`: brain regions

The names are literal, and they are HAL's — `hal/cortex` reasons, `hal/cerebellum`
runs the machinery, `hal/hippocampus` remembers. This codebase already borrows that
architecture directly: `cortex/committee.py` opens by saying it was adapted from
HAL's `cortex.committee`.

| Region | The question it answers | Holds |
|---|---|---|
| `cortex/` | what should we do? | `llm.py`, `committee.py`, `proposal.py` |
| `cerebellum/` | how is the sequence run? | `loop.py`, `manager.py` |
| `brainstem/` | should we be running at all? | `schedule.py`, `lock.py`, `breaker.py` |
| `hippocampus/` | what happened, and what are we holding? | `ledger.py`, `soak.py` |

`run.py` stays flat. It is the entrypoint, not a region's work — HAL keeps `server.py`
outside its regions for the same reason, and `python -m halstreet.agent.run` is in
`start.sh`, the README and the docs.

Pick a region by what the module **is**, not by what it touches. `breaker.py` writes a
file and is not a memory: a drawdown halt is a reflex, and the persistence is
incidental. Each region's `__init__.py` says what it refuses as well as what it holds,
because "what does not belong here" is the half that settles an argument.

One edge is enforced rather than described: **`brainstem/` may not import `cortex/` or
`cerebellum/`.** A kill switch with an opinion is slower than the thing it exists to
stop. `tests/agent/test_regions.py` holds that shut, along with the membership itself
— a `ledger.py` that drifted into `cortex/` would leave four directories that look
like an architecture and describe nothing.

Duplicating a function to keep a file standalone is a defect with a delay on it.
`scripts/verify_multileg.py` carried its own `parse_occ` with a comment saying the
real one "should be ported into `marketdata/`" — the port landed, the comment stayed,
and the copy went on parsing symbols its own way for months.

## 3. Test first, and the test names the behaviour

Same order as everywhere in this repo, and it is not negotiable:

1. **Write the test.** `test_unreadable_positions_do_not_read_as_zero`, not
   `test_run_checks`. The name is the specification.
2. **Run it. Watch it fail.** A test that passes before the code exists is testing
   nothing, and ten seconds finds out.
3. **Smallest code that passes.**
4. **Whole suite**, not the one file.

Tests mirror the package: `src/halstreet/execution/preflight.py` →
`tests/execution/test_preflight.py`. Say *why* in a docstring wherever the answer is
non-obvious — for the gates and the P&L maths these tests are the only written
statement of what the numbers mean, and several of them open by describing the bug
they exist to prevent. Keep doing that.

### What has to be covered

Every branch a person could get wrong: the empty case, the null case, the zero case,
the sign, the boundary — and for anything that reads a broker payload, **the shape we
did not expect**.

Every gate has a test that proves it *rejects*. A gate tested only on the happy path
is decoration (`docs/TESTING.md` lists the adversarial cases).

### The suite is offline, by construction

No test reaches the network. The broker sits behind an MCP client that tests stub, the
clock is injected, and `addopts = -q --strict-markers`. A slow suite is therefore a
signal rather than a fact of life. A test that needs a live account is not a test; it
is `./start.sh soak`, and its offline twin is `tests/agent/test_soak.py`.

## 4. "I could not tell" is not "zero"

The single most repeated bug in this codebase. A broker payload in a shape we do not
recognise, a file that will not parse, a quote that never arrived — each has a
truthful answer, and it is `None`, not `0` and not `[]`.

`preflight._rows()` returns `None` for an unrecognised payload precisely so the check
above it can fail rather than report an empty account as clean. The panel is full of
the same distinction: "priced live" against "priced 4m ago", `unpriced` against `$0`.

Anything that prints, logs or returns a diagnostic must be able to say it does not
know. Constitution VII.

## 5. Money, time, and secrets

- **`Decimal`** for every price, strike, credit, equity and P&L, parsed early and kept.
  A `float` in a money path is a defect even when it happens to come out right.
- **`clock.today()` / `clock.now()`**, never `date.today()`. Nine call sites once asked
  the host's calendar a question about the exchange; ruff's `DTZ` rules now catch it.
  Read the docstring in `clock.py` before you reach for `ZoneInfo`.
- **Never `source` the `.env`**, and never log a key. `config.load_env()` parses it.
  The paper assertion reads the account number the broker returned, not the flag we
  set — `execution/paper_assert.py`.
- **`paths.py` owns every location** the agent writes. A literal path in a module is a
  second claim about the filesystem to keep in sync with the first.

## 6. Lint is a stated contract

`pyproject.toml` selects its ruff rules explicitly and comments every ignore with the
reason. Do not add a bare `# noqa`; either the rule is right and the code changes, or
the exception has a sentence explaining itself. `ruff check .` clean, same standard as
green tests.

## 7. Comments carry the reason, not the mechanism

The house style, and it is worth keeping. A comment here explains why the obvious
thing is wrong — the day two soaks shared a journal, the reason an enum is not a
`StrEnum`, the reason an import is deferred. It does not restate the line beneath it.

When you remove code, the comment explaining why it went is worth more than the code
was.

---

## Working on a change

Follow the method in the [root CLAUDE.md](../../CLAUDE.md): `/specify` → `/plan` →
`/tasks` → `/story` → `/implement` → `/qa`. `specs/001-python-cli-modules/` is a
worked example on this surface.

Skip the ceremony for a typo or a comment. Never skip the failing test.
