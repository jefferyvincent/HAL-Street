"""`Agent.discover` — the universe, chosen by the agent rather than typed into .env.

`marketdata/discovery` counts and screens; this is the orchestration around it, and
the orchestration is where the risks are. Three of them, each with tests below.

  1. **It must never take the scan down with it.** Discovery runs first in a cycle.
     A census that raises, or a screen that trips over one bad ticker, would cost the
     agent every name — including the ones it was already trading. The old universe
     was a constant and could not fail; this one can, so it has to fail small.

  2. **It must be bounded.** Every name is a full committee — catalyst, bull, bear,
     judge — so an unbounded shortlist multiplies the model spend of a cycle by
     however talkative the tape was that morning.

  3. **It must be auditable afterwards.** "Why did the agent trade PFE on Tuesday?"
     has to be answerable from the journal, and "the news mentioned it four times,
     here is the first headline" is that answer. A universe nobody can reconstruct is
     worse than a hardcoded one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import ExitPolicy
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.gates.base import Limits
from halstreet.marketdata import discovery
from halstreet.marketdata.news import Headline
from halstreet.telemetry.journal import Journal


def _h(*symbols, headline="A thing happened"):
    return Headline(ts="2026-08-27T12:00:00Z", headline=headline,
                    source="benzinga", symbols=tuple(symbols))


OPTIONABLE = {"class": "us_equity", "status": "active", "tradable": True,
              "attributes": ["has_options"]}
WARRANT = {"class": "us_equity", "status": "active", "tradable": True,
           "attributes": ["overnight_halted"]}


class _Broker:
    option_feed = "indicative"

    def __init__(self, headlines=(), assets=None, *, news_raises=False,
                 asset_raises=()):
        self._headlines = list(headlines)
        self._assets = assets or {}
        self._news_raises = news_raises
        self._asset_raises = set(asset_raises)
        self.asked: list[str] = []

    async def get_market_news(self, **_):
        if self._news_raises:
            raise RuntimeError("feed is down")
        return list(self._headlines)

    async def get_asset(self, symbol):
        self.asked.append(symbol)
        if symbol in self._asset_raises:
            raise RuntimeError("asset lookup exploded")
        return dict(self._assets.get(symbol, OPTIONABLE))


class _Writer:
    system_prompt = "RULES"


@pytest.fixture
def build(tmp_path):
    def _build(broker):
        journal = Journal.open(tmp_path / "run.jsonl")
        agent = Agent(
            broker, writer=_Writer(), limits=Limits(), journal=journal,
            ledger=Ledger.load(tmp_path / "ledger.json"),
            policy=ExitPolicy(take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200),
                              force_close_dte=5),
            dry_run=True,
            breaker=CircuitState(baseline_equity=Decimal(100000),
                                 baseline_day="2026-08-27"),
        )
        return agent, journal
    return _build


def _event(journal, name):
    return next((e for e in journal.read() if e.get("event") == name), None)


def _tally(journal):
    return _event(journal, "discovery")["tally"]


# --- the happy path ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_most_mentioned_tradable_names_come_back_in_order(build):
    agent, _ = build(_Broker([_h("NVDA"), _h("NVDA"), _h("PFE")]))
    assert await agent.discover(limit=5) == ["NVDA", "PFE"]


@pytest.mark.asyncio
async def test_the_shortlist_is_capped_because_every_name_costs_a_committee(build):
    agent, _ = build(_Broker([_h(f"S{i}") for i in range(20)]))
    assert len(await agent.discover(limit=3)) == 3


@pytest.mark.asyncio
async def test_a_name_with_no_option_chain_is_dropped_and_the_next_one_takes_its_place(build):
    """The live feed's actual top-ranked name on 2026-08-27 was a halted warrant."""
    broker = _Broker([_h("CYCUW"), _h("CYCUW"), _h("CYCUW"), _h("NVDA")],
                     assets={"CYCUW": WARRANT})
    agent, _ = build(broker)
    assert await agent.discover(limit=2) == ["NVDA"]


@pytest.mark.asyncio
async def test_screening_stops_once_the_shortlist_is_full(build):
    """An asset lookup per candidate, over 86 distinct symbols, is 86 round trips.

    The census routinely names that many. Screening the whole census to then throw
    away all but six is most of a minute of broker calls for nothing.
    """
    broker = _Broker([_h(f"S{i}") for i in range(40)])
    agent, _ = build(broker)
    await agent.discover(limit=3)
    assert len(broker.asked) < 10


# --- failing small ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_dead_news_feed_yields_no_names_rather_than_an_exception(build):
    agent, _ = build(_Broker(news_raises=True))
    assert await agent.discover(limit=5) == []


@pytest.mark.asyncio
async def test_one_exploding_asset_lookup_does_not_cost_the_other_names(build):
    broker = _Broker([_h("NVDA"), _h("BOOM"), _h("PFE")], asset_raises={"BOOM"})
    agent, _ = build(broker)
    assert "NVDA" in await agent.discover(limit=5)


@pytest.mark.asyncio
async def test_a_quiet_tape_is_an_empty_universe_not_a_crash(build):
    agent, _ = build(_Broker([]))
    assert await agent.discover(limit=5) == []


# --- the audit trail --------------------------------------------------------------
#
# One `tally` rather than separate picked/refused lists. The heat map wants the whole
# census — the names that were scanned, the ones the screen threw out, and the long
# tail below the cut that was never looked at — and three lists that must be kept in
# step are three chances to disagree about what the agent saw.

