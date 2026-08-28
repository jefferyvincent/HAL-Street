"""What to look at — the universe, discovered from the tape instead of typed in .env.

The agent used to scan `UNIVERSE=SPY,QQQ,IWM`. Three tickers a human picked, and a
human's picking was the only reason those three and not others. That is a fine
default and a poor claim: an agent that cannot choose its own names is doing the
second half of the job.

This module does the choosing, and it does it the way the rest of the deterministic
layer works — by counting, not by reasoning. The market-wide news feed is read, each
article's *publisher-assigned* symbol tags are tallied, and the names the tape is
talking about most come out on top. No model is involved and none should be: which
symbols an article is about is a fact, and facts belong on this side of the boundary.

**The invariant `marketdata/news` sets is kept exactly.** That module's first rule is
that "nothing here is ever parsed for meaning — a headline never becomes a symbol."
It also explains why Alpaca was chosen over RSS: "the mapping from headline to
underlying is the publisher's rather than a regex over a title." Those two sentences
are the whole basis of this module. Counting runs on `Headline.symbols`, the
structured field Benzinga attaches to the article; it never touches the headline text.
HAL solves the same problem the other way — a company-name index matched against RSS
titles — because its feeds carry no tags. Ours do, so we do not guess.

**Discovery nominates. It never approves.** A symbol reaching the end of this module
has earned a scan and nothing else. Between it and an order stand the tradability
screen below, the profile's liquidity floors, and sixteen gates. That ordering is the
point: widening the input is safe precisely because the output is unchanged.

**Why the screen is not optional.** Measured against the live feed on 2026-08-27, the
raw top of a 50-headline count was `SOLS` x4, `NVDA` x3, `ADSK` x3, `MRVL` x3 — and
below them `CYCUW` (a warrant, halted, no chain), `BTCUSD` (a crypto pair) and a row
of microcaps. Two of those cannot be traded as options at all. Screening them here
costs one asset lookup; screening them downstream costs a full committee — four model
calls — to discover there is nothing to buy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halstreet.marketdata.news import Headline

#: Headlines to read market-wide per pass. Larger than the per-symbol limit because
#: this is a census rather than a read: the question is which names recur, and a
#: sample of twelve answers it mostly by accident.
DEFAULT_SCAN = 100

#: How far back the census looks. Shorter than the per-symbol window on purpose —
#: `news.DEFAULT_LOOKBACK_HOURS` is 48 because a catalyst read wants context, and a
#: universe wants today. A name that was loud on Tuesday and silent since is not what
#: the tape is talking about now.
DEFAULT_LOOKBACK_HOURS = 24

#: Above this many tags, an article is a market roundup rather than company news.
#:
#: "Here are the twenty stocks moving today" tags twenty symbols, and counted plainly
#: it hands each of them a mention. Two such articles put the entire list above a
#: company that actually reported. The cap is deliberately generous — a real story
#: about a merger legitimately tags both sides and their sector peers — and it is a
#: threshold rather than a weight because a weighted count is one more number to
#: justify and this one only has to separate news from lists.
MAX_TAGS_PER_HEADLINE = 6

#: Symbols handed to the scan per pass. The binding constraint is cost, not taste:
#: every name is a full committee — catalyst, bull, bear, judge — so the universe
#: size multiplies the model spend of a cycle directly.
DEFAULT_SHORTLIST = 6

#: Alpaca's asset class for the only thing this agent can build a structure on.
EQUITY = "us_equity"

#: The asset attribute that says an option chain exists. Checked rather than assumed:
#: plenty of tradable US equities have no listed options, and a warrant never does.
OPTIONS_ATTR = "has_options"


@dataclass(frozen=True)
class Mention:
    """One symbol the tape named, with the evidence for why it is here."""

    symbol: str
    mentions: int
    #: The first headline that tagged it. Provenance, not analysis — it is what lets
    #: a person reading the journal afterwards see why the agent looked at this name
    #: at all. Nothing downstream parses it.
    headline: str = ""


def tally(headlines: list[Headline], *,
          max_tags: int = MAX_TAGS_PER_HEADLINE) -> list[Mention]:
    """Symbols the feed is talking about, most-mentioned first.

    Ties break alphabetically rather than by insertion order. Two runs over the same
    headlines must produce the same universe in the same order, or a cycle's scan
    depends on how the feed happened to sort itself, and nothing about a run is
    reproducible afterwards.

    Never raises. Discovery failing must not be worse than discovery being off — a
    malformed article is skipped and the rest of the census stands.
    """
    counts: dict[str, int] = {}
    first: dict[str, str] = {}
    for h in headlines:
        symbols = [s for s in (str(sym).strip().upper() for sym in h.symbols) if s]
        # Deduplicated per article: a publisher that tags the same ticker twice is
        # not two mentions, and the roundup cap must count distinct names.
        symbols = list(dict.fromkeys(symbols))
        if not symbols or len(symbols) > max_tags:
            continue
        for symbol in symbols:
            counts[symbol] = counts.get(symbol, 0) + 1
            first.setdefault(symbol, h.headline)
    return [Mention(symbol=s, mentions=n, headline=first.get(s, ""))
            for s, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def screen(asset: Any) -> tuple[bool, str]:
    """Can this name carry an options structure at all? `(ok, why not)`.

    Deliberately a *capability* check and not a quality one. Whether a chain is liquid
    enough to trade is the liquidity gate's question, asked against the real chain with
    real quotes; asking a weaker version of it here would put the same decision in two
    places with two answers. This screen only removes names where the answer is
    structural — there is no chain, or it is not an equity.

    Runs on untrusted tool output, so it never raises: a shape it does not recognise
    is refused, not exploded on. Discovery that throws takes the entire scan with it.
    """
    if not isinstance(asset, dict):
        return False, "unreadable asset record"
    if str(asset.get("class") or "") != EQUITY:
        return False, f"not a US equity ({asset.get('class') or 'unknown class'})"
    if str(asset.get("status") or "") != "active":
        return False, "not active"
    if not asset.get("tradable"):
        return False, "not tradable"
    attributes = asset.get("attributes")
    if not isinstance(attributes, list) or OPTIONS_ATTR not in attributes:
        return False, "no options listed on it"
    return True, ""
