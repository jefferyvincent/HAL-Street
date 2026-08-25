# Migration plan

Two existing codebases feed this repo. Neither drops in whole.

- **HAL** — ~17,600 lines of Python across 46 modules. Local voice agent, Alpaca-connected,
  deterministic risk gates, browser approval modal, Tauri/React frontend.
- **TradeScans** — sunsetted FastAPI/Python service. The valuable part is the options strategy
  engine that ranks structures for a symbol.

The goal is not to merge two apps. It is to take the *one good idea* from each and leave the rest.

---

## From HAL

| Bring | Into | Notes |
|---|---|---|
| Risk gate layer | `gates/` | The crown jewel. Needs extending for options — see below. |
| Agent loop + tool-call plumbing | `agent/` | Strip anything that talks to Alpaca directly; it goes through MCP now. |
| Approval modal | `apps/desktop/` | Keep for the demo. Autonomy is judged, so approval must be *optional*, not required. |
| Voice in/out (faster-whisper, XTTS) | `voice/` | Demo value only. Do not let it block the autonomous path. |
| Tauri/React frontend | `apps/desktop/` | Trim to: positions, proposals, gate decisions, P&L. |
| Config / secrets handling | root | Re-key for paper-only. |

**Leave behind:** the two local Ollama models. The competition runs against a live market on a
schedule; a local model on a tower that has to be awake is a liability. Move inference to a hosted
model, keep the local path as a fallback flag.

## From TradeScans

| Bring | Into | Notes |
|---|---|---|
| Options strategy engine | `strategy/` | This is the reason to raid TradeScans at all. |
| Structure construction (spreads, condors, calendars) | `strategy/` | Verify strike/expiry selection against Alpaca's chain format. |
| Ranking / scoring logic | `strategy/` | Was tuned for human browsing. Re-tune for unattended selection. |
| Greeks + IV calculations | `marketdata/` | Check whether these were computed locally or pulled from a vendor. |

**Leave behind:** FastAPI service layer, credit/IAP billing, App Store plumbing, newsletter and
marketing code, user accounts, the message board. All of it is product scaffolding around the
engine. None of it earns a point in this competition.

## Has to be written new

1. **Alpaca MCP client** (`execution/`). HAL calls the REST API today. The rules require MCP or
   CLI. Wrapping HAL's existing call sites is the smallest change that satisfies it — HAL's tool
   boundary is already the right shape for MCP.
2. **Options-aware gates** (`gates/`). HAL's gates almost certainly reason about share quantity and
   notional. Options need new ones:
   - defined-risk only — reject any structure with unbounded loss
   - max loss per position, and as a share of account equity
   - per-underlying and portfolio-level concentration caps
   - DTE floor (no holding short gamma into expiry week)
   - net short delta / net vega bounds at the portfolio level
   - assignment risk check on short legs near the money
   - liquidity floor: open interest, volume, and bid/ask width per leg
   - paper-environment assertion — refuse to construct an order against live keys
3. **Position manager** (`agent/`). Judged on P&L over a window, so exits matter more than entries.
   Profit-target and stop rules, roll logic, forced close before expiry.
4. **Run journal + P&L export** (`telemetry/`). You will need this for the demo video and for any
   claim you make about performance.

## Suggested order

1. MCP client + paper-mode assertion — proves rule compliance early
2. Strategy engine ported, callable, tested against a live chain
3. Options gates, with tests written *first* — this is the differentiator
4. Agent loop wiring scan → propose → gate → execute
5. Position manager
6. Telemetry, then frontend trim, then voice
7. Demo video

## One thing to settle before the first commit

TradeScans was built with a co-founder (Tyler). Hackathon submissions typically require you to
warrant that you own or are licensed to use the code you submit, and there's a prize pool attached.
Worth a short, friendly message to Tyler confirming he's fine with the engine being reused here —
before it's in the git history, not after.
