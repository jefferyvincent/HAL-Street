"""The ticker's two sources — what the catalyst read, and what the census saw.

Until discovery, the strip was built from one thing: the per-underlying `get_news`
call each committee makes. That is a narrow window by construction — it can only ever
show news about symbols the agent is *already* scanning, so a pinned universe of three
tickers produced the same handful of stories on a loop. Measured on a real soak:
twelve of fourteen items carried SPY, because `get_news(SPY)` returns twelve a cycle
and `get_news(IWM)` returns two.

Discovery already fetches a hundred market-wide headlines every pass to rank the
universe, and the ticker was ignoring them. It now draws from both.

The claim that has to survive the merge is provenance. "The catalyst read this before
deciding" and "this went past in the census" are different facts about an article, and
the strip's own tooltip makes the first claim. So every item says which it is, and a
census article is never described as something the desk read.
"""

from __future__ import annotations

import pytest

from halstreet.telemetry import server


def _run(tmp_path, events):
    from halstreet.telemetry.journal import Journal
    j = Journal.open(tmp_path / "run.jsonl")
    for event, fields in events:
        j.write(event, **fields)
    return server.snapshot(
        journal_path=str(tmp_path / "run.jsonl"),
        ledger_path=str(tmp_path / "ledger.json"),
        breaker_path=str(tmp_path / "circuit.json"),
    )


def _article(headline, *symbols, age=1.0, url="https://example.invalid/a"):
    return {"ts": "2026-08-28T12:00:00Z", "age_hours": age, "source": "benzinga",
            "headline": headline, "symbols": list(symbols), "url": url}


def _committee(underlying, *articles):
    return ("committee", {"underlying": underlying, "headlines": len(articles),
                          "feed": list(articles)})


def _census(*articles):
    return ("discovery", {"headlines": 100, "symbols": 5, "tally": [],
                          "feed": list(articles)})


def _by_headline(snap):
    return {h["headline"]: h for h in snap["headlines"]}


# --- the merge --------------------------------------------------------------------

def test_a_census_article_reaches_the_strip(tmp_path):
    snap = _run(tmp_path, [_census(_article("Nvidia beats", "NVDA"))])
    assert "Nvidia beats" in _by_headline(snap)


def test_a_committee_read_still_reaches_the_strip(tmp_path):
    snap = _run(tmp_path, [_committee("SPY", _article("Fed holds", "SPY"))])
    assert "Fed holds" in _by_headline(snap)


def test_both_sources_appear_together(tmp_path):
    snap = _run(tmp_path, [
        _committee("SPY", _article("Fed holds", "SPY")),
        _census(_article("Nvidia beats", "NVDA")),
    ])
    assert set(_by_headline(snap)) == {"Fed holds", "Nvidia beats"}


def test_the_same_story_from_both_sources_is_one_item(tmp_path):
    """A macro story is in the census *and* in every per-symbol read of it.

    Two entries for one article would waste a third of the strip repeating itself,
    which is the complaint this change exists to answer.
    """
    snap = _run(tmp_path, [
        _committee("SPY", _article("Fed holds", "SPY")),
        _census(_article("Fed holds", "SPY")),
    ])
    assert len(snap["headlines"]) == 1


# --- provenance -------------------------------------------------------------------

def test_an_article_the_catalyst_read_says_so(tmp_path):
    snap = _run(tmp_path, [_committee("SPY", _article("Fed holds", "SPY"))])
    row = _by_headline(snap)["Fed holds"]
    assert row["read"] is True and row["roots"] == ["SPY"]


def test_an_article_only_the_census_saw_does_not_claim_to_have_been_read(tmp_path):
    """The strip's tooltip says the catalyst read these. For a census item it did not.

    `roots` means "which of our underlyings' reads picked this up" — a census article
    was picked up by none of them, and filling that field with the publisher's tags
    would turn a fact about the desk into a fact about the publisher.
    """
    snap = _run(tmp_path, [_census(_article("Nvidia beats", "NVDA"))])
    row = _by_headline(snap)["Nvidia beats"]
    assert row["read"] is False and row["roots"] == []


def test_a_story_in_both_counts_as_read(tmp_path):
    """It was read. That the census also carried it does not make it less so."""
    snap = _run(tmp_path, [
        _census(_article("Fed holds", "SPY")),
        _committee("SPY", _article("Fed holds", "SPY")),
    ])
    assert _by_headline(snap)["Fed holds"]["read"] is True


def test_reading_order_does_not_decide_provenance(tmp_path):
    """The same two events the other way round must give the same answer."""
    snap = _run(tmp_path, [
        _committee("SPY", _article("Fed holds", "SPY")),
        _census(_article("Fed holds", "SPY")),
    ])
    assert _by_headline(snap)["Fed holds"]["read"] is True


def test_every_root_that_read_a_story_is_kept(tmp_path):
    snap = _run(tmp_path, [
        _committee("SPY", _article("Macro", "SPY", "QQQ")),
        _committee("QQQ", _article("Macro", "SPY", "QQQ")),
        _census(_article("Macro", "SPY", "QQQ")),
    ])
    assert _by_headline(snap)["Macro"]["roots"] == ["QQQ", "SPY"]


# --- what the merge must not break --------------------------------------------------

def test_the_publishers_tags_survive_so_a_census_item_can_show_a_symbol(tmp_path):
    """The strip draws chips from `roots`, and a census item has none.

    Its publisher tags are what it can show instead — which is also the variety the
    reader was missing.
    """
    snap = _run(tmp_path, [_census(_article("Nvidia beats", "NVDA", "AMD"))])
    assert _by_headline(snap)["Nvidia beats"]["symbols"] == ["NVDA", "AMD"]


def test_the_strip_stays_ordered_newest_first_across_both_sources(tmp_path):
    snap = _run(tmp_path, [
        _committee("SPY", _article("Older", "SPY", age=9.0)),
        _census(_article("Newer", "NVDA", age=0.5)),
    ])
    assert [h["headline"] for h in snap["headlines"]] == ["Newer", "Older"]


def test_the_strip_is_still_capped(tmp_path):
    many = [_article(f"Story {i}", "NVDA", age=float(i)) for i in range(120)]
    snap = _run(tmp_path, [_census(*many)])
    assert len(snap["headlines"]) == server.TICKER_HEADLINES


def test_only_the_latest_census_is_drawn(tmp_path):
    """Same rule the heat map follows. Yesterday's tape is not the tape."""
    snap = _run(tmp_path, [
        _census(_article("Yesterday", "NVDA")),
        _census(_article("Today", "NVDA")),
    ])
    assert "Yesterday" not in _by_headline(snap)


@pytest.mark.parametrize("feed", [None, "text", 7, [1, 2], [{"no": "headline"}]])
def test_a_malformed_census_feed_costs_the_census_not_the_strip(tmp_path, feed):
    """Polled every five seconds, and reading a journal older than this code."""
    snap = _run(tmp_path, [
        ("discovery", {"headlines": 1, "symbols": 1, "tally": [], "feed": feed}),
        _committee("SPY", _article("Fed holds", "SPY")),
    ])
    assert [h["headline"] for h in snap["headlines"]] == ["Fed holds"]


def test_a_census_from_before_feeds_were_journalled_is_not_an_error(tmp_path):
    snap = _run(tmp_path, [("discovery", {"headlines": 9, "symbols": 3, "tally": []})])
    assert snap["headlines"] == []
