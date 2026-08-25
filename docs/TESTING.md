# Testing

One rule: **every gate has a test that proves it rejects.**

A gate that has only ever been tested on the happy path is decoration. For each gate in
`gates/`, write a paired test:

- a proposal that should pass
- a proposal that violates exactly that gate, and must be rejected with the right reason

These tests are also the demo. Showing a judge a test suite where a deliberately reckless
LLM proposal gets stopped by name is a stronger argument than any backtest curve.

Suggested adversarial cases:

| Case | Expected rejection |
|---|---|
| Naked short call | undefined risk |
| Structure with max loss > cap | position risk limit |
| Third position on the same underlying | concentration limit |
| Short leg 2 DTE | DTE floor |
| Leg with 3 open interest | liquidity floor |
| Bid/ask 40% wide | spread width |
| Live (non-paper) credentials present | environment assertion |
| Proposal referencing a strike not in the chain | contract validation |

Run: `pytest tests/gates -v`