@pytest.mark.asyncio
async def test_the_journal_records_why_each_scanned_name_was_chosen(build):
    agent, journal = build(_Broker([_h("NVDA", headline="Nvidia beats"), _h("NVDA")]))
    await agent.discover(limit=5)
    row = _tally(journal)[0]
    assert row["symbol"] == "NVDA" and row["mentions"] == 2
    assert row["headline"] == "Nvidia beats" and row["status"] == "scanned"


@pytest.mark.asyncio
async def test_the_journal_records_what_was_refused_and_on_what_grounds(build):
    """A name the agent looked at and rejected is evidence the screen is working.

    Without it, a warrant that stops appearing is indistinguishable from a feed that
    stopped mentioning it.
    """
    agent, journal = build(_Broker([_h("CYCUW"), _h("NVDA")], assets={"CYCUW": WARRANT}))
    await agent.discover(limit=5)
    row = next(r for r in _tally(journal) if r["symbol"] == "CYCUW")
    assert row["status"] == "refused" and "no options" in row["reason"]


@pytest.mark.asyncio
async def test_the_names_below_the_cut_are_recorded_as_never_looked_at(build):
    """Not the same as refused, and the heat map must not draw them the same.

    The walk stops when the shortlist fills, so everything after it is unscreened —
    the agent has no opinion about whether those names are tradable. Showing them as
    rejected would claim knowledge nobody has.
    """
    agent, journal = build(_Broker([_h("A"), _h("A"), _h("B"), _h("C")]))
    await agent.discover(limit=1)
    by = {r["symbol"]: r["status"] for r in _tally(journal)}
    assert by == {"A": "scanned", "B": "not-reached", "C": "not-reached"}


@pytest.mark.asyncio
async def test_the_whole_census_is_recorded_not_only_the_shortlist(build):
    """Six names off four headlines and six off four hundred are different claims."""
    agent, journal = build(_Broker([_h(f"S{i}") for i in range(9)]))
    await agent.discover(limit=2)
    event = _event(journal, "discovery")
    assert event["headlines"] == 9 and event["symbols"] == 9
    assert len(event["tally"]) == 9


@pytest.mark.asyncio
async def test_the_tally_is_ordered_hottest_first(build):
    agent, journal = build(_Broker([_h("HOT"), _h("HOT"), _h("HOT"), _h("WARM"),
                                    _h("WARM"), _h("COOL")]))
    await agent.discover(limit=5)
    assert [r["mentions"] for r in _tally(journal)] == [3, 2, 1]


@pytest.mark.asyncio
async def test_a_lookup_that_exploded_is_recorded_as_refused_not_as_unseen(build):
    """It *was* reached. Saying otherwise hides a broker fault as a quiet tail."""
    agent, journal = build(_Broker([_h("BOOM")], asset_raises={"BOOM"}))
    await agent.discover(limit=5)
    row = next(r for r in _tally(journal) if r["symbol"] == "BOOM")
    assert row["status"] == "refused" and "lookup failed" in row["reason"]


# --- the census as a feed ------------------------------------------------------------
#
# The tally keeps a symbol, a count and one headline string — enough to draw a heat
# map, and not enough to be a news item. No timestamp means no age and no ordering; no
# URL means nothing to click. So the census journals the articles themselves as well,
# in the same shape a committee read does, and the ticker draws from both.

@pytest.mark.asyncio
async def test_the_census_journals_the_articles_not_only_the_counts(build):
    agent, journal = build(_Broker([_h("NVDA", headline="Nvidia beats")]))
    await agent.discover(limit=5)
    feed = _event(journal, "discovery")["feed"]
    assert feed[0]["headline"] == "Nvidia beats"


@pytest.mark.asyncio
async def test_a_census_article_carries_what_a_ticker_item_needs(build):
    """Age and a link are the two the tally cannot supply, and both are load-bearing:
    the strip is ordered by recency and every item is meant to be clickable."""
    agent, journal = build(_Broker([_h("NVDA")]))
    await agent.discover(limit=5)
    assert set(_event(journal, "discovery")["feed"][0]) >= {
        "ts", "age_hours", "source", "headline", "symbols", "url"}


@pytest.mark.asyncio
async def test_the_feed_is_bounded_so_a_loud_morning_does_not_bloat_the_journal(build):
    """A census reads a hundred headlines a pass, every pass, all day.

    The ticker shows a couple of dozen and orders by recency, so everything past the
    newest slice is written and never read. The census stays a hundred — the *count*
    is what ranks the map — but the journal keeps only what can surface.
    """
    agent, journal = build(_Broker([_h(f"S{i}") for i in range(80)]))
    await agent.discover(limit=2)
    event = _event(journal, "discovery")
    assert event["headlines"] == 80, "the census itself must not shrink"
    assert len(event["feed"]) == discovery.FEED_KEPT


@pytest.mark.asyncio
async def test_the_feed_keeps_the_newest_because_that_is_what_the_strip_shows(build):
    """The broker returns newest-first, so the slice is the head, not a sample."""
    old = _h("OLD", headline="From yesterday")
    new = [_h(f"N{i}", headline=f"Fresh {i}") for i in range(discovery.FEED_KEPT)]
    agent, journal = build(_Broker([*new, old]))
    await agent.discover(limit=1)
    texts = [a["headline"] for a in _event(journal, "discovery")["feed"]]
    assert "From yesterday" not in texts


@pytest.mark.asyncio
async def test_a_dead_feed_journals_nothing_rather_than_a_broken_event(build):
    agent, journal = build(_Broker(news_raises=True))
    await agent.discover(limit=5)
    assert _event(journal, "discovery") is None
