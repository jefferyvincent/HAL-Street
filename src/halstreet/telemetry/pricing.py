"""What a run cost, from the tokens it actually spent.

Two rules hold this together, and both exist because a wrong number here is worse
than no number.

**Prices are configuration, not constants.** They change, they differ per account, and
this file cannot know them. One is shipped because it is sourced — Claude Opus 5 at
$5/$25 per million tokens — and the rest are left for `LLM_PRICES` to supply. A model
with no configured price has its tokens counted and its cost reported as unknown,
never as zero: a total that quietly omits a quarter of the spend is a total that lies
by exactly the amount nobody notices.

**Cached input is excluded and said to be.** Anthropic reports `cache_read_input_tokens`
separately from `input_tokens` and bills it at a discount this file has no sourced
figure for. Applying the list price to it would overstate; applying a guessed discount
would be a guess with a dollar sign in front. It is counted, shown, and left out of the
arithmetic, which is the only one of the three that is true.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation

#: Dollars per million tokens, as (input, output).
#:
#: Only what is sourced. Opus 5 is documented at $5/$25 per MTok; the analyst tier's
#: price is not in anything this project can cite, so it is absent rather than
#: approximated — and the console shows its tokens under "unpriced" until someone
#: fills it in, which is a visible gap rather than a silent understatement.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5": (Decimal(5), Decimal(25)),
}

#: A million. Prices are quoted per MTok and usage is counted in tokens.
PER = Decimal(1000000)


def from_env() -> dict[str, tuple[Decimal, Decimal]]:
    """The price table, with `LLM_PRICES` merged over the shipped defaults.

        LLM_PRICES='{"claude-sonnet-5": [3, 15]}'

    Malformed JSON is ignored rather than fatal. This is a display figure on a
    read-only panel; a typo in an environment variable must not stop the agent
    reporting, and an unpriced model is already a state the console renders.
    """
    table = dict(PRICES)
    raw = (os.environ.get("LLM_PRICES") or "").strip()
    if not raw:
        return table
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return table
    if not isinstance(parsed, dict):
        return table
    for model, pair in parsed.items():
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        try:
            price_in, price_out = Decimal(str(pair[0])), Decimal(str(pair[1]))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if price_in < 0 or price_out < 0:
            continue
        table[str(model)] = (price_in, price_out)
    return table


def cost(model: str, *, tokens_in: int, tokens_out: int,
         table: dict[str, tuple[Decimal, Decimal]] | None = None) -> Decimal | None:
    """What one model's usage cost, or None when its price is not configured.

    None rather than zero. Zero is a claim, and it is the wrong one.
    """
    prices = (table if table is not None else from_env()).get(str(model))
    if prices is None:
        return None
    price_in, price_out = prices
    return (Decimal(tokens_in) * price_in + Decimal(tokens_out) * price_out) / PER


__all__ = ["PER", "PRICES", "cost", "from_env"]
