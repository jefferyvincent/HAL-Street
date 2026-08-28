# One-page write-up — HAL Street

> Required deliverable. Judges asked for three things by name: **AI logic, risk gates, Alpaca
> infrastructure.** Sections below use their words, in their order.
>
> **Status:** written from the built system. Every number is measured, not projected. Results
> currently show a dev-account rehearsal and are regenerated from the judged window with
> `./start.sh report -- --writeup --window "<dates>"` — so the closing numbers are produced by
> the same journal the agent wrote, not retyped from a terminal.

**Thesis: the model proposes; deterministic gates dispose.**

An LLM is good at ranking a short menu of legal structures and writing down why. It is not
something to trust with a risk limit. So HAL Street draws a hard line: everything above the line
is probabilistic and everything at or below it is auditable Python with no model call in it. The
model never sees a limit it can argue with, cannot reach the environment, and has no say in
whether the gates run.

---

## AI logic

**Universe and cadence.** SPY, QQQ, IWM. One scan every 30 minutes, and only while the *broker's*
`get_clock` says the market is open — a local `datetime` knows nothing about holidays or early
closes, and a test asserts `weekday`/`hour` appear nowhere in the scheduler.

**What the strategy engine produces, deterministically.** `strategy/` builds put and call credit
spreads and iron condors from the live chain — arithmetic only, no model, no randomness, so the
same chain and market view reproduce the same menu from the journal months later. Strikes are
chosen by **delta**, not by dollar distance: a 5-point wing means something different on a $60
stock than on a $760 index, whereas a 0.20-delta short strike means roughly the same thing
everywhere. Structures are priced at the touch — **sell the bid, buy the ask** — because quoting
at mid and discovering the fill is worse is the standard way to talk yourself into a trade that
never had the edge you thought.

Candidates are then ranked by a six-term weighted blend ported from a prior codebase: bias fit,
IV-regime fit, liquidity, reward/risk, probability of profit, and an event-risk penalty. Every
candidate carries its own **score breakdown** into the journal, so "why was this one top of the
menu?" has an answer that is six numbers rather than one.

The event term used to be a constant. It read "index ETFs do not report earnings" and returned
the same value for every candidate in the entire traded universe — a weighted term contributing
nothing, which is worse than an absent one because it looks like diligence. It now resolves per
expiry against a **calendar of scheduled reporters**, keyless from Nasdaq, covering the dominant
holdings that actually move an index ETF. A hole in the calendar poisons the window rather than
reading as "no events": not knowing is not the same as knowing there is nothing, and only one of
those is safe to price as zero.

**The one input a rules engine cannot derive.** Everything above is arithmetic over numbers the
market published, and it is deliberately blind to *why* a price moved: a vol crush after a Fed
statement and a vol crush after nothing at all look identical to a realized-volatility rank. So
each cycle also reads the tape — recent headlines for the underlying, via Alpaca's own `get_news`
rather than a second data path with its own rate limits and its own idea of which symbols an
article is about. The mapping from headline to ticker is the publisher's, not a regex over a
title.

**What the LLM does.** Pick one structure from a menu of at most six, size it, and justify it —
emitted as closed-schema JSON. It also has a first-class way to **decline**: `action: "pass"`,
counted separately from proposals and from failures. That matters more than it sounds. An earlier
version told the model "if no candidate is worth taking, propose nothing" against a schema that
required a priced structure; both cannot be satisfied, and what came back was `qty: 0` — which
read as a broken model rather than the considered pass it was.

**A committee, not one opinion.** By default the proposal is reached by four calls rather than
one: a **catalyst analyst** reads the headlines, a **bull** and a **bear** argue the same evidence
in parallel, and a **judge** decides. Reflection is not a call — closed structures on that
underlying come straight from the ledger with their realized P&L, because an agent reasoning about
its own past trades from a model's recollection is reasoning about a story.

