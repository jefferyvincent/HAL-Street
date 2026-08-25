# One-page write-up — HAL Street

> Required deliverable. Judges asked for three things by name: **AI logic, risk gates, Alpaca
> infrastructure.** Structure the page in exactly those three sections, in that order, and use
> their words as the headings. Fill this in as you build; do not write it the night before.

---

## AI logic

*What the model actually decides, and what it is not allowed to decide.*

- Universe and scan cadence:
- What the strategy engine produces (deterministic candidate structures):
- What the LLM does with them (rank, size, justify) — and the exact schema it must emit:
- What the LLM explicitly does not control: strike selection bounds, position sizing ceilings,
  environment, order type
- Prompt/context strategy, and how hallucinated contracts are caught before they reach an order

## Risk gates

*The differentiator. Be specific and name each gate.*

| Gate | Rule | Rejects |
|---|---|---|
| Defined risk only | | naked/unbounded structures |
| Max loss per position | | |
| Portfolio risk ceiling | | |
| Per-underlying concentration | | |
| DTE floor | | short gamma into expiry |
| Liquidity floor | | thin OI / wide spreads |
| Delta & vega bounds | | portfolio-level drift |
| Assignment proximity | | ITM short legs near expiry |
| Environment assertion | | any non-paper credential |

State plainly: gates are deterministic Python, contain no model call, and cannot be modified by
the agent at runtime. Include the count of proposals rejected during the competition — a real
number here is more persuasive than any prose.

## Alpaca infrastructure

- MCP server: which tools consumed, how the client is wired, auth handling
- Account: brand-new dedicated paper account, starting balance $100,000
- Order flow: construction → submission → fill handling → position reconciliation
- Scheduling / hosting
- Telemetry: run journal, P&L tracking, how results were exported

## Results

- Window traded:
- Trades placed / gate rejections:
- Realized + unrealized P&L:
- Max drawdown:
- What went wrong and what you'd change:
