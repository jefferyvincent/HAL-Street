# Competition account

**Hard rule: the judged run must use a brand-new Alpaca paper account created for this hackathon.
A reused or existing account is ineligible.** Starting balance must be set to $100,000.

This is the easiest way to lose on a technicality, so treat it as infrastructure, not an errand.

## Two accounts, always

| Account | Purpose | Env file |
|---|---|---|
| `dev` | prototyping, breaking things, replaying scenarios | `.env` |
| `comp` | judged run only — never used for development | `.env.comp` |

Never point the dev config at the competition account "just to test something." The moment you do,
you cannot prove the account is clean.

## Before the judged run

Run `python -m scripts.preflight --env comp`. It must pass all of:

1. Credentials resolve to a **paper** endpoint
2. Account equity is exactly $100,000.00
3. Zero fills in account history
4. Zero open positions and zero open orders
5. Account creation date is inside the competition window
6. Account ID does not match any ID recorded in `journal/accounts-used.json`

Record the competition account ID, creation timestamp, and starting equity in the run journal on
first use. That record is what you point at if anyone asks whether the account was fresh.

## Do not

- Reset the competition account mid-competition to escape a drawdown
- Run dry-run scans against it before the official start
- Share its keys into any screenshot or build-in-public post