The shape is adapted from a prior codebase's take on the TradingAgents pattern, but two of its
four analysts did not survive the port, and the reason is the whole difference between the two
projects. That codebase asks a model to read volatility and judge whether a chain offers a clean
structure. Here both are arithmetic that has already run — `regime` computes the HV rank, `bias`
counts indicator votes, `scoring` ranks every candidate on six weighted terms. Replacing that with
a model's opinion of the same numbers would be a downgrade dressed as sophistication, so they
arrive as **evidence** rather than as agents. The only analyst that runs is the one asking a
question no rules engine can answer.

The bull and bear run **concurrently and neither sees the other's argument**, because a bear that
has read the bull's case argues with the case rather than with the trade — and the resulting
agreement looks like corroboration to a judge. The judge is told so explicitly: they were
instructed to disagree, so their agreeing is not evidence.

**The committee cannot approve anything.** It produces a proposal, and a proposal meets the same
sixteen gates whichever path built it. A committee that agreed unanimously and enthusiastically
still has its structure checked against the menu, its loss against the cap, and its size against
buying power. More deliberation is allowed to make a *better* proposal; it is never allowed to
make a *permitted* one. `COMMITTEE=false` falls back to the single call for a cheap demo.

**The headlines are untrusted, and the design says so.** Alpaca's own envelope stamps them
`trust: untrusted_tool_output`. Anyone who can get an article published can put a sentence in
front of a model that is about to size a trade. Three things follow. Nothing in a headline is
ever parsed for meaning — it never becomes a symbol, a strike, a size or a limit. Fields are
truncated hard and stripped of the constructs injection leans on: URLs, code fences, and lines
opening `system:` or `assistant:`. And they reach exactly one place, the catalyst analyst's user
turn, fenced and labelled, where what comes back is a constrained JSON verdict rather than prose
that flows onward.

None of that is the security boundary. The gates are. A successful injection reaches a lean, a
sentence of note, and from there a worse trade proposal — which is the case sixteen deterministic
gates already exist for. That is the point of putting the model between two deterministic layers:
it is what makes reading untrusted input safe enough to do at all.

**What the LLM does not control.** Strike-selection bounds, position-size ceilings, the trading
environment, order type, whether gates run, or what they check. A limit a confident model can talk
its way past is not a limit — model confidence is journalled and consulted by nothing.

**Hallucinated contracts.** Caught twice. The parser rejects any leg that is not a valid OCC
symbol or whose root differs from the proposed underlying; then `contract_exists` rejects any leg
absent from the chain actually fetched this cycle. A contract that was not on the menu does not
exist.

**Context strategy.** A 1,592-token cached system prefix carrying the full gate catalogue — every
gate named and described, so the model is never rejected by a rule it was not told about. A test
asserts every gate in `ALL_GATES` appears in the prompt, which is what stops the catalogue
drifting. Cache reads confirmed live (0 → 2,237 tokens). One corrective retry on a parse failure,
strictly one: a model that cannot satisfy the schema twice will not satisfy it on the third
attempt, and an unattended loop must not spend an unbounded budget arguing with itself.

---

## Risk gates

**Sixteen gates. All of them run on every proposal — evaluation never short-circuits**, because
"rejected by four gates" is a more useful artifact than "rejected by the first one we checked."
Every gate **fails closed**: a missing greek, an absent quote, an unreadable open-interest figure
is a rejection, never a skip. A gate that silently stops protecting you when the data is bad stops
protecting you exactly when you need it most.

| Gate | Rule | Rejects |
|---|---|---|
| `daily-loss-halt` | Latched off once equity falls past the day's floor (5%) | every entry, for the rest of the session |
| `entry-rate-throttle` | Entries per rolling hour | a runaway loop submitting outside the schedule |
| `open-position-count` | Broker positions held at once | a book bigger than the exit path can work through |
| `contract-validation` | Leg must exist in the chain fetched this cycle | hallucinated or stale contracts |
| `from-the-menu` | Structure must be one the strategy engine actually built and scored | a real but unscored structure the ranking never saw |
| `defined-risk-only` | Every short leg must be covered | naked / unbounded structures |
| `dte-floor` | Minimum days to expiry | short gamma into expiry |
| `max-loss-per-position` | Worst case vs the per-position cap | oversized single trades |
| `portfolio-risk-ceiling` | Summed defined risk vs equity | book-level over-deployment |
| `options-buying-power` | Collateral vs *options* buying power, with a reserve | orders the account cannot collateralise |
| `liquidity-floor` | Open interest **and** today's volume, per leg | contracts that cannot be exited |
| `quoted-spread-width` | Bid/ask as % of mid, worst leg decides | positions expensive to leave |
| `underlying-concentration` | Net contracts per underlying | stacking one name |
| `correlated-exposure` | Contracts across a basket that moves together | SPY+QQQ+IWM as "diversification" |
| `portfolio-greek-bounds` | Net delta and vega across the whole book | directional / vol drift |
| `assignment-proximity` | Short leg near the money near expiry | operational assignment risk |
| *(environment assertion)* | Paper-only, three independent signals | any non-paper credential |

