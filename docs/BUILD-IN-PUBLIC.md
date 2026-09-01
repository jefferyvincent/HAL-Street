# Build in public

Optional extra challenge: post progress to X and LinkedIn, tag **@lablab.ai** and **@Alpaca**,
submit up to 5 links with the final project.

Five posts is the cap, so plan five rather than posting five times about the same day.

## Suggested arc

| # | Beat | Why it travels |
|---|---|---|
| 1 | The thesis — model proposes, deterministic gates dispose | The idea is the hook, not the repo |
| 2 | A gate rejecting a real LLM proposal (screenshot the rejection) | Most compelling artifact you own |
| 3 | Wiring the Alpaca MCP server — what surprised you | Alpaca is likely to engage with this one |
| 4 | A setback, honestly told — a bad fill, a bug, a strategy that didn't work | Rules explicitly ask for setbacks |
| 5 | Results + demo clip | The close |

## Rules of thumb

- Screenshot the terminal, not the editor. Rejections and fills read better than source code.
- Never post a frame containing account keys or the competition account ID.
- Post the loss as well as the win. A drawdown post with an explanation is worth more than a green
  day with a rocket emoji, and the brief asked for reasoning and setbacks by name.
- Record post URLs in `journal/social.md` as you go — chasing five links at submission is misery.

---

## The five posts, drafted

Written from the build log, not from imagination — every claim below is traceable to
`docs/WRITEUP.md` or a commit. Post 5 is a template: it has placeholders, because the
judged window has not been run and a results post written before the results exist is
the one post here that could turn into a lie.

Tags, so they are in one place and get copied rather than remembered:

| | X | LinkedIn |
|---|---|---|
| lablab.ai | `@lablabai` | `@lablab.ai` |
| Alpaca | `@AlpacaHQ` | `@Alpaca` |

On LinkedIn the tag only registers if you pick the company from the autocomplete
dropdown as you type `@` — pasting the plain text posts a string, not a mention, and a
string does not satisfy the requirement.

---

### 1 — The thesis

**X**

> Building HAL Street for the @AlpacaHQ AI Trading Agents Hackathon with @lablabai.
>
> One rule: the model proposes, deterministic gates dispose.
>
> An LLM ranks option spreads and writes a proposal. Sixteen gates in plain Python, no
> model in the loop, decide if it ever trades.

*272 characters.*

**LinkedIn**

> Most LLM trading agents let the model decide and execute. I think that is the wrong
> shape, so HAL Street splits them.
>
> A deterministic strategy engine builds a menu of defined-risk option structures from the
> live chain — credit spreads and iron condors, strikes chosen by delta, priced at the
> touch. The model's job is narrow: pick one, size it, and write down why, as closed-schema
> JSON. It can also decline, and a decline is counted as a decision rather than a failure.
>
> Then the proposal meets seventeen risk gates written in plain Python. No model call, no
> network, no clock beyond an injected date. They check defined risk, max loss, portfolio
> risk, options buying power, liquidity, spread width, concentration, correlation, net
> greeks, assignment proximity, days to expiry — and every one of them runs on every
> proposal, because "rejected by four gates" is a more useful record than "rejected by the
> first one checked."
>
> The model can be wrong, hallucinate a strike, or talk itself into something stupid. It
> still cannot put on an undefined-risk position, and it has no say in whether the gates
> run.
>
> Everything above the line is probabilistic. Everything below it is auditable.
>
> Built on @Alpaca paper trading for the AI Trading Agents Hackathon with @lablab.ai.
>
> #buildinpublic #AI #algotrading #options #Alpaca

---

### 2 — A gate rejecting a real proposal

Screenshot the terminal rejection, not the source. Crop out the account number.

**X**

> Gate of the day: correlated-exposure.
>
> My agent approved put credit spreads on SPY, QQQ and IWM in one cycle. Every other gate
> waved it through — three different roots, three separate names.
>
> That is one bullish bet at 3x size with better paperwork.
>
> @lablabai @AlpacaHQ

*270 characters.*

**LinkedIn**

