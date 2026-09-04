# HAL Street — demo narration

**Runtime ≈ 5:10 at 140 wpm.** Timecodes are cumulative. If you're running ahead at the
3:27 mark, cut the second paragraph of *The evidence* — it's the only one nothing else
depends on. If you're running long, cut the middle paragraph of *The gates*.

`>` lines are what's on screen. Everything else is what you say. **Bold** takes the stress.

---

## 0:00 — Cold open

> Console tab, live. Gate ledger visible with a green 18/18.

This is HAL Street. It's an autonomous options trading agent, and it runs on one idea:
**the model proposes, and eighteen deterministic gates dispose.**

A language model is very good at building an argument. It is not reliable at knowing
when its own argument is wrong — and a confident wrong trade looks exactly like a
confident right one. So in this system the model never touches the money. It writes a
proposal. Python decides whether that proposal ever becomes an order.

---

## 0:40 — The committee

> Committee tab mid-cycle — catalyst, then bull and bear side by side, then judge.

Every scan starts here. A catalyst analyst reads the news feed and takes a view. Then a
bull and a bear argue the same chain **in parallel**, and neither sees the other's case.
A judge reads all three and either writes a structure or declines.

The tiers are deliberate. The analysts run on Sonnet — they're doing volume work,
reading headlines and chains. The judge runs on Opus, because that's the call that costs
money if it's wrong. Four model calls per name, and every one of them is written to the
journal with its token count, so the bill is visible rather than assumed.

---

## 1:35 — The gates

> Gates tab. Scroll the eighteen slowly. Land on a rejection with its reason text.

Then the proposal meets the gates. **All eighteen run** — evaluation never stops at the
first rejection, because a decision with one reason is worth less than a decision with
eighteen verdicts you can read afterwards.

They check defined risk, max loss per position, buying power, liquidity, correlated
exposure — because SPY, QQQ and IWM are one bet wearing three tickers. They cap
contracts per name. They refuse a structure the model invented that wasn't on the menu
it was shown.

And every one of them **fails closed**. If a gate can't read the data it needs, it
rejects. Not knowing whether a trade is safe is not the same as knowing it is — and only
one of those is safe to act on.

---

## 2:37 — Getting out

> Book tab → click a holding → the chart with entry, target and stop drawn.

Entries are the easy half. Exits are where the money actually is, so the exit path has
no gates at all — every reason to block an entry is a reason to be **more** able to
close, not less.

It takes profit at a target it holds out for. It stops out. It force-closes before
expiry week. It ratchets: once a position has been up, it won't let that gain evaporate.
And nothing short is carried overnight — the gap is the one move a defined-risk
structure can't be traded out of, because it arrives already having happened.

---

## 3:27 — The evidence

> Terminal: `./start.sh scorecard` — let the table land.

Everything it does goes into an append-only journal. The panel you're looking at **reads
that journal and never writes anything** — it can't move a position, so what you see is
the record, not a second version of it.

Which lets it do this. Five strategy engines vote on every scan — trend, a Markov
persistence chain, Monte Carlo scenarios, market structure, macro odds. This marks them
against what the tape actually did. It's how I found that one of them had never made a
single call, and another was running **below** the base rate. The system grades its own
inputs.

---

## 4:20 — Results, honestly

> Terminal: `./start.sh report`. Don't hide the minus sign.

The rehearsal window is 45 proposals against 224 considered declines, 15 orders, seven
closed trades — and **down sixty-five dollars.**

I'd rather show you that than a cherry-picked green day. Six of those seven were call
credit spreads, and every loss is the same trade: short calls into a rally. That's not
variance at 224 declines, it's the menu — every risk profile could only **sell**
premium, so a bullish read had exactly one expression. The agent's own judge said so, in
the journal, before I spotted it. Long verticals went in yesterday.

---

## 5:13 — Close

> Back to the console. Hold on the live gate ledger. Fade.

Two thousand one hundred and fifty tests stand behind this, and a constitution that says
money is never a float, the journal is never rewritten, and a diagnostic may never state
something it can't support.

The model is the part that can be wrong. **Everything downstream of it is the part that
assumes it will be.**

---

## Figures, if a judge asks

| | |
|---|---|
| Gates | 18 |
| Tests | 2,150 (1,890 Python + 260 panel) |
| Proposals | 45 |
| Considered declines | 224 |
| Approved / rejected | 42 / 3 |
| Orders submitted | 15 |
| Closed positions | 7 — 1W / 5L |
| Realized P&L | −$65.00 |
| Max drawdown | 0.19% |
| Model spend | $32.76 |

**Declines** are cycles where the model chose not to propose — counted separately from
gate rejections, because they are different events. **Realized** is the dev paper
account over the rehearsal window, not the competition account.