Four of these are worth a sentence each, because they came from things that actually happened.

**`from-the-menu` exists because this project's own thesis was, for a long time, a sentence in a
prompt.** "Legs come from the candidates given to you. Do not invent strikes or expiries." The
model complied. Nothing made it. And `contract-validation` does not cover this — it asks whether
each leg exists in the chain, so a model that assembled real, listed strikes into a structure the
ranking never scored would pass it cleanly. That trade would carry no score breakdown, no
liquidity screen, no viability check against friction, and no reason in the journal beyond the
model's own sentence about it: the one trade in the run that nothing deterministic ever looked at,
which is precisely the case this project exists to make impossible. It compares leg *signatures*
rather than names, so it also catches the subtler version — legs borrowed from two candidates and
recombined into a third that was never on the menu. Finding this was the argument for the
committee being harmless: more deliberation cannot reach a structure the engine never built.

**`correlated-exposure` exists because the shipped universe walked into it.** A live scan approved
put credit spreads on SPY, QQQ *and* IWM in one cycle. That is one bullish bet at triple size, and
every other gate waved it through — `underlying-concentration` matches roots exactly, so three
roots look like three separate names to it. Diversification across tickers that move together is
not diversification; it is leverage with better paperwork.

**`options-buying-power` is the one that reads a different number than everything
else.** Every other sizing gate measures against equity. The broker does not: options
collateral comes out of `options_buying_power`, which is cash — $89,817 on this
account against a headline `buying_power` of $359,270, because the latter is 4×
margin for equities. The two agree only while the book is flat; as positions
accumulate, held collateral drains buying power while equity stays put, so an
equity-based ceiling keeps approving trades the broker has stopped being able to
accept. A reserve is kept back so there is always something left to *close* with —
some exits are debits, and being unable to pay one is how a defined-risk position
stops being defined.

**`daily-loss-halt` is latched and survives a restart.** A breaker that un-trips when the tape
bounces is a delay, not a breaker. And it is persisted to disk rather than held in process memory,
because restarting the agent is precisely what someone does when an unattended agent starts
behaving oddly — a latch that dies with the process is not a latch.

**The environment assertion is not in the list on purpose.** It is not a judgement over a
proposal; it runs inside `place_structure`, against the broker's own account snapshot,
immediately before every single order. Putting it in the chain would imply it could be reordered,
disabled, or handed a stale context. It checks three independent signals — `ALPACA_ENV`, the key
prefix (`PK` paper vs `AK` live), and the account number prefix — and refuses live credentials
outright.

**Gates are deterministic Python.** No model call, no network, no clock beyond an injected date,
and nothing the agent can rewrite at runtime. Every gate has a test proving it **rejects**, which
is the only kind of test that shows a safety layer is load-bearing rather than decorative.
1074 tests, and the per-gate rejection count for the window is in Results below — generated from
the journal rather than asserted here, because a safety layer's own write-up is the last place a
number should be taken on trust. Coverage is not the standard used: a test is accepted when the
defect it names, planted back into the source, actually makes it fail.

**Exits are never gated.** Nothing in `gates/` applies on the way out. A latched halt, a breached
concentration cap, an account in drawdown — every one of those is a reason to be *more* able to
close, not less.

---

## Alpaca infrastructure

