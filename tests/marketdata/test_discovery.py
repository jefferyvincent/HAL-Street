"""Symbol discovery — where the agent decides *what to look at*, not what to trade.

This is a boundary worth being careful at. Until now the universe was three tickers
in `.env`, and the model's whole job was choosing a structure on a name a human had
picked. Discovery moves the choice of *name* upstream of the model, and the input it
moves it onto is a feed of attacker-controllable text.

Two claims hold the design up, and both are tested here.

  1. **A headline is still never parsed for meaning.** Counting runs on the
     publisher's own `symbols` tag — structured metadata Benzinga attaches to the
     article — and never on the headline text. `marketdata/news` chose Alpaca over
     RSS for exactly this reason: "the mapping from headline to underlying is the
     publisher's rather than a regex over a title." Discovery keeps that. Nothing
     here reads a sentence.

  2. **Discovery nominates; it never approves.** A symbol that comes out of this
     module has done nothing but earn a look. It still faces the tradability screen
     below, then the liquidity floors, then the sixteen gates. The worst a poisoned
     feed achieves is wasting a scan on a name that gets rejected — which is the
     case the gates already exist for.

The fixtures are shaped from a real market-wide `get_news` response, checked live on
2026-08-27: 50 headlines carried 86 distinct symbols, and the top of the raw count was
a halted warrant (`CYCUW`), a crypto pair (`BTCUSD`) and a clutch of microcaps. That
run is why the screen is not optional and why it is tested against those exact shapes.
"""

from __future__ import annotations

import pytest

from halstreet.marketdata import discovery
from halstreet.marketdata.news import Headline


def _h(*symbols: str, headline: str = "Something happened", ts: str = "2026-08-27T12:00:00Z"):
    return Headline(ts=ts, headline=headline, source="benzinga", symbols=tuple(symbols))


# --- counting ---------------------------------------------------------------------

def test_a_symbol_is_ranked_by_how_many_headlines_tagged_it():
    ranked = discovery.tally([_h("NVDA"), _h("NVDA"), _h("MRVL")])
    assert [(m.symbol, m.mentions) for m in ranked] == [("NVDA", 2), ("MRVL", 1)]


def test_every_symbol_on_a_headline_is_counted_not_just_the_first():
    ranked = discovery.tally([_h("NVDA", "AMD")])
    assert {m.symbol for m in ranked} == {"NVDA", "AMD"}


def test_the_headline_text_is_never_read_for_symbols():
    """The one property this module must not lose.

    A headline that *says* TSLA but is tagged NVDA counts for NVDA. If discovery ever
    grows a regex over the title — a cashtag matcher, an exchange-qualified matcher,
    a company-name index — this test is what fails, and it should.
    """
    ranked = discovery.tally([_h("NVDA", headline="$TSLA soars as (NASDAQ: TSLA) Tesla rips")])
    assert [m.symbol for m in ranked] == ["NVDA"]


def test_a_tie_breaks_alphabetically_so_two_runs_agree():
    ranked = discovery.tally([_h("MRVL"), _h("AMD"), _h("NVDA")])
    assert [m.symbol for m in ranked] == ["AMD", "MRVL", "NVDA"]


def test_a_roundup_tagged_with_the_whole_market_counts_for_nobody():
    """"Here is every stock moving today" is not news about any of them.

    `marketdata/news` already says a headline tagged with eleven tickers is macro
    noise. Left in, one such article hands a free mention to twenty names at once and
    a second one puts them all above a company that actually had news.
    """
    roundup = _h(*[f"S{i}" for i in range(discovery.MAX_TAGS_PER_HEADLINE + 1)])
    assert discovery.tally([roundup]) == []


def test_a_headline_at_the_tag_limit_still_counts():
    ok = _h(*[f"S{i}" for i in range(discovery.MAX_TAGS_PER_HEADLINE)])
    assert len(discovery.tally([ok])) == discovery.MAX_TAGS_PER_HEADLINE


def test_the_first_headline_that_named_a_symbol_is_kept_as_provenance():
    """Why did the agent look at this name? A count alone does not answer that."""
    ranked = discovery.tally([_h("NVDA", headline="Nvidia beats"), _h("NVDA", headline="Later")])
    assert ranked[0].headline == "Nvidia beats"


def test_symbols_are_normalized_before_counting():
    ranked = discovery.tally([_h("nvda"), _h(" NVDA ")])
    assert [(m.symbol, m.mentions) for m in ranked] == [("NVDA", 2)]


def test_no_headlines_is_not_an_error():
    assert discovery.tally([]) == []


def test_a_headline_with_no_tags_is_skipped_without_taking_the_others_with_it():
    ranked = discovery.tally([_h(), _h("NVDA")])
    assert [m.symbol for m in ranked] == ["NVDA"]


# --- the tradability screen -------------------------------------------------------

def _asset(symbol="NVDA", cls="us_equity", tradable=True, attrs=("has_options",), status="active"):
    return {"symbol": symbol, "class": cls, "tradable": tradable,
            "attributes": list(attrs), "status": status}


def test_a_liquid_optionable_equity_survives():
    ok, why = discovery.screen(_asset())
    assert ok and why == ""


@pytest.mark.parametrize("asset,expected", [
    (_asset(symbol="CYCUW", attrs=("overnight_halted",)), "no options"),
    (_asset(symbol="BTCUSD", cls="crypto", attrs=("fractional_eh_enabled",)), "not a US equity"),
    (_asset(tradable=False), "not tradable"),
    (_asset(status="inactive"), "not active"),
])
def test_the_shapes_the_live_feed_actually_surfaced_are_refused(asset, expected):
    """Every one of these was in the top of a real market-wide count.

    `CYCUW` is a warrant, `BTCUSD` is a crypto pair. Both were tagged on real
    articles, both rank, and neither has an option chain to trade. Without this screen
    the agent spends a full committee — four model calls — discovering that.
    """
    ok, why = discovery.screen(asset)
    assert not ok and expected in why


def test_a_response_that_is_not_a_dict_is_refused_rather_than_crashing():
    """The screen runs on untrusted tool output on every cycle.

    An `AttributeError` here aborts discovery, and discovery aborting takes the whole
    scan with it — the same failure `news.parse` is written to avoid.
    """
    for junk in (None, "NVDA", [], 7):
        ok, why = discovery.screen(junk)
        assert not ok and why


def test_a_missing_attributes_field_reads_as_no_options_not_as_a_pass():
    ok, why = discovery.screen({"symbol": "X", "class": "us_equity", "tradable": True,
                                "status": "active"})
    assert not ok and "no options" in why
