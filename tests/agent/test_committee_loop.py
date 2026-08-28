"""`Agent._committee_proposal` — the orchestration as production runs it.

`test_committee.py` covers the stages and proves they compose. It does not prove the
*loop* composes them that way, and the difference is the whole point of a committee: a
judge that ran before the debate is four calls buying one call's worth of decision, and
every stage-level test would still pass.

So this drives the real method against a stub broker and a scripted committee. What it
watches is order, degradation, and the journal — the three things that are invisible
from inside any single stage.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import ExitPolicy
from halstreet.agent.cortex import committee as C
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.gates.base import Limits
from halstreet.marketdata.news import Headline
from halstreet.telemetry.journal import Journal

HEADLINE = Headline(ts="2026-08-26T12:00:00+00:00", headline="Fed holds",
                    source="wire", symbols=("SPY",))


class _Broker:
    option_feed = "indicative"

    def __init__(self, headlines=(HEADLINE,)):
        self._headlines = list(headlines)
        self.news_calls = []

    async def get_news(self, underlying: str, **_):
        self.news_calls.append(underlying)
        return list(self._headlines)


class _Recorder:
    """A committee that records the order it was called in and what it was handed."""

    def __init__(self, *, catalyst_error=None, debate_errors=(), judge=None):
        self.order: list[str] = []
        self.seen: dict[str, object] = {}
        self._catalyst_error = catalyst_error
        self._debate_errors = list(debate_errors)
        self._judge = judge

    def catalyst(self, *, underlying, headlines, evidence):
        self.order.append("catalyst")
        self.seen["evidence"] = evidence
        self.seen["headlines"] = list(headlines)
        v = (C.Verdict(error=self._catalyst_error) if self._catalyst_error
             else C.Verdict(lean="bearish", confidence=0.8, note="Fed on Wednesday"))
        return v, {"in": 100, "out": 10, "cache_read": 0}

    def debate(self, brief):
        self.order.append("debate")
        self.seen["debate_brief"] = brief
        bull = "" if any(e.startswith("bull") for e in self._debate_errors) else "BULL ARG"
        bear = "" if any(e.startswith("bear") for e in self._debate_errors) else "BEAR ARG"
        return bull, bear, {"in": 200, "out": 20, "cache_read": 0}, list(self._debate_errors)

    def judge(self, *, system, brief):
        self.order.append("judge")
        self.seen["judge_system"] = system
        self.seen["judge_brief"] = brief
        from halstreet.agent.cortex.llm import LLMResult
        return (self._judge or LLMResult(None, error="scripted")), \
               {"in": 400, "out": 40, "cache_read": 7}


class _Writer:
    system_prompt = "THE REAL RULES INCLUDING EVERY GATE"


class _Bias:
    direction, reasons = "bullish", ["ema", "rsi"]


class _Regime:
    label, rank, realized_vol = "low", Decimal("0.51"), Decimal("0.12")


@pytest.fixture
def harness(tmp_path):
    def build(broker=None, committee=None, ledger=None):
        broker = broker or _Broker()
        committee = committee or _Recorder()
        journal = Journal.open(tmp_path / "run.jsonl")
        agent = Agent(
            broker, writer=_Writer(), limits=Limits(), journal=journal,
            ledger=ledger or Ledger.load(tmp_path / "ledger.json"),
            policy=ExitPolicy(take_profit_pct=Decimal(50), stop_loss_pct=Decimal(200),
                              force_close_dte=5),
            dry_run=True, breaker=CircuitState(baseline_equity=Decimal(100000),
                                               baseline_day="2026-08-26"),
            committee=committee,
        )
        return agent, broker, committee, journal
    return build


def _menu():
    """One candidate of each family, so the burn table has something to rank."""
    from halstreet.strategy import profiles as P
    from halstreet.strategy.candidates import Candidate
    return [Candidate(name=f"a {kind}", kind=kind, legs=[], net=Decimal("-1.00"),
                      max_loss_usd=Decimal(400), max_gain_usd=Decimal(100), dte=45,
                      score=Decimal("0.5"))
            for kind in P.VERTICALS_AND_CONDORS]


async def _run(agent, base_turn="THE MENU", candidates=None):
    return await agent._committee_proposal(
        underlying="SPY", base_turn=base_turn,
        candidates=_menu() if candidates is None else candidates,
        state={"bias": _Bias(), "regime": _Regime()})


def _committee_event(journal):
    return next(e for e in journal.read() if e.get("event") == "committee")


# --- order ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_stages_run_catalyst_then_debate_then_judge(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    assert com.order == ["catalyst", "debate", "judge"]


@pytest.mark.asyncio
async def test_the_researchers_argue_the_catalyst_read_but_not_each_other(harness):
    # The debate brief is built after the catalyst and before either researcher runs.
    # Building it a line later would hand each side the other's case and turn two
    # independent reads into one conversation.
    agent, _, com, _ = harness()
    await _run(agent)
    brief = com.seen["debate_brief"]
    assert "Fed on Wednesday" in brief
    assert "BULL ARG" not in brief and "BEAR ARG" not in brief


@pytest.mark.asyncio
async def test_the_judge_sees_everything_the_committee_produced(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    brief = com.seen["judge_brief"]
    assert "Fed on Wednesday" in brief
    assert "BULL ARG" in brief and "BEAR ARG" in brief
    assert "THE MENU" in brief, "the ranked menu must still be the thing being decided"


@pytest.mark.asyncio
async def test_the_researchers_are_framed_and_the_judge_is_not(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    assert com.seen["debate_brief"].startswith(C._DEBATE_FRAME)
    assert not com.seen["judge_brief"].startswith(C._DEBATE_FRAME)


@pytest.mark.asyncio
async def test_the_judge_runs_under_the_writers_own_system_prompt(harness):
    # Not a copy. A second statement of the rules is a second thing to update when a
    # gate is added, and the judge would be the copy nobody remembers.
    agent, _, com, _ = harness()
    await _run(agent)
    assert com.seen["judge_system"] == _Writer.system_prompt


# --- the news ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_news_is_fetched_once_and_reaches_the_catalyst(harness):
    agent, broker, com, journal = harness()
    await _run(agent)
    assert broker.news_calls == ["SPY"]
    assert com.seen["headlines"] == [HEADLINE]
    assert _committee_event(journal)["headlines"] == 1


@pytest.mark.asyncio
async def test_a_silent_tape_still_runs_the_committee(harness):
    # No headlines is a normal Tuesday, not an outage. The debate and the judge are
    # worth running on the desk's own numbers alone.
    agent, _, com, journal = harness(broker=_Broker(headlines=[]))
    await _run(agent)
    assert com.order == ["catalyst", "debate", "judge"]
    assert _committee_event(journal)["headlines"] == 0


@pytest.mark.asyncio
async def test_the_desks_deterministic_reads_reach_the_catalyst(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    ev = com.seen["evidence"]
    assert ev["bias"] == "bullish" and ev["vol_regime"] == "low"
    # The rank is a realized-vol proxy, and an analyst that reads it as IV rank will
    # call a quiet tape expensive. Said in the evidence rather than assumed.
    assert "not IV rank" in ev["note"]


# --- degradation -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_failed_catalyst_does_not_stop_the_committee(harness):
    agent, _, com, journal = harness(committee=_Recorder(catalyst_error="timeout"))
    await _run(agent)
    assert com.order == ["catalyst", "debate", "judge"]
    assert "catalyst: timeout" in _committee_event(journal)["errors"]


@pytest.mark.asyncio
async def test_a_missing_researcher_is_named_in_the_journal_and_to_the_judge(harness):
    # The failure that actually happened on the first live run, at the level that
    # would have surfaced it: the judge decided having heard one side, and the only
    # trace is this line.
    agent, _, com, journal = harness(
        committee=_Recorder(debate_errors=["bull: truncated at max_tokens=1600"]))
    await _run(agent)
    assert "bull: truncated at max_tokens=1600" in _committee_event(journal)["errors"]
    assert "truncated" in com.seen["judge_brief"]


@pytest.mark.asyncio
async def test_every_stage_failing_still_returns_and_still_journals(harness):
    agent, _, _, journal = harness(committee=_Recorder(
        catalyst_error="timeout", debate_errors=["bull: timeout", "bear: timeout"]))
    llm, tokens = await _run(agent)
    assert llm.error == "scripted"
    rec = _committee_event(journal)
    assert len(rec["errors"]) == 3
    assert tokens["in"] == 700, "four calls that produced nothing still cost four calls"


# --- the record --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_whole_session_is_journalled_once_after_the_judge(harness):
    # After, so the record carries the whole session's cost. Written before the judge
    # it would understate every committee cycle by its largest call.
    agent, _, _, journal = harness()
    events = [e for e in journal.read() if e.get("event") == "committee"]
    assert events == []
    await _run(agent)
    rec = _committee_event(journal)
    assert rec["tokens"] == {"in": 700, "out": 70, "cache_read": 7}
    assert rec["bull"] == "BULL ARG" and rec["bear"] == "BEAR ARG"
    assert rec["catalyst"]["note"] == "Fed on Wednesday"


@pytest.mark.asyncio
async def test_the_reported_cost_is_the_committees_not_the_judges(harness):
    # The return value feeds the cycle's token accounting. Returning only the judge's
    # counts would make the committee path look 40% cheaper than it is, on the one
    # number anyone would check before turning it on.
    _, tokens = await _run(harness()[0])
    assert tokens == {"in": 700, "out": 70, "cache_read": 7}


@pytest.mark.asyncio
async def test_closed_trades_on_this_underlying_reach_the_judge(harness, tmp_path):
    """Reflection comes from the ledger, not from the model's memory of the session.

    An agent that reasons about its own past trades from recollection is reasoning
    about a story. These are the ones that closed and what they actually made — a real
    ledger here rather than a stub, because the arithmetic that turns two net prices
    into a realized figure is the part worth getting in front of a judge correctly.
    """
    from halstreet.agent.hippocampus.ledger import OpenStructure

    ledger = Ledger.load(tmp_path / "reflect.json")
    ledger.structures.extend([
        OpenStructure(structure_id="a", name="SPY 765/770 call spread", underlying="SPY",
                      qty=1, legs={"SPY261016C00765000": 1, "SPY261016C00770000": -1},
                      opened_at="2026-08-01T14:00:00", closed_at="2026-08-10T14:00:00",
                      entry_price=Decimal("-1.00"), exit_price=Decimal("2.20"),
                      rationale="sold into a low-IV tape"),
        OpenStructure(structure_id="b", name="QQQ 500/505 put spread", underlying="QQQ",
                      qty=1, legs={}, opened_at="2026-08-02T14:00:00",
                      closed_at="2026-08-11T14:00:00",
                      entry_price=Decimal("-1.00"), exit_price=Decimal("0.10")),
        OpenStructure(structure_id="c", name="SPY still open", underlying="SPY", qty=1,
                      legs={}, opened_at="2026-08-20T14:00:00"),
    ])

    agent, _, com, journal = harness(ledger=ledger)
    await _run(agent)

    record = _committee_event(journal)["reflection"]
    assert [r["structure"] for r in record] == ["SPY 765/770 call spread"], \
        "this underlying only, and only what closed"
    # Sold for 1.00 credit, bought back at 2.20: (-2.20 - -1.00) * 100 = -120.
    assert record[0]["realized_usd"] == "-120.00" and record[0]["outcome"] == "loss"
    assert "-120.00" in com.seen["judge_brief"]


@pytest.mark.asyncio
async def test_an_empty_desk_record_says_so_rather_than_going_quiet(harness):
    # Silence lets the judge assume a history that is not there.
    agent, _, com, journal = harness()
    await _run(agent)
    assert _committee_event(journal)["reflection"] == []
    assert "nothing closed yet" in com.seen["judge_brief"]


@pytest.mark.asyncio
async def test_the_committee_never_reaches_the_broker_beyond_reading_news(harness):
    # `_Broker` implements get_news and nothing else. Any other broker call raises
    # AttributeError, so this passing is the assertion.
    agent, broker, _, _ = harness()
    await _run(agent)
    assert broker.news_calls == ["SPY"]


# --- the burn table ------------------------------------------------------------------
#
# Added with news discovery. The judge used to be handed a ranked menu and a
# paragraph, and had to work out both what the news implied about direction and which
# structure expresses it. The second half is arithmetic — `strategy/burn` does it — and
# these tests pin that its answer actually reaches the people arguing.

@pytest.mark.asyncio
async def test_the_researchers_argue_against_the_burn_table(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    assert "BURN TEST" in com.seen["debate_brief"]


@pytest.mark.asyncio
async def test_the_judge_sees_the_burn_table_too(harness):
    agent, _, com, _ = harness()
    await _run(agent)
    assert "BURN TEST" in com.seen["judge_brief"]


@pytest.mark.asyncio
async def test_the_table_is_built_after_the_catalyst_so_it_can_use_the_news_read(harness):
    """Order, not content. The catalyst's lean is an input to the table.

    Built one stage earlier it would be a restatement of the price trend, which the
    ranking already has — the whole reason it sits between the catalyst and the debate
    is that it is the first point where both reads exist.
    """
    agent, _, com, _ = harness()
    await _run(agent)
    # `_Recorder.catalyst` returns bearish 0.8; `_Bias` is bullish. That is a conflict,
    # and a conflict can only be detected by something that has seen both.
    assert "conflicted" in com.seen["debate_brief"]


@pytest.mark.asyncio
async def test_a_failed_catalyst_leaves_a_table_built_on_the_chart_alone(harness):
    """Degradation, like every other stage. No news is not no table."""
    agent, _, com, _ = harness(committee=_Recorder(catalyst_error="503"))
    await _run(agent)
    assert "BURN TEST" in com.seen["debate_brief"]
    assert "no-news" in com.seen["debate_brief"]


@pytest.mark.asyncio
async def test_the_burn_table_is_journalled_with_the_rest_of_the_session(harness):
    """It is deterministic, so it is reconstructable — but only if the menu is kept.

    The menu is not: candidates are journalled per cycle and the table is the reading
    of them. Recording the verdict costs a few hundred bytes and makes "why did the
    judge favour the condor" answerable from one event.
    """
    agent, _, _, journal = harness()
    await _run(agent)
    burn = _committee_event(journal)["burn"]
    assert burn["agreement"] == "conflicted"
    assert {r["kind"] for r in burn["structures"]}