**MCP, not REST.** All broker interaction goes through Alpaca's official MCP server
(`uvx alpaca-mcp-server`, stdio); nothing in the project calls the REST API. Tools consumed:
`get_account_info`, `get_option_chain`, `get_option_contracts`, `get_option_snapshot`,
`get_stock_bars`, `get_stock_latest_trade`, `get_all_positions`, `get_orders`,
`get_account_activities`, `get_clock`, `place_option_order`, `close_position`.

Two findings worth recording, both from reading a live server rather than the repo. The tool names
in `toolsets.py` are OpenAPI operationIds (`getAccount`, `OptionChain`) — every *registered* MCP
tool is snake_case, and calling an operationId returns "Unknown tool." And every response is
wrapped in a `{_alpaca_mcp_security, data}` envelope that the client unwraps; a caller that
receives an error message shaped like data will act on it.

**Connection model.** Connect-per-call: each call opens a short-lived stdio session and closes it,
which avoids juggling long-lived async MCP sessions across asyncio tasks. Subprocess startup per
call is real, but against a 30-minute cadence it is noise.

**Verified live before anything was built on it.** Multi-leg (`mleg`) submission, the 4-leg
ceiling, the 4-leg roll, and options level 3 were all confirmed by real paper orders on
2026-08-26 — because the whole project rests on that assumption and the remaining unknowns needed
real keys. Two things that survey came back with:

- **The broker nets legs across structures.** After a vertical and a condor both sold the same
  Oct-16 770 call, the account reported *one* position at qty −2, not two positions tagged to
  their parents. Alpaca has no concept of which structure a leg belongs to. That reshaped both the
  ledger and the concentration gate: everything counts contracts, never structures.
- **Friction, measured per leg per contract.** $7.50 — so ~$15 round trip for a two-leg spread and
  ~$30 for a condor. The unit matters: the raw figure was a $73.40 total across *three* structures
  and 16 leg-fills, and comparing that lump against one structure's per-contract max gain
  overstated friction roughly 4× and had the agent declining trades it should have taken.

**Account.** A brand-new dedicated paper account, starting balance $100,000, never used for
anything else. `scripts/preflight.py` refuses to run against an account that is not fresh at
$100,000, and the judged run reads `COMP_ALPACA_*` credentials where a dev run reads `ALPACA_*`,
with no fallback between them — pointing the dev config at the competition account "just to test
something" is the mistake that ends a competition entry, so it is made structurally impossible
rather than discouraged. The separation is the variable name, not a second config file: one `.env`
means the two credential pairs sit four lines apart, and the failure that actually happens — the
same account pasted under both names — becomes a comparison the loader can make.

**The record is separated the same way.** The two accounts do not share a journal, a ledger or a
breaker file. They used to: `--env comp` changed the credentials and nothing else, so a judged run
appended to the same files as every dev rehearsal — and since every figure below is computed over
whole files, the Results block would have folded a rehearsal into itself and said nothing. The
line that made it obvious is `Equity: X → Y`, which would have taken X from a dev cycle and Y from
the competition account: two accounts averaged into one claim. And the window is now *measured*
from the journal rather than asserted by whoever ran the report; a description that names dates
the data does not contain is reported beside the measured one instead of printed over it.

**Order flow.** Construct (`execution/structures.py`, 4-leg ceiling enforced at construction) →
gate → assert paper → submit as a single `mleg` order → journal on acceptance, not on fill → the
ledger reconciles against broker positions every cycle. **Broker always wins**: divergence is
reported, never repaired. An agent that "fixes" its own books to match its expectations is an
agent that cannot tell you when it is wrong.

**On Alpaca's Skills Library.** The Paper Trading Skill published during the build
names five capabilities: restate strategy logic before ordering, preview orders with
buying-power checks, verify the paper environment and block live credentials, track
order lifecycle, and save session artifacts. HAL Street does all five — but as
deterministic Python rather than agent instructions, which is the whole argument here.
A skill is a prompt; the environment assertion has to be a guarantee, so it runs in
`place_structure` against the broker's own account snapshot where no model can decline
to follow it. Adopting the skill for that job would move a hard check into the
probabilistic layer. What the skill *did* contribute is the buying-power gate above:
it was the one item on that list this project genuinely lacked, and the measurement
that followed found options buying power to be a quarter of the headline figure.