> A gate I did not know I needed until the agent walked straight into it.
>
> One scan approved put credit spreads on SPY, QQQ and IWM in the same cycle. Every risk
> check passed. The concentration gate matches roots exactly, so to it those were three
> separate underlyings — textbook diversification.
>
> They are the same trade. Diversification across tickers that move together is not
> diversification; it is leverage with better paperwork. So there is now a
> correlated-exposure gate that counts contracts across a basket rather than per ticker.
>
> The follow-on was more interesting. When the universe stopped being a hand-picked list
> and started being discovered from the news tape, the correlation map — about sixty names
> — stopped covering the common case. An unmapped ticker used to pass, on the reasoning
> that a human had chosen the universe so an unmapped name was a deliberate choice. Under
> discovery, unmapped is the default, and a cap that waves through the default is not a
> cap. Unmapped roots now land in their own bucket with its own limit: not a claim that
> they move together, just a bound on how much of the book can sit in names whose
> correlation nobody has checked.
>
> Two claims, two numbers. Sharing one knob would mean loosening the verified claim to
> make room for the unverified one.
>
> @Alpaca @lablab.ai
>
> #buildinpublic #risk #options #AIagents

---

### 3 — Wiring the Alpaca MCP server

**X**

> Two things I only learned by pointing code at a live @AlpacaHQ MCP server, not the repo:
>
> 1. The names in toolsets.py are OpenAPI operationIds. Registered tools are snake_case.
> getAccount → "Unknown tool."
>
> 2. options_buying_power ≠ buying_power: $89,817 vs $359,270.
>
> @lablabai

*278 characters.*

**LinkedIn**

> Every broker call in HAL Street goes through Alpaca's official MCP server. Nothing
> touches the REST API. Four things that survey turned up, none of which I would have
> found by reading documentation:
>
> 1. The tool names in toolsets.py are OpenAPI operationIds. The registered MCP tools are
> snake_case. Call getAccount and you get "Unknown tool," which reads like a permissions
> problem and is not one.
>
> 2. Every response is wrapped in a security envelope. A client that treats the envelope
> as data will happily act on an error message.
>
> 3. The broker nets legs across structures. After a vertical and a condor both sold the
> same Oct-16 770 call, the account reported one position at qty −2 — not two positions
> tagged to their parents. Alpaca has no concept of which structure a leg belongs to, so
> the ledger and the concentration gate now count contracts, never structures.
>
> 4. Options collateral does not come out of the headline buying power. On this account:
> $89,817 of options buying power against $359,270 of buying power, because the latter is
> 4x margin for equities. Those two agree only while the book is flat. An equity-based
> sizing ceiling keeps approving trades the broker has already stopped being able to
> accept.
>
> All four were confirmed with real paper orders before anything was built on top of them,
> because the whole project rests on those assumptions.
>
> @Alpaca @lablab.ai
>
> #buildinpublic #MCP #Alpaca #tradingsystems

---

### 4 — The setback

The brief asks for setbacks by name. Two of them, one lesson: I trusted something I had
not checked. **Shoot:** the traceback in `var/log/halstreet.log`, or the uv cache
timestamps showing the two environments built on the 31st.

**X**

> My trading agent was up all day and never placed a trade.
>
> alpaca-mcp-server allows fastmcp>=3.1.0, unbounded. fastmcp 4.0.0 shipped, moved a
> module the server imports at start-up, and every call came back "Connection closed".
>
> Nothing in my repo changed.
>
> @lablabai @AlpacaHQ

*276 characters.*

**LinkedIn**

