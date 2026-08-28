"""Macro odds as a number, from a venue that prices them.

The catalyst reads headlines, and headlines are prose about probability. On
2026-08-28 the judge quoted "Sept hike odds now favor a hike" off a Benzinga wire; at
that moment Polymarket had the same market at 50.5 cents, which is a coin flip and not
a lean. One of those is a claim somebody wrote and the other is a price somebody paid,
and the second is worth putting in front of a model that is about to reason from the
first.

**A signal, never a position.** Nothing here is tradeable by this agent. It trades US
equity options on Alpaca and that is the entire universe — these odds reach the
catalyst as evidence about the macro backdrop, exactly as the earnings calendar does,
and `to_prompt` says so on every row so a model reading the menu cannot mistake one
for the other.

**It fails to silence.** One HTTP call with a hard timeout, and every failure mode —
unreachable venue, error status, a payload in a shape we do not recognise — returns
`None`. A prediction market being down must not stop an options agent trading options.
`None` and `[]` stay different answers: the first is "could not ask", the second is
"asked, and nothing was deep enough to report".

**Thin markets are dropped rather than reported.** A 2.75-cent quote on nine hundred
dollars of volume is not a probability anybody staked anything on, and carrying it
would put a confident-looking number in front of the model with almost nothing behind
it. The volume that survived is on every row so the model can discount further.

One more oddity worth naming: the venue serialises `outcomes` and `outcomePrices` as
*strings containing JSON*. Read naively the price of a market is `["0.505", "0.495"]`,
which is not a number and does not raise — it just quietly is not one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

#: Polymarket's public read API. No key, no account, and nothing here posts.
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"

#: The venue's own tag for economics and macro. Sports and politics dominate by
#: volume, and neither is evidence about an equity-index option.
MACRO_TAG = 100328

#: Hard. This sits in the read that runs before every cycle; a slow prediction market
#: must not become a slow trading agent.
TIMEOUT = 6.0

#: Dollars of volume below which a quote is a curiosity rather than a price.
MIN_VOLUME_USD = 25_000.0

#: How many to carry. The catalyst gets the deepest handful; a wall of macro questions
#: is the same failure as a forty-structure menu.
KEEP = 6

#: How many to ask for. Wide enough that the depth filter has something to choose from.
PAGE = 60

HEADERS = {"User-Agent": "halstreet/1.0 (+read-only macro odds)"}

_NOTE = ("prediction-market odds, one venue, not tradeable by this agent — "
         "evidence about the macro backdrop only")


@dataclass(frozen=True)
class Odds:
    """One market's price for `Yes`, with enough context to discount it."""

    question: str
    #: 0..1. The venue's price, which is the probability somebody is paying.
    yes: float
    volume_usd: float
    ends: str | None

    def to_prompt(self) -> dict:
        return {
            "question": self.question,
            "yes_pct": round(self.yes * 100, 1),
            "volume_usd": round(self.volume_usd),
            "ends": self.ends,
            "venue": "polymarket",
            "note": _NOTE,
        }


def fetch(*, client: httpx.Client | None = None,
          tag: int = MACRO_TAG, keep: int = KEEP) -> list[Odds] | None:
    """The deepest macro markets open right now, or None if the venue could not be read.

    Never raises. Every failure is `None`, which the caller reports as "could not ask"
    rather than as "nothing is happening".
    """
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers=HEADERS,
                                    follow_redirects=True)
    try:
        response = client.get(GAMMA_MARKETS, params={
            "closed": "false", "limit": PAGE, "order": "volume",
            "ascending": "false", "tag_id": tag,
        })
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None
    finally:
        if owned:
            client.close()

    if not isinstance(payload, list):
        return None
    return parse(payload, keep=keep)


def parse(rows: list, *, keep: int = KEEP) -> list[Odds]:
    """The readable, deep-enough markets among these, deepest first."""
    out: list[Odds] = []
    for row in rows:
        odds = _one(row)
        if odds is not None and odds.volume_usd >= MIN_VOLUME_USD:
            out.append(odds)
    out.sort(key=lambda o: o.volume_usd, reverse=True)
    return out[:keep]


def _one(row: object) -> Odds | None:
    """One market, or None where the row cannot be read as one."""
    if not isinstance(row, dict):
        return None
    question = str(row.get("question") or "").strip()
    if not question:
        return None

    outcomes = _json_list(row.get("outcomes"))
    prices = _json_list(row.get("outcomePrices"))
    if outcomes is None or prices is None or len(outcomes) != len(prices):
        return None

    # The `Yes` leg by name rather than by position. A market whose outcomes are
    # ordered the other way would otherwise report the exact complement of its own
    # price, which is the most convincing kind of wrong.
    try:
        index = [str(o).strip().lower() for o in outcomes].index("yes")
        yes = float(prices[index])
    except (ValueError, TypeError):
        return None
    if not 0.0 <= yes <= 1.0:
        return None

    try:
        volume = float(row.get("volumeNum") or 0.0)
    except (TypeError, ValueError):
        volume = 0.0

    ends = row.get("endDate")
    return Odds(question=question, yes=yes, volume_usd=volume,
                ends=str(ends) if ends else None)


def _json_list(value: object) -> list | None:
    """A field the venue sends as a JSON string, unwrapped. None if it will not."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None
