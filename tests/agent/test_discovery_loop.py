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


#: Marker snapshots. The chain arithmetic itself is tested in tests/strategy; here
#: the question is only whether the loop reads a chain and acts on the answer.
LIQUID, WIDE = "LIQUID", "WIDE"

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
        self.chains_read: list[str] = []

    async def get_market_news(self, **_):
        if self._news_raises:
            raise RuntimeError("feed is down")
        return list(self._headlines)

    async def get_asset(self, symbol):
        self.asked.append(symbol)
        if symbol in self._asset_raises:
            raise RuntimeError("asset lookup exploded")
        return dict(self._assets.get(symbol, OPTIONABLE))

    # Every candidate that clears the asset screen is then measured against its own
    # chain, so a broker in these tests has to have one. Liquid by default: the tests
    # above are about counting and screening assets, not about liquidity.
    async def get_option_chain(self, underlying, **_):
        self.chains_read.append(underlying)
        return {"snapshots": {LIQUID: {}}}

    async def get_option_contracts(self, underlying, **_):
        return []


class _Writer:
    system_prompt = "RULES"


@pytest.fixture(autouse=True)
def stub_chain_arithmetic(monkeypatch):
    """Stand in for the chain maths; this file tests the wiring around it.

    `generate` and `leg_ok` have their own tests against a real Black-Scholes chain
    in tests/strategy/test_candidates.py.
    """
    monkeypatch.setattr("halstreet.agent.cerebellum.loop.enrich",
                        lambda snaps, contracts: snaps)
    monkeypatch.setattr("halstreet.agent.cerebellum.loop.buildable",
                        lambda chain, limits, profile, dte, asof:
                            6 if LIQUID in chain else 0)


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


# --- the liquidity screen -------------------------------------------------------------
#
# The point of discovery was to widen the universe. It was not widening it. Six names
# came back per pass and five of them could never trade: measured on the live chains,
# SPY's median bid-ask at 45 DTE is 4% and it built six candidates, while ESTC (13%),
# S (46%) and BBY (53%) built none against an 8% ceiling. The agent was still trading
# exactly one symbol, and the other five slots were spent proving it.
#
# So a name now earns its slot by having a chain that could produce a structure. This
# is not a second liquidity gate — it asks `candidates.leg_ok`, the same question the
# menu builder asks of every leg, and the sixteen gates still decide everything after.
# It only declines to spend a scan on a chain that has already answered.

class _Chains(_Broker):
    """A broker whose chains differ by symbol, so the screen has something to decide."""

    def __init__(self, headlines=(), assets=None, *, liquid=(), raises=(), **kw):
        super().__init__(headlines, assets, **kw)
        self._liquid = set(liquid)
        self._chain_raises = set(raises)

    async def get_option_chain(self, underlying, **_):
        self.chains_read.append(underlying)
        if underlying in self._chain_raises:
            raise RuntimeError("chain unavailable")
        return {"snapshots": {LIQUID if underlying in self._liquid else WIDE: {}}}


@pytest.mark.asyncio
async def test_a_name_whose_chain_cannot_trade_does_not_get_a_slot(build):
    broker = _Chains([_h("BBY"), _h("BBY"), _h("SPY")], liquid={"SPY"})
    agent, _ = build(broker)
    assert await agent.discover(limit=2) == ["SPY"]


@pytest.mark.asyncio
async def test_the_next_name_down_takes_the_slot_instead(build):
    """The slot is not lost with the name. That is the whole point of screening."""
    broker = _Chains([_h("BBY"), _h("BBY"), _h("S"), _h("SPY")], liquid={"SPY"})
    agent, _ = build(broker)
    assert await agent.discover(limit=1) == ["SPY"]


@pytest.mark.asyncio
async def test_the_refusal_says_it_was_the_chain_and_not_the_asset(build):
    """"No options listed" and "options nobody will quote" are different facts,
    and the second is the one that changes tomorrow."""
    broker = _Chains([_h("BBY"), _h("SPY")], liquid={"SPY"})
    agent, journal = build(broker)
    await agent.discover(limit=2)
    row = next(r for r in _tally(journal) if r["symbol"] == "BBY")
    assert row["status"] == "refused" and "no structure" in row["reason"].lower()


@pytest.mark.asyncio
async def test_a_chain_that_will_not_load_costs_that_name_and_no_other(build):
    broker = _Chains([_h("BOOM"), _h("SPY")], liquid={"SPY"}, raises={"BOOM"})
    agent, _ = build(broker)
    assert await agent.discover(limit=2) == ["SPY"]


@pytest.mark.asyncio
async def test_no_chain_is_read_for_a_name_the_asset_screen_already_refused(build):
    """A warrant has no chain to fetch. Asking anyway is a round trip for a 404."""
    broker = _Chains([_h("CYCUW"), _h("SPY")], assets={"CYCUW": WARRANT}, liquid={"SPY"})
    agent, _ = build(broker)
    await agent.discover(limit=2)
    assert "CYCUW" not in broker.chains_read


@pytest.mark.asyncio
async def test_it_stops_reading_chains_once_the_shortlist_is_full(build):
    broker = _Chains([_h(f"S{i}") for i in range(20)],
                     liquid={f"S{i}" for i in range(20)})
    agent, _ = build(broker)
    await agent.discover(limit=3)
    assert len(broker.chains_read) == 3


@pytest.mark.asyncio
async def test_it_gives_up_examining_rather_than_walking_the_whole_census(build):
    """A census names seventy-odd symbols and each one costs two broker calls.

    On a thin pre-market where nothing is liquid, walking the lot is minutes of
    silence at the top of every pass, repeated every thirty minutes. Better a short
    universe now than a full one late — and the cap is per pass, so a name below it
    gets its turn as soon as the tape reshuffles.
    """
    broker = _Chains([_h(f"S{i}") for i in range(80)], liquid=set())
    agent, _ = build(broker)
    assert await agent.discover(limit=6) == []
    assert len(broker.chains_read) <= discovery.MAX_EXAMINED


@pytest.mark.asyncio
async def test_the_cap_is_generous_enough_to_fill_a_shortlist(build):
    """It took 19 examined to find 6 on the live tape. A cap under that would bite
    on an ordinary day, which is the one thing it must not do."""
    assert discovery.MAX_EXAMINED >= 30


@pytest.mark.asyncio
async def test_names_never_examined_are_recorded_as_such_not_as_refused(build):
    """The distinction the heat map already draws. Hitting the cap must not start
    claiming the agent judged names it never looked at."""
    broker = _Chains([_h(f"S{i}") for i in range(80)], liquid=set())
    agent, journal = build(broker)
    await agent.discover(limit=6)
    statuses = {r["status"] for r in _tally(journal)}
    assert "not-reached" in statuses