> My autonomous trading agent spent a full session up, healthy, and doing nothing at
> all. No trades. No errors on the console. The loop was running.
>
> Alpaca's MCP server declares `fastmcp>=3.1.0` with no upper bound, and it is launched
> through `uvx`, which re-resolves its dependencies at every single start. fastmcp 4.0.0
> was released. It moved a module the server imports at start-up. So the server died
> before it could speak, and every broker call — including the one that asks whether the
> market is open — came back as "Connection closed". The scheduler read that as "market
> state unknown", waited 30 minutes, and did it again. All day.
>
> Nothing in my repository changed. The uv cache dates it precisely: environments built
> on the 28th and the 30th resolved fastmcp 3.4.7 and worked. Both environments built on
> the 31st got 4.0.0 and did not.
>
> One design decision saved me. The MCP subprocess prints a fifteen-line banner on every
> launch, and I had written a filter for it rather than pointing stderr at /dev/null —
> because the channel that carries the noise is the same one that carries the failure.
> The filter's bias runs one way: an unrecognised line is always kept. So the
> ModuleNotFoundError was sitting in the log, in full, and the diagnosis took one grep
> instead of a day.
>
> The fix is a pin — `uvx --with 'fastmcp<4' alpaca-mcp-server` — and it lives in the
> code rather than in a config file, because a default that only works if someone edited
> their environment is not a default.
>
> The second one, the same week, was mine rather than upstream's, and it is the same
> lesson wearing different clothes.
>
> A lint rule flagged a timestamp normalisation: .replace("Z", "+00:00") on a broker
> timestamp. The suggested fix was .removesuffix("Z"). I took it. It was even correct in
> the abstract — Python 3.11 parses a trailing Z natively, so the substitution had been
> dead code for two releases.
>
> What Alpaca actually sends is not Z. It is −04:00. So removesuffix did nothing to the
> string, and a later concatenation produced −04:00+00:00, which does not parse, which the
> clock parser swallowed, which left next_open as None, and the scheduler waited forever
> for a market open that was never computed. The agent was up. It was idle. Nothing logged
> an error.
>
> Three lessons, all cheaper to learn on paper money:
>
> — A lint suggestion is a hypothesis about your data, not a fact about your code. I never
> looked at a real value.
> — A parser that swallows exceptions converts a loud failure into a silent one, and silent
> is the expensive kind in an unattended system.
> — The related discovery: the timezone lint rule had been removed from the ignore list and
> the suite went green. True and meaningless — the rule had never been in select. Nine
> host-calendar reads were sitting behind a check that was never on. It is enabled now,
> confirmed by planting a violation and watching it fire.
>
> There is now a test over all three timestamp shapes the broker emits, and a test that
> fails if the fastmcp pin is ever dropped.
>
> One lesson, twice: a suggestion is a hypothesis about your data, and an unbounded
> dependency range is a promise someone else can break on a Tuesday. Verify both.
>
> A build log with no mistakes in it is a build log nobody should believe.
>
> @Alpaca @lablab.ai
>
> #buildinpublic #debugging #lessonslearned #tradingsystems

---

### 5 — Results and demo

**Template. Do not post until `./start.sh report -- --writeup --window "<dates>"` has run
against the competition account.** Every `<…>` is filled from that output, not retyped
from a scrolled terminal.

**X**

> HAL Street, final numbers from the judged window.
>
> <N> proposals, <M> considered passes. <G> gate rejections. <O> orders. P&L <$X>, max
> drawdown <Y%> at scan resolution.
>
> Every figure generated from the agent's own append-only journal. Demo ↓
>
> @lablabai @AlpacaHQ

*263 characters with the placeholders as written; recount after filling them in.*

**LinkedIn**

> HAL Street is finished. Numbers from the judged window on a fresh @Alpaca paper account,
> starting at $100,000:
>
> — Proposals: <N>, of which <P> were considered passes rather than trades
> — Gate outcomes: <A> approved, <R> rejected, by gate: <breakdown>
> — Orders submitted: <O>. Positions closed: <C> (<W>W / <L>L)
> — Realized P&L: <$X>. Equity <$start> → <$end>
> — Max drawdown: <$D> (<Y>%) over <S> scan samples — scan resolution, not tick resolution
>
> Every one of those is generated from the agent's append-only journal by the report
> command, not typed by me. The two figures a judge reads first are the ones most likely to
> be wrong if a human retypes them.
>
> Two caveats stated up front rather than left to be discovered: quotes come from Alpaca's
> indicative feed, not the paid OPRA consolidated feed, so paper fills here can diverge
> from official NBBO — and which feed produced each result is recorded in the journal.
> Drawdown is sampled once per scan.
>
> What I would keep from this build: the line between the probabilistic layer and the
> auditable one, drawn once and enforced structurally. The panel is read-only and the
> read-only-ness is proven by a test that parses the AST, because a dashboard that can
> trade is a second path to the broker that never passes the gates.
>
> Thanks to @lablab.ai and @Alpaca for the hackathon.
>
> #buildinpublic #AI #algotrading #Alpaca

---

## Before posting, each time

- Terminal, not editor. A rejection or a fill reads better than source.
- No frame containing keys, the `.env`, or the competition account number.
- Log the URL in `journal/social.md` the moment it is live.