**Telemetry.** Append-only JSONL journal: every cycle, market view, candidate menu with score
breakdowns, the committee session, proposal, all sixteen gate verdicts, order, fill, exit. `./start.sh report` exports
`summary.json`, `positions.csv` and `results.txt`. Realized P&L comes from the ledger rather than
the broker, because Alpaca can tell you what a *contract* did but never what a *condor* did.
Drawdown is labelled "over N scan samples" — it is scan-resolution, not tick-resolution, and the
output should not imply otherwise.

**The panel, and why it cannot trade.** `./start.sh panel` serves a React/TypeScript app that
reads the same journal: one decision with all sixteen verdicts grouped by family, the full
decision history, the chain with each gate's actual rejection count, an equity curve, and — on
clicking a position — a chart of that structure's own net price with its entry, target and stop
drawn on it. Those three lines are derived from the same `ExitPolicy` the position manager acts
on, and a test walks a structure across each boundary to prove the action flips exactly where the
chart says it will; two derivations of one rule is how a chart starts lying while looking
confident. A WebSocket pushes it within half a second of the agent writing a record.

It is read-only, and the interesting part is that this is enforced rather than promised. Every
HTTP route is a GET. The socket is *send-only* — the server never calls `receive` and the client
never calls `send` — so a crafted frame reaches no code, and a test parses the module's AST to
prove the call does not exist. The Tauri desktop shell registers no commands and holds no
capability past a window, so the desktop build is a frame around the identical unprivileged
page. There is no override button, no editable limit, and no way to clear a latched halt from
the screen: that is a deliberate act at the CLI, where it lands in shell history.

The reason for all of it is the thesis. A dashboard that can trade is a second path to the
broker that does not pass through `gates/`, and the claim this project makes is that there is
exactly one such path.

---

## Results

**Generated, not typed.** `./start.sh report -- --writeup --window "<dates>"` emits this
section as markdown straight from the journal. The numbers a judge reads first are the
ones most likely to be wrong if a human retypes them from a scrolled terminal, so the
only line below written by hand is the last one.

*Rehearsal figures from the dev paper account on 2026-08-26 — replaced by the judged
window's output before submission:*

- **Window traded:** 2026-08-26 (dev account rehearsal)
- **Proposals / passes:** 30 proposed, 15 passed (45 model turns). A pass is a
  considered decline, not a failure — it is counted separately for that reason.
- **Gate outcomes:** 30 approved, 0 rejected
- **Rejections by gate:** none. Not evidence the gates are inert — candidates are
  pre-filtered against the same limits before the model sees them, so the strategy
  layer absorbs most of what would otherwise be rejected.
- **Orders submitted:** 2
- **Positions:** 1 closed, 0 open — 0W / 1L
- **Realized P&L:** $-9.00 · **Unrealized:** $0.00 · **Total:** $-9.00
- **Equity:** $89,826.79 → $89,817.69
- **Max drawdown:** $9.10 (0.01%) over 60 scan samples — scan resolution, not tick
  resolution

**That figure was $-10.00 until the soak harness explained why.** The ledger held two
*limits* — -1.59 in and 1.69 out — because an order is `pending_new` when it is
recorded and the only number in hand at that moment is the price you were willing to
pay. `refresh_fills` was written to correct exactly this, and did not: it walked open
structures only, so a position opened and closed inside one session was never revisited,
and a closing order's fill was never fetched under any circumstances. Both halves of a
round trip could go unchecked, and this one did.

It now corrects both sides, and each price carries a flag recording whether a fill has
actually been confirmed or the limit is still standing in. Asked for its own record,
Alpaca reports the open filled at **-1.60** and the close at **1.69** — so the real
loss is $9.00, and the extra dollar was never a trading result at all.

An earlier draft of this section argued the number should stand uncorrected, on the
grounds that editing a historical ledger entry is what an audit trail exists to
prevent. That was the right instinct pointed at the wrong thing. What an audit trail
forbids is a number changing with no record of why; what happened here is that the
broker's own fill was fetched and written with a journalled `fill_correction` carrying
both the old price and the new one — the same event the agent now emits automatically.
The correction is in the record. Reporting a P&L computed from prices nobody traded at
would have been the actual violation.

