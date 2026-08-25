# HAL Street

An autonomous options trading agent built on Alpaca. The model proposes; deterministic gates dispose.

Submission for the Alpaca AI Trading Agents Hackathon (co-hosted with lablab.ai), main challenge
**Options Alpha Agents**. Runs entirely in Alpaca's paper trading environment.

---

## The idea in one paragraph

Most LLM trading agents let the model decide *and* execute. HAL Street splits those. A scanning
loop surfaces candidate option structures from a rules-based strategy engine; the LLM reasons over
them, ranks them, and writes a structured trade proposal; every proposal then passes through a
layer of deterministic risk gates written in plain Python — no model in the loop — before an order
is ever constructed. If a gate rejects, the trade dies, and the rejection reason is logged as part
of the run journal. The model can be wrong, hallucinate a strike, or get talked into something
stupid; it still cannot put on an undefined-risk position or exceed a per-underlying cap.

## Hackathon requirements → where they live

| Requirement | Implementation | Module |
|---|---|---|
| Autonomous AI trading agent | Scan → propose → gate → execute → manage loop, runs unattended on a schedule | `agent/` |
| Alpaca MCP server *or* CLI | All broker interaction goes through Alpaca's MCP server; nothing calls the REST API directly | `execution/` |
| Options trading | Defined-risk multi-leg structures only (credit spreads, iron condors, calendars) | `strategy/` |
| Paper trading environment | `ALPACA_ENV=paper` enforced at startup; a gate refuses to run against live keys | `gates/` |
| Demonstrable P&L | Per-trade and cumulative P&L journal, exportable for the demo | `telemetry/` |
| Fresh account, $100k balance | Enforced by preflight; judged run refuses a dirty account | `scripts/preflight.py` |
| One-page write-up | AI logic / risk gates / Alpaca infrastructure | `docs/WRITEUP.md` |
| Build in public (extra) | Five-post plan, links logged as you go | `docs/BUILD-IN-PUBLIC.md` |

## Architecture

```
  market data ──► strategy engine ──► candidate structures
                  (deterministic)              │
                                               ▼
                                      ┌─────────────────┐
                                      │   LLM agent     │  ranks, sizes, writes
                                      │  (proposal)     │  a structured proposal
                                      └────────┬────────┘
                                               │  TradeProposal (typed)
                                               ▼
                                      ┌─────────────────┐
                                      │  RISK GATES     │  deterministic, no model
                                      │  pass / reject  │  reject → journal, stop
                                      └────────┬────────┘
                                               │
                                               ▼
                                    Alpaca MCP ──► paper account
                                               │
                                               ▼
                                    position manager (rolls, closes, expiry)
```

The boundary that matters is the one between the proposal and the gates. Everything above it is
probabilistic. Everything below it is auditable.

## Layout

```
src/halstreet/
  agent/        LLM loop, prompt construction, proposal schema
  gates/        deterministic risk gates — the safety layer
  strategy/     options strategy engine: structure construction + ranking
  marketdata/   chains, quotes, IV, greeks
  execution/    Alpaca MCP client, order construction, fills
  telemetry/    run journal, P&L tracking, competition scoring export
  voice/        speech in/out — demo surface, not required for autonomy
apps/desktop/   Tauri + React control panel and approval UI
apps/claude-skill/  optional conversational control surface — NOT the agent (see below)
scripts/        one-off runners, backfills, competition harness
tests/          gate tests are the ones that matter — see docs/TESTING.md
```

## Why this is a service, not a chat plugin

The competition scores an *autonomous* agent over a live window. A chat plugin only runs when a
human is in a session typing, which fails the requirement outright. So the agent is a headless
scheduled process that consumes Alpaca's MCP server as a client.

`apps/claude-skill/` is a second, optional surface on top of the same internal API — ask the agent
what it holds, why a proposal was rejected, close everything. Good for the demo video. Cut it
first if time gets short.

## Running it

```bash
cp .env.example .env          # fill in paper keys
uv sync                       # or: pip install -e ".[dev]"
python -m halstreet.agent.run --dry-run     # scan + propose, submit nothing
python -m halstreet.agent.run               # full loop, dev paper account

# judged run — refuses to start unless the account is fresh and at $100,000
python -m scripts.preflight --env comp
python -m halstreet.agent.run --env comp
```

## Status

Scaffold. See `MIGRATION.md` for what gets pulled from HAL and TradeScans, and what has to be
written new.
