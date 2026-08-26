# Migration plan

Two existing codebases feed this repo. Neither drops in whole.

- **HAL** — 20,179 lines of Python across 51 files, though 6,833 of that is a single `server.py`.
  The `hal/` package proper is ~13,300 lines across 49 modules. Local voice agent,
  Alpaca-connected, deterministic risk gates, and **two** frontends: a Tauri 2 + React 18 +
  Vite + Tailwind + Zustand desktop app in `app/`, and a separate hand-written 3,670-line
  `static/index.html` served by `server.py`.
- **TradeScans** — sunsetted **TypeScript** product: a React Native app (`tradescans`) plus Node
  API packages (`tradescans-api`, `OptionTradeScanAPI`) and an Ionic web UI (`tradescans-ui`).
  There is no Python in any of them. The valuable part is the options strategy engine.

The goal is not to merge two apps. It is to take the *one good idea* from each and leave the rest.

> **Correction, 2026-08-25.** An earlier draft of this plan described TradeScans as a "sunsetted
> FastAPI/Python service" and listed four items as net-new. Both were wrong, and in opposite
> directions: the TradeScans port is *harder* than assumed (it is a cross-language rewrite), and
> the MCP client and gate layer are *further along* than assumed. The tables below are checked
> against the source.

---

## From HAL

