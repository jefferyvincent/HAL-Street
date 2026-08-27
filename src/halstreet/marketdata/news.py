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
from urllib.parse import urlsplit

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
    #: Where to read it. Empty unless it passed `safe_url` — see there for why this is
    #: the one piece of untrusted input that gets an allowlist rather than a scrub.
    url: str = ""

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

    def to_ticker(self) -> dict[str, Any]:
        """The compact form the panel scrolls, and the record of what was read.

        The journal kept a *count* — "12 headlines" — which says the catalyst had
        something to read and nothing about what. That is the one input to a cycle
        that did not come from arithmetic, and for a judged run it is the part worth
        being able to point at afterwards.

        Truncated here rather than in the panel, because this is also what goes on
        disk: a day of scanning writes a few hundred of these, and the whole article
        was never the thing being kept.

        **Still untrusted.** These are publisher strings that reached us through the
        catalyst's prompt with an explicit fence around them. Nothing downstream may
        treat one as an instruction, and the panel renders them as text — never as
        markup — for exactly that reason.
        """
        age = self.age_hours
        return {
            "ts": self.ts,
            "age_hours": None if age is None else round(age, 1),
            "source": self.source,
            "headline": self.headline[:180],
            "symbols": list(self.symbols),
            # The publisher's own page. We link to it rather than reproducing the
            # article: the body is theirs, and a headline plus a way to the source is
            # both the honest presentation and the useful one.
            "url": self.url,
        }

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


#: Schemes a headline may link to. An allowlist, not a blocklist.
#:
#: The URL is publisher-supplied and ends up in an `href` the reader clicks, which
#: makes it the one piece of untrusted input in this system that a browser will
#: *execute* rather than merely display: `javascript:` in an anchor runs on click.
#: Blocklisting the schemes one can think of is the losing side of that; naming the
#: two that are ever correct is not.
LINK_SCHEMES = ("https", "http")

#: A URL longer than this is not a link to an article.
MAX_URL = 2048


def safe_url(value: Any) -> str:
    """A publisher's link, or "" if it is not one we will put behind a click.

    Validated here rather than in the panel, and once: this is a security control, and
    a control implemented in two places is a control implemented in whichever place
    someone forgets. The panel renders what this returns and adds nothing.

    **The allowlist is the control.** Not the strip above it, which is what an earlier
    version of this comment claimed — mutation testing said otherwise, and a comment
    naming the wrong line is how the right one comes to be deleted. `urlsplit` already
    removes tab, newline and carriage return before reading the scheme, exactly as a
    browser does, so `java\tscript:alert(1)` arrives here with a scheme of
    `javascript` and is refused for being `javascript` rather than for containing a
    tab. Turn the allowlist into a blocklist and every one of those tests fails.

    The strip stays, and earns its place elsewhere: it removes whitespace and
    unprintables from the middle of an otherwise valid URL, which `urlsplit` is happy
    to leave in and which have no business in an `href`. `netloc` is required for the
    same reason — `https:alert(1)` has the right scheme and no host.
    """
    raw = "".join(ch for ch in str(value or "") if ch.isprintable() and not ch.isspace())
    if not raw or len(raw) > MAX_URL:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in LINK_SCHEMES or not parts.netloc:
        return ""
    return raw


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
            url=safe_url(row.get("url")),
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
