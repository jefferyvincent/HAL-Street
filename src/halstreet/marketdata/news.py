"""Recent headlines for an underlying, from Alpaca's news endpoint via MCP.

Why this exists. Everything else the agent knows is computed from a chain and a
series of bars — arithmetic over numbers the market published. That is the whole of
`strategy/`, and it is deliberately blind to the reason a price moved. A vol-crush
after a Fed statement and a vol-crush after nothing at all look identical to an HV
rank. News is the one input a rules engine cannot derive, which is exactly why it
belongs on the model's side of the boundary rather than in the ranking.

Why Alpaca rather than RSS. Everything the agent knows about the market arrives
through the MCP server, and a second data path with its own failure modes, its own
rate limits and its own idea of which symbols an article is about would weaken a
claim this project actually makes. `get_news` is Benzinga-sourced and tags each
article with its symbols, so the mapping from headline to underlying is the
publisher's rather than a regex over a title.

**Every field here is attacker-controllable text.** Alpaca's own MCP envelope says so
in as many words — `trust: untrusted_tool_output`, `risk: external_text` — and it is
right to. Anyone who can get a headline published can put a sentence in front of a
model that is about to size a trade. Three things follow, and none of them is
optional:

  1. Nothing here is ever parsed for meaning. A headline never becomes a symbol, a
     strike, a size or a limit. It is text handed to a model and nothing else.
  2. It is truncated hard and stripped of the constructs injection leans on — URLs,
     code fences, and the role markers that make a paragraph look like an instruction.
  3. The real answer is downstream: the model's output is a proposal, and a proposal
     faces sixteen gates that cannot be argued with. The worst a successful injection
     achieves is a *bad trade proposal*, which is the case the gates already exist
     for. That is the point of putting the model between two deterministic layers —
     it means untrusted input can be allowed in at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

#: Headlines per underlying. Enough for a read on the tape, few enough that the
#: catalyst analyst is looking at today rather than skimming a week.
DEFAULT_LIMIT = 12

#: How far back to look. A headline older than this is not news, it is context, and
#: the strategy engine has already priced whatever it did.
DEFAULT_LOOKBACK_HOURS = 48

#: Per-field truncation. Long enough to carry a real headline and the gist of a
#: summary; short enough that a wall of text cannot crowd out the actual instructions.
MAX_HEADLINE = 200
MAX_SUMMARY = 400

# Constructs that exist to make text read as instruction rather than as data. Removing
# them is not a security boundary — the gates are — but it removes the cheap attempts.
_STRIP = re.compile(
    r"https?://\S+"                       # links: nothing here should be followed
    r"|```|~~~"                           # code fences
    r"|<\|[^|]*\|>"                       # chat-template role markers
    r"|^\s*(?:system|assistant|user|tool)\s*:",  # a line pretending to open a turn
    re.IGNORECASE | re.MULTILINE,
)


def _clean(value: Any, limit: int) -> str:
    text = _STRIP.sub(" ", str(value or ""))
    text = " ".join(text.split())
    return text[: limit - 1] + "…" if len(text) > limit else text


@dataclass(frozen=True)
class Headline:
    """One article, reduced to what a catalyst read actually uses."""

    ts: str
    headline: str
    source: str
    summary: str = ""
    #: Every symbol the publisher tagged — the article may be about a peer, not us.
    symbols: tuple[str, ...] = ()

    @property
    def age_hours(self) -> float | None:
        """Hours since publication, or None when the timestamp cannot be trusted.

        The subtraction is inside the `try` because it is the half that actually
        failed. `fromisoformat` accepts a naive timestamp happily and returns a naive
        datetime; subtracting that from an aware one raises `TypeError` one line later,
        outside the guard. That propagated out of `to_prompt`, out of the catalyst
        stage, and was caught at the cycle level — so a single off-contract article
        abandoned the entire scan for that underlying, and went on doing it every cycle
        until the article aged out of the 48-hour window.

        Which is the exact outcome this module's own docstring rules out: news is an
        enrichment, and a news problem must never become a trading problem.

        A naive timestamp is off-contract — Alpaca sends RFC-3339 with a `Z` — so it is
        reported as unknown rather than assumed to be UTC. Assuming would be a guess
        that can be wrong by hours; unknown is true, renders as "unknown" in the
        prompt, and simply does not count toward the freshness tally. That understates
        how new an article is, which is the safe direction: the catalyst treats it as
        context rather than as breaking news.
        """
        try:
            return (datetime.now(UTC) - datetime.fromisoformat(self.ts)).total_seconds() / 3600
        except (TypeError, ValueError):
            return None

    def to_prompt(self) -> dict[str, Any]:
        age = self.age_hours
        return {
            "when": "unknown" if age is None else f"{age:.0f}h ago",
            "source": self.source,
            "headline": self.headline,
            **({"summary": self.summary} if self.summary else {}),
            # Kept because a headline tagged with eleven tickers is macro noise, and a
            # model reading it as company news would be reading it wrong.
            "also_tagged": list(self.symbols),
        }


def parse(payload: Any, *, limit: int = DEFAULT_LIMIT) -> list[Headline]:
    """Turn the tool's response into headlines. Never raises on a shape it dislikes.

    News is an enrichment, not a dependency: a cycle with no headlines must scan and
    propose exactly as before. A parser that threw would turn a quiet news day into a
    missed trading cycle.
    """
    rows: Any = payload
    if isinstance(rows, dict):
        rows = rows.get("news") or rows.get("articles") or rows.get("data") or []
    if not isinstance(rows, list):
        return []

    out: list[Headline] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        headline = _clean(row.get("headline"), MAX_HEADLINE)
        if not headline:
            continue
        symbols = row.get("symbols") or []
        out.append(Headline(
            ts=str(row.get("created_at") or row.get("updated_at") or ""),
            headline=headline,
            source=_clean(row.get("source") or row.get("author"), 40),
            summary=_clean(row.get("summary") or row.get("content"), MAX_SUMMARY),
            symbols=tuple(str(s) for s in symbols if s)[:12],
        ))
    return out


def window(hours: int = DEFAULT_LOOKBACK_HOURS) -> str:
    """The `start` argument, as a date-time the API accepts."""
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")


def summarize(headlines: list[Headline]) -> str:
    """A one-line description for the journal. Counts, not content.

    The journal records that news was read and how much of it, not what it said. The
    articles themselves are the publisher's copyrighted text and they are untrusted
    input; neither belongs replicated in a permanent local record of our own trading.
    """
    if not headlines:
        return "no headlines in window"
    fresh = sum(1 for h in headlines if (a := h.age_hours) is not None and a <= 6)
    sources = len({h.source for h in headlines if h.source})
    return f"{len(headlines)} headline(s) from {sources} source(s), {fresh} within 6h"