| Bring | Into | Notes |
|---|---|---|
| `sensory/risk.py` — portfolio circuit breakers | `gates/` | Far more complete than assumed. See below. |
| `cortex/rules.py` — per-trade gate | `gates/` | YAML-driven. **Re-key: the agent must not be able to write its own gate file.** |
| `peripheral/mcp_client.py` — generic MCP client | `execution/` | 546 lines, stdio + streamable HTTP + OAuth. Not net-new work. |
| `sensory/alpaca_data.py` — `occ_root`, `parse_occ`, `option_chain` | `marketdata/` | OCC symbol parsing already correct and tested in anger. |
| Agent loop + tool-call plumbing | `agent/` | Ollama-shaped at the tool-call seam — see the hosted-model note below. |
| `app/` — the Tauri desktop app | `apps/desktop/` | **This is the frontend. Not `static/index.html`.** 4,568 lines, 24 components; the panels already exist — see below. |
| `app/src/components/Hud.tsx` | `apps/desktop/` | The confirm↔autopilot toggle and kill-switch control. Autonomy is judged, so approval must stay *optional* — this already implements that. |
| ~~Voice in/out (faster-whisper, XTTS)~~ | — | **Cut.** Demo value only, and it never blocked the autonomous path because it was never started. The directory is removed rather than left as a stub. |
| `app/tailwind.config.ts` | `apps/desktop/` | Two scoped palettes: `hal.*` (red/amber on #050507, Michroma + Share Tech Mono) and `term.*`, a Bloomberg-style amber-on-black terminal skin. Keep both. |
| Config / secrets handling | root | Re-key for paper-only. |

**Leave behind:** the two local Ollama models. The competition runs against a live market on a
schedule; a local model on a tower that has to be awake is a liability. Move inference to a hosted
model, keep the local path as a fallback flag.

⚠️ That swap is not a config flag. `mcp_client.py` exposes tools to the model as
`mcp__<server>__<tool>` "to the Ollama model," and `server.execute_tool` dispatches on that
convention. Budget real time for the tool-call adapter.

### What HAL's gates already do

The earlier draft guessed they "almost certainly reason about share quantity and notional." They
do considerably more than that. `sensory/risk.py` (278 lines) already implements:

- order-rate throttle (N entries per rolling minute)
- max concurrent open positions
- gross exposure ceiling vs equity
- daily-loss kill switch, **latching** until manually reset
- per-underlying concentration cap, resolving OCC option symbols via `occ_root`
- correlated-group cap — SPY/QQQ/IWM already counted as one bet, not three
- volatility-regime scaling that contracts every ceiling as realized vol climbs its trailing-year
  percentile

It is also **entries-only by design**, so exits are never blocked even with the kill switch
latched. That is exactly the right shape for a judged P&L window, and it is not an accident worth
re-deriving.

Two defects to fix before this can back the claim in the README:

1. **`cortex/rules.py` reads its gate from `Rules/trading-rules.md` in the vault.** The README
   says gates "cannot be modified by the agent at runtime." If the agent can write to the vault,
   that sentence is false. Hash-pin the file at startup and assert the hash before each gate
   evaluation, or mount it read-only for the judged run.
2. **`sensory/risk.py` holds counters, the equity baseline and the kill-switch latch in
   module-level process state.** A scheduled per-invocation process re-baselines and clears the
   latch on every run — the daily-loss halt would never survive to do its job. Persist it.

### The frontend, and why it is not TradeScans'

Settled: **keep HAL's `app/`; do not adopt TradeScans' design.**

TradeScans has no design language to inherit. `constants/theme.ts` is the unmodified Expo starter
file — boilerplate docstring, default teal/white tints. `components/ui/` is twelve files of stock
scaffolding (Button, Card, Input, Select, DatePicker, tooltips). The only real customisation in
its Tailwind config is one cool-gray ramp. Against that, the carrying cost is React Native 0.81 +
Expo 54 + NativeWind + react-native-web and roughly 45 RN/Expo dependencies, IAP, AdMob, LogRocket
and push notifications among them — a stack that reaches a desktop panel only by dragging Metro
and react-native-web behind it.

HAL's `app/` already is the trim list:

| Trim target | Already exists |
|---|---|
| positions | `PositionsPanel.tsx` (448) + `PositionChartModal.tsx`, `PositionSizing.tsx` |
| proposals | `TradeIdeasPanel.tsx` (108) |
| P&L | `TelemetryPanel.tsx` (124) |
| gate decisions | — the one genuine gap |

`McpPanel.tsx` (312) is already an MCP surface, and `Hud.tsx` already carries the
confirm↔autopilot toggle and kill switch. The panel talks to the backend over plain HTTP at
`localhost:8000`, so repointing it is a base-URL change, not a rewrite.

Take exactly two things from TradeScans, as reference for a rewrite rather than as drop-ins —
both are React Native source:

- `strategy-engine/PnlChart.tsx` — payoff diagrams. HAL uses `lightweight-charts` for price
  series and has nothing for structure P&L curves. Pairs with the `pnl-curve.ts` port.
- `positions/open-position-card.tsx` and `open-position-analysis-modal.tsx` — multi-leg position
  display. HAL's `PositionsPanel` is single-leg-shaped, the same way its broker is.

**Leave behind:** everything else in `tradescans-ui` and the Expo app shell.

## From TradeScans

Everything here is **TypeScript being rewritten into Python**, not ported. Size the work
accordingly.

⚠️ `hal/cerebellum/option_strategy.py` already claims to be "ported from TradeScan." It is — but
from `utils/strategy-screener.ts`, a 239-line bias × IV lookup table returning ranked strategy
*names* with prose rationale. It builds no structures, prices nothing, and reads no chain. It is
not the engine. Treat it as a labelling layer and keep it for the write-up's plain-English
rationale; do not mistake it for the thing below.

The engine is `tradescans/src/services/strategy-engine/` — 15 modules, ~2,300 lines:

| Bring | Into | Notes |
|---|---|---|
| `strategy-builders/` (13 files) | `strategy/` | vertical call/put, iron-condor, calendars, diagonals, straddle, strangle, long call/put, covered-call. **Check leg counts against the 4-leg ceiling.** |
| `candidate-generator.ts`, `strike-selector.ts` | `strategy/` | Verify strike/expiry selection against Alpaca's chain format. |
| `scoring.ts`, `profile-config.ts` | `strategy/` | Was tuned for human browsing. Re-tune for unattended selection. |
| `liquidity-gate.ts` | `gates/` | Goes in `gates/`, not `strategy/` — it is a rejection rule, and it belongs on the auditable side of the boundary. |
| `pop-calculator.ts`, `pnl-curve.ts` | `strategy/` | Needs local theoretical pricing at hypothetical spots — so the Black-Scholes port survives even though live greeks come from Alpaca. |
| `iv-rank.ts` | `marketdata/` | IV percentile vs trailing range. Alpaca gives spot IV, not rank; this still has to be computed. |
| `position-monitor/` (~590 lines) | `agent/` | `health-check.ts` + `book-metrics.ts` map directly onto the position manager listed as net-new below. Raid it. |

Resolved open question: greeks and IV were computed **locally** — Black-Scholes with a Newton IV
solver (`black-scholes.ts`, `bs-iv-solver.ts`, `greeks-enrichment.ts`, ~425 lines). No vendor
dependency. Alpaca returns greeks and IV on its chain snapshots, so **for live quoting, prefer
Alpaca and skip the port**. Port Black-Scholes only for the hypothetical-spot pricing that
`pop-calculator` and `pnl-curve` need.

Measured on a live SPY chain (2026-08-26, 1,322 contracts over a 20-day expiry window):

- **1,250 of 1,322 (94.6%) carry `greeks` and `impliedVolatility`.** ATM SPY 765C returned
  delta 0.5414, gamma 0.0144, theta -0.2230, vega 0.8703, IV 0.126.
- **72 do not, all deep ITM or OTM** — strike/spot from 0.49 to 1.20. These are contracts whose
  price is essentially all intrinsic or all zero, where inverting Black-Scholes for IV is
  ill-conditioned. Not a problem for defined-risk structures near the money, but it *is* a gate
  concern: the delta and vega gates must **fail closed on a missing greek**, never skip the check.
  A proposal whose legs have no greeks is a proposal that cannot be risk-assessed.
- **0DTE contracts have no greeks at all.** Per Alpaca staff, Black-Scholes carries
  time-to-expiry in the denominator, so at same-day expiry the greeks are indeterminate rather
  than merely unavailable. `MIN_DTE=7` already excludes this, which means the DTE floor is
  quietly doing double duty — it is a risk gate *and* the thing that guarantees the greeks the
  other gates depend on actually exist. Worth stating in the write-up.

⚠️ **The account has no OPRA agreement.** Requesting `feed=opra` returns HTTP 403; the data above
came from the free `indicative` feed, which is the default. Indicative quotes are not the official
OPRA consolidated feed, so fills in paper may diverge from what a real NBBO would give. This is
acceptable for a paper-only competition but must be stated plainly in the write-up rather than
discovered by a judge.

**Leave behind:** credit/IAP billing (`aiCredits.ts`, `promoCode.ts`), App Store plumbing,
newsletter and marketing, user accounts (`users.ts`, `follows.ts`, `userBlocks.ts`), the message
board (`posts.ts`, `commentImages.ts`), all seven broker CSV parsers, and the profile taxonomy in
`STRATEGY_ENGINE_PLAN.md` — five risk profiles × two overlays is a product surface for humans
choosing a risk appetite. This agent has exactly one risk appetite and it is written in `gates/`.

There is no FastAPI service layer to leave behind. There never was one.

### Done: the strategy engine, and what changed on the way across

Ported into `strategy/` — `blackscholes.py`, `indicators.py`, `regime.py`, `bias.py`,
`pop.py`, `profiles.py`, `scoring.py`, and `candidates.py` rewired onto them. The
placeholder `score()` is gone; ranking is now the six-term weighted blend, and every
candidate carries its own breakdown into the journal.

Six things did not survive the crossing intact, each for a measured reason:

- **The indicators are computed, not fetched.** TradeScans made one HTTP call per
  indicator to a vendor. Alpaca has no indicator endpoint, so `indicators.py`
  computes SMA/EMA/RSI/MACD from the daily bars we already pull. Better than what it
  replaces: one request feeds all five, the conventions are visible in the file
  rather than in someone's docs, and the numbers are reproducible from the recorded
  closes. Wilder's RSI, SMA-seeded EMAs, aligned MACD series.
- **HV rank is still not IV rank, and now says so everywhere.** `Regime.is_proxy` is
  True and unconditional, and the journal stamps `regime_source: realized_vol_proxy`
  on every record. The two diverge exactly when it matters — before an event, implied
  climbs while realized has not moved — which is why the regime is one weighted term
  and not a gate.
- **Directional structures are classified exactly.** The vendor listed
  `vertical_call` in *both* the bullish and bearish sets, because a vertical there
  might be credit or debit and the type alone did not say. Here it does, so the bias
  term stopped being a coin flip for two thirds of the menu.
- **Iron condor POP uses both shorts' own IVs.** TradeScans passed one volatility into
  a two-sided calculation, which ignores skew; index put skew is steep enough that
  the downside tail is materially fatter. On a live SPY condor the difference was
  50.4% against 46.1%.
- **The mid-dependent spread rule was dropped.** Below a $10 mid the vendor capped
  spreads in dollars rather than percent. Sound rule, wrong universe: sampling the
  live 45-DTE SPY/QQQ/IWM chains at every delta and width this agent builds, the
  widest leg quoted 5.0% and the cheapest cost $1.22 — it would never have fired. And
  it would have made the pre-filter looser than `liquidity_floor`, manufacturing
  guaranteed rejections, which is the exact failure the pre-filter exists to prevent.
- **`ultra_aggressive` lost its naked shorts.** `defined_risk_only` rejects an
  unhedged short leg whatever profile built it. What survives is a wider delta band
  and a hunger for reward/risk, which is the honest remainder.

Two additions with no vendor ancestor, both from watching it run:

- **A viability filter.** A live QQQ 710/708 put spread offered $14 of max gain
  against $32.50 of one-way entry slippage. Every gate passes it — they judge risk,
  not edge. `viable()` now refuses to offer a structure whose entry cost exceeds its
  best case.
- **Menu diversification.** A straight top-6 collapsed: under a bullish read the six
  best-scoring SPY candidates were all put credit spreads on the same 0.45-delta short
  strike, differing only in wing width, because the bias term is worth 25 points and
  sweeps every directional structure up at once. `diversify()` fills the menu
  round-robin by kind. The top pick is unchanged and order within a kind is still
  score order; what changes is that the model always sees a real alternative.

**The profile can never loosen a gate.** `EffectiveFloor.compose` takes the stricter
of profile and `.env` on every dimension, and reports the disagreement in *both*
directions at startup. The second direction matters more than it sounds: the moderate
profile's ported volume floor of 25 silently overrode a deliberate
`MIN_DAILY_VOLUME=10` and starved QQQ of candidates entirely, and it surfaced as "no
candidates built from the chain" rather than as anything mentioning volume.

**Resolved: the volume floor was measuring the wrong thing.** Daily volume was the
binding constraint and nothing else was close. Sweeping the live 45-DTE chains with
everything else held fixed:

| volume floor | SPY | QQQ | IWM | short deltas reachable |
|---|---|---|---|---|
| 25 (as ported) | 9 | **0** | 1 | 0.20, 0.30, 0.50 |
| 5 (now) | 19 | 7 | 9 | 0.20, 0.30, 0.40, 0.50 |

Spread did nothing at all over the same sweep — 8%, 10% and 12% gave identical counts
— and open interest 250 → 300 moved a single candidate. So `MIN_OPEN_INTEREST` and
`MAX_BID_ASK_WIDTH_PCT` are unchanged; only volume moved.

The bias mattered more than the count. The further out of the money a strike sits, the
less it trades *today* — so a volume floor selects hardest against exactly the OTM
structures a premium-selling strategy is built on, and was quietly pushing the agent
toward near-the-money spreads at ~50% odds. The profile floors came down with it
(50/50/25/10/5 → 15/15/5/3/1), because `.env` alone could not fix this: strictest-wins
meant the ported 25 silently beat the configured 10, and the symptom was "no candidates
built from the chain" with nothing mentioning volume.

**Corrected: round-trip friction was quoted in the wrong unit, and it was suppressing
trades.** `MEASURED_ROUND_TRIP_USD = 73.40` was the *total* cost of the 2026-08-26
verification run — which opened, rolled and closed **three separate structures** across
5 orders and 16 leg-fills. That lump sum was being compared against a single
structure's per-contract max gain, and quoted to the model in the system prompt.
Decomposed into the round trips it actually was, at qty 1:

| structure | legs | round trip | per leg |
|---|---|---|---|
| Oct-16 765/770 call spread | 2 | −$15.00 | $7.50 |
| Oct-16 755/760/770/775 condor | 4 | −$23.00 | $5.75 |
| Nov-20 765/770 call spread | 2 | −$35.00 | $17.50 |

The Nov-20 spread is excluded as an outlier — 87 DTE, where the market is materially
wider than the 21-60 band this agent trades. `FRICTION_PER_LEG_USD` is now $7.50 per
leg per contract, so a two-leg spread costs ~$15 and a four-leg condor ~$30 round trip.
The old figure overstated friction roughly 4x on a condor, and the agent had been
declining trades on the strength of it — one live pass cited "a measured ~$73
round-trip cost… which alone eats over two contracts' worth of maximum gain."

Both sides now scale with quantity, which makes the warning size-invariant. That is the
point: a structure whose edge does not cover its own friction is not rescued by trading
more of it.

**Added: an explicit `action: "pass"`.** Two cycles failed with `qty: 0` and an empty
`legs` array. Not model flakiness — the prompt said *"if no candidate is worth taking,
propose nothing"* against a schema requiring a priced structure, and both cannot be
satisfied. Declining is now a first-class outcome, counted separately from proposals and
from failures, and it must carry a rationale because on a pass that rationale is the
cycle's only output.

Together these three changes took a scan from *two parse failures and one approval* to
*two approvals and one fully-reasoned pass*, with the model computing expectancy
against the corrected per-leg friction unprompted.

Not ported, and deliberately: `pnl-curve.ts` (the payoff maths already lives in
`marketdata/occ.py`), and the ten structure types the 4-leg ceiling and
`defined_risk_only` exclude. Probability functions for structures that can never be
submitted would be dead code pretending to be capability.

### Done: circuit breakers, and the panel

**Four gates that judge the situation rather than the proposal** — `gates/circuit.py`,
raided from HAL's `sensory/risk.py`. Gross-exposure and per-symbol caps were left
behind: `portfolio_risk_ceiling` and `underlying_concentration` already cover them and
measure defined risk directly rather than through market value.

`correlated_exposure` is the one with teeth, and it exists because the shipped default
universe walked straight into it. A live scan approved put credit spreads on SPY, QQQ
*and* IWM in one cycle — one bullish bet at triple size — and every existing gate
waved it through: `underlying_concentration` matches roots exactly, so three roots are
three separate names to it, and `portfolio_greek_bounds` only bites above 5,000
share-equivalents. The static group map is deliberate over a live correlation matrix:
it needs no data, cannot go stale mid-session, and is auditable by eye.

Two departures from HAL:

- **The latch is on disk, not in module globals.** This file listed HAL's
  process-local latch as a defect and it is now fixed: restarting the agent used to
  silently re-arm trading after the kill switch fired, and restarting is exactly what
  someone does when an unattended agent starts behaving oddly. A latch that dies with
  the process is not a latch. Unreadable state starts *halted* — the file exists to
  record that trading was stopped, so one we cannot read might say exactly that.
- **State lives in `agent/breaker.py`, not in the gates.** The gate layer is pure by
  contract; the gates read history off `GateContext.breaker` and never load it, so
  every one stays testable without a broker, a clock or a filesystem.

**The panel needed a backend nobody had noticed was missing.** This file said adopting
HAL's `app/` was "a base-URL change, not a rewrite" — true as far as it went, but HAL
Street has no HTTP server at all, so there was nothing to point at. Rather than import
HAL's React app and its build chain, `telemetry/server.py` is stdlib `http.server`
(no new dependency — a judge running `install.sh` should not wait on a web framework)
and `apps/desktop/index.html` is one self-contained file with no build step.

It is **read-only by design, not by omission**: no POST, no order route, no way to
clear the halt latch. A dashboard that can trade is a second path to the broker that
does not go through `gates/`, and the whole argument here is that exactly one such
path exists. Clearing a halt is a deliberate act at the CLI, visible in shell history,
not a button someone can hit twice. A test asserts the handler defines only `do_GET`.

### Done: the submit path, proven live

`DRY_RUN=false ./start.sh -- --once --submit --universe QQQ` on 2026-08-26. One
structure, opened and closed. `.env` was never edited — an existing environment
variable already wins over the file, which `config.load_env` documents and which is
the safer way to do this than toggling a safety flag on disk and hoping to remember.

Order `365deebd` — QQQ Oct-16 755/765 call credit spread. Limit −1.59, **filled
−1.60**. Verified end to end: order journalled with its id and status, ledger entry
written with legs, entry price and rationale, throttle stamped, and reconciliation
reporting the ledger and broker in agreement. Closed at +1.69 for a $9.00 round trip
on two legs — $4.50/leg, the cheapest of the three in-band observations and comfortably
inside the $7.50 estimate.

Two defects it surfaced, both invisible in dry runs:

- **Ledger writes were not durable at the point of mutation.** `record_open` and
  `record_close` mutated in memory and left persistence to the caller. The loop does
  call `save()`, so it was correct in practice — but an order accepted by the broker
  with no ledger record is an untracked position that reconciliation reports as a
  divergence forever, and the window between submission and the caller's next save is
  exactly where a crash would land. Both now persist immediately.
- **The ledger recorded limit prices, not fills.** Every downstream figure — realized
  P&L, the exit policy's percentage thresholds, the write-up's headline number — is
  computed from entry price, and the limit is by definition the *worst* price you were
  willing to take, so the bias ran one way. On one contract it was a dollar. Over a
  competition window it is the reported result. `refresh_fills` now backfills the real
  fill from `get_order_by_id` at the top of each cycle, before exits are judged, and
  journals the correction rather than making it silently. Order id is the only
  unambiguous source here: position `avg_entry_price` blends across structures because
  the broker nets legs.

### Done: the options buying-power gate

Prompted by Alpaca's Paper Trading Skill announcement, which lists "order preview with
buying power checks" among its five capabilities. Four of the five were already here
and built deterministically; that one was a genuine hole, and checking it produced a
number worth writing down:

    buying_power            $359,270      4x margin, for equities
    options_buying_power     $89,817      cash. This is what actually binds.
    equity                   $89,817

Every sizing gate in the project measured against **equity**. The broker does not —
options collateral comes out of `options_buying_power`, and those two agree only while
the book is flat. As positions accumulate, held collateral drains buying power while
equity stays put, so a ceiling expressed as a percentage of equity keeps approving
trades after the broker has stopped being able to accept them. The failure is not a
bad position; it is a wasted cycle ending in a rejection the journal files as
infrastructure error.

Collateral for a defined-risk structure is its max loss, so the gate reuses
`max_loss_per_contract` rather than modelling margin twice. A configurable reserve is
kept back: running buying power to zero leaves nothing to *close* with, and some exits
are debits.

**The skill itself was not adopted.** Its other four capabilities — restating strategy
logic, environment verification, lifecycle tracking, session artifacts — all exist
here already as deterministic Python, and a skill is a prompt. Moving the paper-mode
assertion from `place_structure` into agent instructions would relocate a hard
guarantee into the probabilistic layer, which is the one thing this project is built
not to do.

### Done: the console, conformed to the gate layer

The panel was rebuilt to a supplied terminal mockup, and the mockup turned out to be
right about something the first version got wrong. It grouped the fifteen verdicts into
**five families — contract 2, liquidity 2, defined risk 4, portfolio 3, circuit 4** —
which is exactly the five modules in `gates/`. The first panel sliced the chain
positionally (3/6/6); a positional slice mislabels every gate after an insertion, and
does it confidently.

So `GateResult` now carries `family`, stamped by `evaluate` from the gate's
`__module__` rather than declared per gate — the module *is* the grouping, and a
declared family is one more thing to forget when a gate moves file. It is stamped
even on a gate that raised, so a crashing gate still lands in the right place. The API
serves the whole chain and the active limits, so the panel's meter is drawn from what
is loaded rather than a hard-coded 2/2/4/3/4, and adding a gate changes the UI on the
next request with no second place to update.

Limits are shown read-only beside the environment variable you would have to edit,
because raising one is a human act outside the app. There is no override affordance and
no "approve as adjusted": a `Decision` is binary, gates never rewrite a proposal, and
the UI should not imply a state the type system does not have.

**A defect the mockup surfaced.** Building a genuine rejection for the screenshot meant
running the real chain over real chain data with an oversized proposal — and
`correlated-exposure` passed when it should not have. The cap read
`cap_positions * legs * qty`, so a proposal inflated its own ceiling faster than it
inflated its exposure: held contracts do not scale with the order, so a 1-contract
order was rejected while the same structure at 10 contracts passed. Backwards for a
concentration limit. Both it and `underlying-concentration` now scale with legs only,
and a test asserts the property directly — adding contracts can only move a structure
toward rejection, never away from it. With that fixed the demonstration proposal
rejects on 5 of 15 gates, `correlated-exposure` among them.

## Has to be written new

1. **Multi-leg order construction** (`execution/`). *Not in the earlier draft, and it is the
   critical path.* `hal/sensory/broker.py` is explicitly "equities + single-leg options"; nothing
   in HAL references `mleg`, `OptionLegRequest`, or a legs array. Every structure this project
   exists to trade is multi-leg. See the verification section below for the exact shape.
2. **Alpaca MCP wrapper** (`execution/`). Downgraded from "write a client." `mcp_client.py`
   already does transport, OAuth, discovery and caching. What is missing is a typed wrapper over
   `place_option_order` and the options-data tools, plus the paper assertion.
3. **Options-aware gates** (`gates/`). The portfolio-level and concentration gates exist; these do
   not:
   - defined-risk only — reject any structure with unbounded loss
   - max loss per position, and as a share of account equity
   - DTE floor (no holding short gamma into expiry week)
   - net short delta / net vega bounds at the portfolio level
   - assignment risk check on short legs near the money
   - liquidity floor: open interest, volume, and bid/ask width per leg
   - contract validation — every leg's OCC symbol must exist in the fetched chain
   - paper-environment assertion — refuse to construct an order against live keys
   - **leg-count ceiling — reject any structure over 4 legs before it reaches order construction**
   - **roll atomicity — reject any roll that cannot be expressed as one ≤4-leg order** (below)
4. **Position manager** (`agent/`). Judged on P&L over a window, so exits matter more than
   entries. Profit-target and stop rules, roll logic, forced close before expiry. Start from
   TradeScans' `position-monitor/` rather than from nothing.
5. **Run journal + P&L export** (`telemetry/`). `cerebellum/tradelog.py` (130 lines) is a starting
   point but is trade-level, not run-level. You need this for the demo video and for any claim you
   make about performance.

---

## Verified: multi-leg options through Alpaca MCP

Checked 2026-08-25 against alpaca-py 0.43.4 (installed in HAL's venv) and the official
`alpacahq/alpaca-mcp-server` source. **The architecture holds.** Details that constrain design:

**The tool.** `place_option_order` in `src/alpaca_mcp_server/overrides.py` — a hand-written
override, not one of the OpenAPI-generated tools, and the generated `postOrder` is excluded in
favour of it.

```python
async def place_option_order(
    qty: str,
    type: str = "market",
    time_in_force: str = "day",
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    position_intent: Optional[str] = None,
    limit_price: Optional[str] = None,
    client_order_id: Optional[str] = None,
    order_class: Optional[str] = None,
    legs: Optional[list[dict]] = None,
) -> dict
```

Each leg is `{"symbol": str, "ratio_qty": str, "side"?: str, "position_intent"?: str}`.
`order_class` is set to `"mleg"` automatically when `legs` is supplied.

Note every numeric field is a **string**. The typed wrapper must serialise deliberately —
`Decimal` in, exact string out, no float formatting anywhere near a strike or a limit price.

**Hard limit: 4 legs.** Enforced in the MCP override and independently in alpaca-py, which also
requires order-level `qty`, unique symbols across legs, and `side` or `position_intent` on each.

Target structures against that ceiling:

| Structure | Legs | Fits |
|---|---|---|
| Vertical call / put spread | 2 | ✅ |
| Calendar, diagonal | 2 | ✅ |
| Straddle, strangle | 2 | ✅ |
| Iron condor | 4 | ✅ exactly |
| Iron butterfly | 4 | ✅ exactly |

Legs may carry **different expirations**, so calendars and diagonals are genuinely available.

**Three consequences the plan has to absorb:**

1. **Condor rolls cannot be atomic, so condors do not roll.** *Settled — see the rule below.*
   Closing a 4-leg condor and opening a replacement is 8 legs, which no single order can express.
   It would decompose into sequential orders with real leg risk in the gap, and if the second
   rejects you are holding a half-unwound position no gate ever approved.

   **The rule: a roll is permitted if and only if it fits in one order — closing legs plus
   opening legs ≤ 4.** In practice that means 2-leg structures (verticals, calendars, diagonals,
   straddles, strangles) roll atomically as a single 4-leg order, and 4-leg structures (condors,
   butterflies) have no roll primitive at all. They close. Any re-entry afterwards is a fresh
   proposal that runs the full scan → propose → gate chain like any other.

   This is the conservative choice and also the more defensible one. The project's entire claim is
   that everything below the proposal boundary is auditable; an intermediate position that no gate
   evaluated would falsify that for the sake of an optimisation. Closing is always available and
   always safe, and a condor "roll" is economically close to two independent decisions anyway —
   gating them separately is more legible, not less.

   Enforced in `execution/structures.py:roll()`, which refuses to build the order at all, so a
   model that proposes a condor roll is stopped at construction rather than at the broker.
2. **Options Level 3 coverage rule.** Alpaca accepts an MLeg order "only if all its legs are
   covered within the same MLeg order." Roll construction has to satisfy coverage inside each
   individual order, which further constrains the decomposition above.
3. **The MCP server has no read-only mode and no environment assertion.** `place_option_order` is
   annotated `destructiveHint: True` and performs no paper/live check; `ALPACA_PAPER_TRADE`
   defaults to `true` but is an ordinary env var with nothing guarding it. The paper-environment
   gate **cannot be delegated to the MCP server** and must run on our side of the boundary,
   before the call. This is the single most important consequence of the verification: the thing
   that keeps the judged run legitimate is code we own.

**Also confirmed available:** the `options-data` toolset exposes `OptionChain`, `OptionSnapshots`
(greeks + IV), `OptionLatestQuotes`, `optionBars`, `OptionTrades`. Enough to feed the strategy
engine and the liquidity gate without a second data vendor.

### Confirmed by live paper submission, 2026-08-26

Three orders placed against the dev paper account at the open. Everything above held,
and two things came out of it that desk research could not have.

| Order | Legs | Result |
|---|---|---|
| Vertical 765/770C Oct-16 | 2 | filled, `mleg`, net debit 2.99 |
| Iron condor 755P/760P/770C/775C Oct-16 | 4 | filled, `mleg`, net credit 4.04 |
| Roll Oct-16 → Nov-20 765/770C | 4 | **filled**, `mleg`, net debit 0.37 |

**The 4-leg roll is accepted.** This was the one question research left open: Alpaca
accepts an MLeg order only if all legs are covered within that same order, and it was
not obvious a close-plus-open would satisfy that. It does. The roll rule — close legs
plus open legs ≤ 4 — is now validated rather than assumed, and 2-leg structures really
do roll atomically.

**Slippage is not the problem.** The condor filled at 4.04 against a 4.00 net mid, and
the vertical at 2.99 against 3.13 — i.e. essentially at mid on a 4-leg market order at
the open, with the widest single leg quoting 3.4%. Market orders on defined-risk SPY
structures are viable; the liquidity gate should still enforce the width floor, but the
fear that a 4-leg market order would be mauled does not survive contact.

**The sign convention is confirmed empirically.** The condor reported
`filled_avg_price = -4.04` for a credit received. Negative is credit, positive is debit,
exactly as the tool schema says.

**Round-trip friction is measured, not guessed.** Closing both structures as single
`mleg` orders (never legging out) completed the cycle: 5 multi-leg orders, 16 legs,
open → roll → close. Equity moved 89,900.19 → 89,826.79, so the whole exercise cost
**$73.40** — about 0.08% of the account — of which $73 is spread and $0.40 fees.

That number belongs in `telemetry/` and in the position manager's tuning: a profit
target set inside the round-trip cost is noise, not edge. It is also the honest
counterweight to the slippage result above — individual fills land at mid, but five
orders still add up.

⚠️ **Alpaca nets legs across structures into one position per contract.** After the
vertical and the condor both sold the Oct-16 770 call, the account showed a single
`SPY261016C00770000` position at **qty −2** — not two positions of −1 tagged to their
parent structures. The broker has no concept of which structure a leg belongs to.

This is the most consequential finding of the run and it reshapes two modules:

- **`agent/` position manager** cannot read its own state back from the broker. It must
  keep its own structure → legs ledger and reconcile against a flat, netted position
  list. "Close the condor" is a thing only our side knows how to express.
- **`gates/` concentration** must count net contract exposure per underlying, not open
  structures. Two structures sharing a short strike are one larger short, and a gate
  counting structures would score that as diversification.

It also means a partial fill or a manual intervention can silently desynchronise the
ledger from the account, so reconciliation is a first-class job, not a startup step.

## Suggested order

1. **Multi-leg order construction through MCP, against a live paper chain.** Ahead of everything
   else: it is the assumption the whole project rests on, the remaining unknowns need real keys,
   and it proves rule compliance early.
2. Paper-mode assertion, on our side of the MCP boundary
3. ~~Strategy engine rewritten TS→Python, callable, tested against a live chain~~ — done; see above
4. Options gates, with tests written *first* — this is the differentiator
5. ~~Fix the two defects in HAL's inherited gates~~ — process-local latch fixed (see above); the vault-writable rules file does not cross over: HAL Street has no runtime-editable rules
6. Agent loop wiring scan → propose → gate → execute
7. Position manager — roll rule already settled (≤4 legs per order; condors close, never roll)
8. Telemetry, then the panel. ~~Voice~~ and ~~the conversational surface~~ are cut — see above
9. Demo video

## Done: one config file

`.env.comp` is gone. There was never a good reason for it — the dev/comp separation was
already carried by the variable *prefix* (`ALPACA_*` vs `COMP_ALPACA_*`), which
`paper_assert.py` has read from the start. The second file added no guarantee on top of
that and cost a near-duplicate 135-line template to keep in sync; `diff .env.example
.env.comp.example` was 17 lines, all of them comments, and one of those comments existed in
only one of the two files. That is the drift arriving on schedule.

Collapsing it also recovered a check the split had hidden. Two files could enforce "the comp
file exists"; they could not see the mistake that actually ends a competition entry, which is
the dev account's keys pasted into the `COMP_` slots. Nothing downstream catches that — the
credentials are real, the environment is paper, every gate passes, and the judged run trades
the development account. In one file it is a comparison, and `load_env` now refuses it
outright. `start.sh` refuses it too, before Python starts.

`load_env`'s account check is tied to `required`, so `report --offline` still runs with no
credentials at all — it reads the journal and the ledger and never opens a broker connection.

New: `tests/test_config.py`, nine tests. The old property was "a comp run reads a different
file"; the new one is "a comp run reads different *names*," which is stronger and less
self-evident, so it is pinned rather than assumed. Suite 351 → 360.

The README had no configuration section at all — the thing the user actually noticed. It has
one now, with the two-account table, and `## Running it` was rewritten around `./start.sh`
rather than the raw module paths.

## Done: the tabs are real, and no Vite

**The defect.** The chrome bar shipped JOURNAL and GATES as tabs — `cursor-pointer`,
hover state, the whole affordance — wired to nothing. They came straight from the mockup,
which has those screens; the implementation had only the console. This is the same lie as
an F1-PROPOSE button that does not propose, and the reason it survived is that it looks
finished. `meter()` was dead too — defined, never called — and is gone.

Both tabs now render. JOURNAL is the mockup's 4b: the full decision table, every record
with room for the whole rejection reason, where the right-hand tape truncates to one
column. Clicking a row selects that decision and drops you on the console, which already
*is* the 4c decision record — so 4c needed no new screen, only a way in. GATES is the
chain as loaded from the server, in evaluation order, grouped by family, each gate showing
how often it has actually rejected something (`pnl.rejections_by_gate`). A gate list nobody
can check against the run is decoration; this one is drawn from the same `ALL_GATES` the
agent evaluates and counted from the journal. No server change was needed — every field was
already in the snapshot.

Console keeps the rails, because the family meter and the tape both describe the *selected*
decision. The other two views take the full width rather than compete with a narrower copy
of themselves. `1` / `2` / `3` switch, and the footer advertises them because they exist.

**New: `tests/telemetry/test_panel.py`, 11 tests.** `test_server.py` proved the server has
no write route; nothing covered the page. Now: no `XMLHttpRequest`, `sendBeacon`,
`WebSocket`, `<form>`, or `method:` anywhere; every `fetch` a plain GET; every tab resolves
to a branch in the stage dispatch *and* every view function is reachable from a tab (both
directions — an unreachable view is as dead as an empty tab); no `cursor-pointer` in the
static markup, which is what makes the tab check sufficient; and the footer advertises only
bound keys. Verified by mutation: reintroducing a dead tab, a static clickable, and a POST
each fail the suite. 360 → 371.

## Decided: no Vite

HAL uses Vite because HAL earns it — React, TypeScript, Tauri, `lightweight-charts`,
WebSockets to FastAPI, a real `src/` tree. This panel is one 300-line file with ~150 lines
of vanilla DOM, no imports and no runtime dependency. Vite's job is resolving a module graph
and serving it with HMR; there is no graph.

Three specific costs, against no benefit:

1. **The audit gets weaker.** `telemetry/server.py` serves `index.html` byte-for-byte, so
   "prove the panel cannot trade" is *read the file* — which is exactly what the new tests
   do, as text. Under Vite the served artifact is a minified `dist/` bundle and the claim
   becomes "read the source and trust the build."
2. **Node moves from dev-only to required.** Today `build.py` is the one thing in the repo
   that wants npm, nothing at runtime runs it, and the CSS ships already inlined — clone and
   `./start.sh panel` works with no Node at all. Vite means Node on the judges' path, or
   committing `dist/` (which `.gitignore` excludes).
3. **A build step is a thing that breaks during a demo.**

The one real need — Tailwind's JIT, which cannot work without scanning — is already met by
`apps/desktop/build.py`, 80 lines, dev-only, writing the result back into the single file.

This changes if the panel grows charts, more views than tabs can carry, or Tauri packaging.
At that point the answer is not "add Vite" but "port it to HAL's stack," which is a
deliberate rewrite rather than a build-tool decision.

## Done: the panel is a real app

The single 300-line HTML file is gone. `apps/desktop/` is Vite + React + TypeScript + Tauri +
`lightweight-charts`, pushed over a WebSocket from FastAPI — HAL's stack, applied here.

**What actually changed on the Python side.** `telemetry/server.py` kept `snapshot()` and
swapped `http.server` for FastAPI: `GET /api/state`, `GET /`, mounted `/assets`, and `WS /ws`.
The socket watches the mtime *and size* of the journal, ledger and circuit files — size too,
because an append inside one mtime tick is otherwise invisible — and pushes a whole snapshot
when any changes, with a heartbeat in between. Measured: 0.5s from a file write to a push,
against the old five-second poll. `pnl.equity_series()` is new, returning `(ts, value)` pairs;
`equity_curve()` now derives from it. The chart needs the timestamps, because scans only run
while the market is open, and plotting equity against sample index would draw three sessions as
one continuous line.

**The socket is send-only, and that is the whole safety argument.** A WebSocket is duplex, which
makes it the one thing here that could quietly become a write path — a frame carrying
`{"action": "halt"}` is only dangerous if something reads it. Nothing does: `receive`,
`receive_json` and the `iter_*` family appear nowhere in the module, and the client never calls
`send`. That costs the usual disconnect detection, which is why the heartbeat is load-bearing
rather than cosmetic — a failed send is the only signal a client has gone. Verified against the
running server by sending `{"action": "clear_halt", "submit": true}` down the socket: accepted
by the transport, reached nothing, connection still healthy afterwards.

**Tauri adds no privilege.** No `#[tauri::command]`, no `invoke_handler`, `permissions:
["core:default"]`, and a CSP pinning `connect-src` to `127.0.0.1:8787`. Tauri's whole appeal is
the bridge it opens to native code, and that bridge is exactly what this must not have. The
desktop build is a nicer frame around the identical unprivileged page.

**Structure, per the requests during the build.** `views/` one file per screen; `components/`
presentational only; `hooks/` all derived state (`useDecisions`, `useGateFamilies`,
`useGateChain`, `useEquityChart`, `useShortcuts`, `useTabs`, `useStatus`, `useStrings`); `lib/`
pure functions with no React import; `stores/` zustand — `connection` holds the snapshot and has
no action that edits one, `ui` holds what you are looking at; `constants/` every string, colour,
icon path and repeated class. No `.tsx` file computes anything or spells a sentence.

Two things fell out of that discipline rather than being designed. Holding the selection as a
*timestamp* — an object reference would deselect on every push, an index would slide as records
arrive, and `l` for "latest" selects `null` so it keeps following. And `constants/strings.ts`
turned out to be worth more than translation: the sentences that say there is no override, that
limits are not editable here, that exits are never blocked are promises about behaviour, and
having them in one reviewable file beats finding them nine components apart.

**Tests: `test_panel.py` rewritten, 18 tests; `test_server.py` gained 2.** They read the sources
rather than running them — a real limit, and a deliberate trade: the invariants are structural
("this call does not appear", "this view is reachable"), they hold across the whole tree rather
than one code path, and they run in the Python suite with no browser, so they cannot be the
thing skipped on competition day. Two of them parse an AST or strip comments first, because the
server docstring and `lib.rs` both name the thing they refuse and a substring search cannot tell
a promise from a violation. Verified by mutation: an unrouted view, a client `POST`, a hardcoded
sentence in a view, and a `#[tauri::command]` each fail the suite. 371 → 380.

**One thing does not build here.** `cargo check` resolves all 429 crates and `cargo
verify-project` passes, but the Linux build stops at `webkit2gtk-4.1: not installed` — a system
package needing `sudo apt install libwebkit2gtk-4.1-dev`, which is not mine to run. Everything
up to that line is verified. The browser build is complete and serving.

**Also fixed:** `docs/WRITEUP.md` said the journal carries "all fourteen gate verdicts" while
naming fifteen gates twice in the same document.

## Correction: the Tauri shell does build, and install.sh now knows it

I reported that the desktop build stopped at `webkit2gtk-4.1: not installed`. That was wrong,
and wrong in an instructive way: this shell runs inside a Flatpak sandbox (VS Code's, on the
Freedesktop SDK runtime), which has its own `/usr` and does not have WebKitGTK. The host — the
actual Pop!_OS install — has had it all along. Asked through `flatpak-spawn --host`, `cargo
check` finishes in 10s and `cargo build` links a 187MB binary. Nothing was missing; the question
was asked in the wrong room.

`./install.sh --desktop` now owns that knowledge, so it is in one place rather than in a
paragraph someone has to remember:

- Package names for **apt, dnf, pacman and zypper**, plus the nothing-to-do cases (macOS uses
  the system WebKit; Windows has WebView2) and a link for anything else.
- A `sys` helper that runs detection **on the host** when we are sandboxed and the portal is
  reachable, so a library the host has never again reads as missing. The run announces it:
  `(inside a Flatpak sandbox — asking the host, not this runtime)`.
- It refuses to pretend a sandboxed shell can install host packages, and prints the command to
  run on the host instead.
- Rust is pointed at (`https://rustup.rs`), never installed behind someone's back.

It is a flag rather than the default because a repo installer should not reach for `sudo` unless
it was asked to. Everything else — agent, gates, CLIs, and the panel in a browser — installs
with no root at all. `--help` prints the header comment, so the two cannot drift.

Verified: the branch for each package manager was exercised with a stubbed PATH, and a full
`./install.sh` run ends green with 380 passing.

## Done: the repository root

Four things were wrong with it, and three of them were the same thing.

**Runtime state sat beside source.** `journal/` and `halstreet.log` in the root, mixed in with
`src/` and `tests/`. Everything the agent writes now lives under `var/` — `var/journal/` and
`var/log/` — which is the Unix name for variable program state. One `.gitignore` line covers it
and `rm -rf var/` is a complete reset.

**One fact was written down fourteen times.** The paths to the journal, ledger and circuit file
were default strings in fourteen `add_argument` calls across five files. `src/halstreet/paths.py`
owns them now, and `HALSTREET_VAR` moves the lot — for a mounted volume, a tmpfs, or a directory
per competition run. That made the defaults invisible in `--help`, so the CLIs gained
`ArgumentDefaultsHelpFormatter` and help text: `--journal` now prints `(default:
var/journal/run.jsonl)`.

**`MIGRATION.md` was the biggest file in the front door** at 48K — larger than the README. It is
a build log, so it moved to `docs/`. The README's Status section still said "Scaffold", which
stopped being true a long time ago; it now says what actually works and what is left.

**And two absences.** A `LICENSE` (MIT — change it if that is wrong, it is one file). And
`.github/workflows/ci.yml`: pytest and ruff on 3.11 and 3.13, the panel's `tsc -b && vite build`,
and `cargo check` for the Tauri shell with the same system packages `./install.sh --desktop`
installs. 383 tests that only ever ran on one laptop were a claim rather than a gate.

### The lint config, and why it is now explicit

`[tool.ruff]` had `line-length` and `target-version` and no `select`, so the rule set was whatever
the installed ruff defaulted to — 189 findings, and CI would have been red on its first run
against code nobody had touched. The rules are now stated in `pyproject.toml`, which means "lint
passes" is a claim about the code rather than about a version.

157 findings were autofixed, 30 fixed by hand, and the rest are **decisions with reasons written
beside them**, because three of the suggestions were wrong for this codebase:

- **`UP042`** would rewrite `class Side(str, Enum)` as `StrEnum`. Measured rather than assumed:
  `str(Side.BUY)` is `"Side.BUY"` under the first and `"buy"` under the second, and these enums
  build order payloads. Ignored.
- **`E501` in `llm.py`** — that file holds the system prompt verbatim. Reflowing it changes the
  prompt and invalidates the ~1,592-token cached prefix. The line length is the prompt's, not the
  code's. Per-file ignore.
- **`DTZ`** flags fourteen `date.today()` calls. The finding is real: `today()` reads the
  machine's local calendar while an option expiry is an exchange fact, so an agent run outside
  market hours on a UTC box can compute DTE off by one. It is safe in the scheduled path, which
  only runs while the broker's clock says open. **It is not a lint fix** — it needs one exchange
  clock that every DTE calculation goes through, which is a behaviour change to the strategy
  layer and belongs in its own commit with its own tests. Ignored deliberately and named, rather
  than silently omitted.

### A bug I introduced, and the test that caught it

Ruff's `FURB162` flagged `datetime.fromisoformat(str(raw).replace("Z", "+00:00"))`. I took the
autofix — `.removesuffix("Z") + "+00:00"` — across two files without reading the values it would
see. Identical on `…00Z`. On `…00-04:00`, which is what Alpaca actually sends, it produces
`…00-04:00+00:00` and raises `ValueError`.

`MarketClock.parse` swallows that and returns `None`, which is correct — a malformed timestamp
should not kill a run — so `next_open` became `None` and **the scheduler sat there forever**. The
suite went from 0.9s to hanging, which is how it was found.

The substitution was dead code to begin with: `fromisoformat` has parsed a trailing `Z` since
3.11, which this project requires, and unlike a hand-rolled substitution it also parses a real
offset. `tests/agent/test_schedule.py` now pins all three timestamp forms, with the reason on the
test, because the failure mode here is a process that hangs rather than an error anyone can see.

Two smaller ones from the same pass: a regex rewrite of `try/except/pass` into
`contextlib.suppress` produced invalid Python in `schedule.py` (reverted, redone by hand), and
the `contextlib` import in `run.py` was missing on a path the tests never execute — ruff caught
what the suite could not. 380 → 383.

## Done: the menu gate, news, the committee, and a soak that found three bugs

### 1. `from-the-menu` — the gate the thesis was missing

*"Legs come from the candidates given to you. Do not invent strikes or expiries."* That
was a sentence in the system prompt for the entire build. The model complied. Nothing
made it.

`contract-validation` is not the same check and never was: it asks whether each leg
exists in the fetched chain, so a model assembling real, listed strikes into a
structure the ranking never scored passes it cleanly. That trade would carry no score
breakdown, no liquidity screen and no viability check against friction — the one trade
in a run that nothing deterministic ever looked at.

The gate compares **signed contracts per symbol**, so it is insensitive to leg order
and to the structure's name, and it catches the subtler case: legs borrowed from two
different candidates and recombined into a third thing that was never on the menu.
Size is deliberately not part of the signature — `max-loss-per-position` is the gate
with an opinion about quantity, and it should be the one that speaks. Fails closed on
an empty menu. Chain is 15 → 16 gates; contract family 2 → 3.

The shared `ctx` fixture was deliberately *not* given a menu. An accommodating fixture
saying "yes, everything was offered" would make the gate pass in every test that never
thought about it, which is the same as not having it. Tests that need one call
`offered(ctx, ...)` explicitly.

### 2. News, through MCP

`get_news` exists on the Alpaca MCP server, so the "everything goes through MCP" claim
survives — no RSS scraping, no second data path with its own rate limits and its own
idea of which symbols an article is about. Benzinga-sourced, symbols tagged by the
publisher.

Alpaca's envelope marks it `trust: untrusted_tool_output`, `risk: external_text`, and
it is right to: anyone who can get a headline published can put a sentence in front of
a model that is about to size a trade. `marketdata/news.py` truncates hard, strips URLs
and role markers, and never parses a headline for meaning — a headline never becomes a
symbol, a strike or a size. The real answer is structural: **a successful injection can
reach a worse trade proposal, and a proposal faces sixteen gates.** That is what makes
untrusted input admissible at all.

### 3. The committee, adapted rather than copied

HAL's `cortex.committee` runs four analysts. Two of them do not survive the port, and
that is the whole difference between the projects: HAL asks a model to read volatility
and judge whether the chain offers a clean structure, and here both are arithmetic that
has already run — `regime.build`, `bias.derive`, `scoring`'s six weighted terms.
Replacing that with a model's opinion of the same numbers is a downgrade dressed as
sophistication. They arrive as **evidence**; only the catalyst analyst runs, because
"what happened, and does it change what these numbers mean" is the one question no
rules engine can answer.

So: catalyst → bull ∥ bear → judge, four calls per underlying. Reflection is not a
call — closed structures come from the ledger with their realized P&L. The judge runs
under `ProposalWriter.system_prompt` itself rather than a copy, so it cannot drift from
the gate catalogue. Off by default (`COMMITTEE=true` or `--committee`).

First live run, SPY: it passed, and the rationale cited *"a Fed decision and an NVDA
print inside the 51-DTE window"* against `event_risk 0.0` on every candidate. That is
correct and the scorer cannot see it — `NO_EARNINGS` treats index ETFs as having no
earnings, true of the ETF and false of its largest holding. **A real strategy-layer
finding, surfaced by the committee on its first run**, and left as a finding rather
than folded into this change.

Two of its own bugs, both fixed: token counts were totalled into a local and journalled
as zeros, and the debate was handed the base user turn — which is written to elicit a
proposal — so the bear returned a filled-in proposal schema instead of an argument. It
now gets an explicit evidence frame.

### 4. The soak, and the three defects it found

`tests/agent/test_soak.py` drives the real `Agent` across scripted cycles. Six journal
events had never once been written in production — `fill_correction`, `exit_decision`,
`divergence`, `halt`, and the marks feeding them — not because they were broken, but
because reaching them takes a *sequence*, and nothing in a unit test spans one.

**Defect 1: exit fills were never fetched.** `refresh_fills` walked `open_structures`,
so a position opened and closed inside one session was never corrected, and a closing
order's fill was never looked up at all. Realized P&L is the difference between the two
prices. The one live round trip reported `-$10.00` computed from two limits; Alpaca's
own record has it filling at -1.60 and closing at 1.69, a real loss of **$9.00**. Now
corrected on both sides, with `entry_filled`/`exit_filled` flags — without them a fill
that happens to equal its limit is indistinguishable from one never looked up.

**Defect 2: `get_orders` returned nothing, always.** Two envelopes, not one: `_parse`
strips Alpaca's security wrapper and returns `data`, and several tools nest their
payload under a second key — `result` for positions and orders. The loop unwrapped
positions by hand at the call site, which is exactly why orders never got the same fix.
`_rows()` now does it once in the client, and `reconcile` raises a named error instead
of an `AttributeError` several frames from the cause.

**Defect 3: the journal could not tell an entry from an exit.** Both were bare `order`
events with a structure name. Realized P&L was never wrong — it comes from the ledger —
but a record whose meaning has to be inferred has a gap in it, and exits were the half
nobody could see. `intent` is now `"open"` or `"close"`.

Also: `scripts/soak.py` (`./start.sh soak`) runs a live session and then reports which
lifecycle events it actually reached, and names the ones it did not. A soak reporting
"no errors" without saying what it never touched proves very little.

**Not covered, and no offline test can be:** whether Alpaca fills a closing `mleg`
order and how long it takes. That needs a live window; the market was closed when this
landed. 389 → 399 tests.

## Done: real event risk, and the structure chart

### The event term was a constant on every trade this agent has ever scored

`event_risk_for(underlying)` answered from `NO_EARNINGS`, a frozen set of tickers that
do not report. SPY, QQQ and IWM are all in it, so the term returned `none` on every
candidate — one of six weighted terms, inert, for the life of the project.

The set's reasoning was not wrong; it was answering a narrower question than the term's
name. An index does not report earnings, and a diversified one spreads its
constituents' reports across a quarter. Both true. Neither says anything about the two
things that actually price index options: a macro print, and a single holding big
enough to move the index alone. QQQ is roughly a tenth NVDA — that is concentration
wearing a diversified name, and the committee caught it live before this was written.

**Where the data comes from.** Not Alpaca: `get_corporate_action_announcements` covers
dividends, splits, mergers and spinoffs, and returns `{"result": []}` for SPY, QQQ and
NVDA alike on this entitlement. Not Yahoo either — every endpoint, including the
cookie/crumb hop, returns 429 to an unauthenticated client now. Nasdaq's keyless
calendar works, is what HAL already uses for the same job, and is cached per date under
`var/cache/`. It is the one lookup that does not go through MCP, which is a deliberate
and narrow exception: a public calendar is not broker interaction, and no order,
position or account figure is ever read from it.

**The fix that matters is the window, not the feed.** `EventWindow.risk_for(dte)`
answers per candidate, so two structures on the same underlying — one expiring before
an event, one spanning it — no longer score identically. That discrimination was
impossible before, because the term only ever saw a symbol.

`known=False` and `known=True, days_out=()` are kept apart deliberately: one says the
calendar was read and the window is clear, the other says it could not be read. Only
the first removes a penalty, and collapsing them is the original bug in miniature. A
hole anywhere in the window poisons the whole answer rather than reporting the days
that happened to load.

Live, on QQQ: `2 event(s), next NVDA earnings 2026-08-26 (via QQQ)` — NVDA reported
that afternoon and AVGO follows on 2026-09-02. Every candidate's event term went from
**0.0 to 1.0**, and the journal now records the events themselves rather than a verdict,
because "event_risk: present" is unfalsifiable six weeks later and "AVGO earnings
2026-09-02" can be checked.

### The structure chart

Click a structure in the new **BOOK** view and it charts against the levels its exit
policy acts on: entry, target, stop.

The line is the structure's *net* price, not a leg's — `sum(signed * close)`, on the
same sign convention `mark_structure` uses. A timestamp missing from any leg is
dropped, because `mark_structure` already refuses to act on a partial mark and a chart
that drew the bars which did arrive would put dips in the line that are an absent quote
rather than a price.

**The three lines come from `manager.exit_levels`, and a test pins that function to
`evaluate_exit` itself** — walking a structure across each boundary and asserting the
action flips exactly where the levels say it will. Two derivations of one rule is how a
chart starts lying while looking confident. The conversion is worth stating: the exit
reasons in dollars, a chart plots the mark, and `credit * tp%` becomes
`entry * (1 - tp/100)` with the multiplier and quantity cancelling — a target is a
price, and it does not move when you trade ten instead of one.

Two things fell out of writing it. A 200% stop on a *debit* structure sits below zero
and is unreachable, since you cannot lose more than the premium paid; noted rather than
"fixed", because this project trades credit structures. And the chart's visible range is
forced to include every level — a stop three times the credit from entry would
otherwise auto-scale off the bottom, and an invisible stop defeats the point of drawing
one.

**The route reaches the broker; it cannot be pointed anywhere.** `/api/structure/{id}/chart`
resolves symbols from our own ledger, so the panel can ask about the book and nothing
else — not a general market-data proxy wearing a read-only dashboard. Still a GET, still
no write path, and it degrades to drawing the levels with no price line when the broker
is unreachable, which is most of what it is for.

Also: the panel now loads `.env` (optional — it runs fine without, the chart just goes
priceless), the snapshot serves closed structures so a completed trade can be charted at
all, and a bare `FileNotFoundError` from a missing `uvx` now names the cause instead of
saying "No such file or directory" about nothing in particular.

**A mistake worth recording.** `constants/strings.ts` had been refactored to i18next
with `locales/en.json` since I last read it, and my edit to it silently did nothing —
`str.replace` on text that was no longer there. The build caught it. The words are now
in the locale where the refactor put them, and the typed shape is accessors like every
other section. 399 → 428 tests.