### What already went wrong, and what changed

Kept here because a build log with no mistakes in it is a build log nobody should believe.

- **A gate that would have blocked every order.** `assert_paper_account` checked an `is_paper`
  field Alpaca never returns. Fixed to read the `PA` account-number prefix. Found by testing the
  assertion rather than trusting it.
- **A hidden ×100.** `MAX_NET_DELTA=50` silently meant 5,000 shares. Units changed to
  share-equivalents, which is the number that tells you what the book does when the tape moves a
  dollar.
- **Limits that were decoration.** The `.env` risk limits were read by nothing until
  `Limits.from_env()` existed. A malformed value now raises instead of falling back — believing
  you are protected at the number you wrote is worse than no limit at all.
- **A liquidity floor measuring the wrong thing.** The volume floor rejected almost everything
  while open interest and spread rejected almost nothing, and it was biased: the further OTM a
  strike sits, the less it trades *today*, so it selected hardest against exactly the structures
  this strategy is built on. Retuned on measurement, and the sweep is in the commit.
- **A sign error worth $0 and nearly a lot more.** `evaluate_exit` negated a mark that was already
  in the right convention, reporting a profitable debit spread as a 254% loss — which the stop
  would have closed at the worst possible moment.
- **A lint autofix that stopped the agent trading.** A rule flagged `.replace("Z", "+00:00")` on
  a broker timestamp; the suggested `removesuffix` was taken without checking the values. On what
  Alpaca actually sends — `…-04:00` — it produced `…-04:00+00:00`, which fails to parse, which the
  clock parser swallowed, which left `next_open=None`, and the scheduler waited forever. The
  substitution had been dead code since Python 3.11 parses a trailing `Z` natively. There is now
  a test over all three timestamp forms the broker emits.
- **A lint rule that was never on.** The timezone rule was removed from ruff's `ignore` list and
  the suite went green, which was true and meaningless: it had never been in `select`. Nine
  host-calendar reads sat behind it. The rule is enabled now, confirmed by planting a violation
  and watching it fire, and the trading path takes the exchange's own date from the broker —
  no timezone database, no hardcoded venue.
- **A default that quietly switched off the news.** The committee shipped off, for the honest
  reason that four model calls per underlying is a real cost. What that missed is that the news
  fetch lives on the committee path alone, so the cheap setting was also the one where the agent
  never read the tape — trading the only genuinely new input in the system for a smaller token
  bill. On by default now.
- **A researcher lost to a token ceiling.** The first live committee cycle journalled
  `bull: no text block` and decided having heard only the bear. The model had not been silent:
  adaptive thinking spends from the same budget as the answer, and it ran out mid-thought at a
  measured 1270 tokens against a 1600 ceiling. Budgets raised to ~2.5× observed, truncation named
  as truncation rather than as silence, and a partial argument is discarded rather than passed on
  — half a bull case reads to a judge as a *weak* one.
- **A malformed timestamp that would have abandoned a scan.** `age_hours` parsed the timestamp
  inside a `try` and did the arithmetic outside it, so a naive value raised one line later, escaped
  the catalyst stage, and was caught at the cycle level — one off-contract article would have
  killed the whole scan for that underlying, every cycle, until it aged out of the 48-hour window.
  Found by writing the tests for the module that reads untrusted text, which had none.
- **A soak that reported on a journal it never wrote.** `scripts/soak.py` took `--journal`, printed
  it, read it for the coverage table, and did not pass it to the agent. Both defaulted to the same
  path so it was invisible until someone kept a session's record separate — the exact thing you do
  for a run you intend to cite. The worse shape is silent: with a file left from an earlier run it
  reports that run's coverage as this one's.
- **A write-up nothing was checking.** This document counted fifteen gates against sixteen in three
  places, spelled as a word so no search for "16" would find it, and had never heard of the
  committee, the news feed, the earnings calendar or the chart. `tests/test_writeup.py` now pins
  every checkable claim in it — the gate table against `ALL_GATES`, the count, the quoted limits
  against the shipped defaults, the test total, and every file path it names.
