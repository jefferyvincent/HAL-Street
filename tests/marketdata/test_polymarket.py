"""Macro odds as a number, from a venue that prices them.

The catalyst reads headlines, and headlines are prose about probability: this
afternoon's judge quoted "Sept hike odds now favor a hike" off a Benzinga wire. At the
same moment Polymarket had that market at 50.5 cents — a coin flip, not a lean. One of
those is a claim somebody wrote and the other is a price somebody paid, and the second
is the one worth putting in front of a model.

**A signal, never a position.** Nothing here is tradeable by this agent: it trades US
equity options on Alpaca and that is the whole universe. These are read-only odds that
reach the catalyst as evidence, the same way the earnings calendar does.

Everything below runs offline against recorded payload shapes. The network path is one
`httpx` call with a hard timeout that degrades to silence, and a test that reached the
internet would fail on a train.
"""

from __future__ import annotations

import json

import httpx
import pytest

from halstreet.marketdata import polymarket as pm

PAYLOAD = [
    {"question": "Fed Rate Hike by September 2026 Meeting?",
     "outcomes": '["Yes", "No"]', "outcomePrices": '["0.505", "0.495"]',
     "volumeNum": 4_200_000.0, "endDate": "2026-09-17T00:00:00Z", "closed": False},
    {"question": "Will PPI YoY be 5.1% or more in August?",
     "outcomes": '["Yes", "No"]', "outcomePrices": '["0.6", "0.4"]',
     "volumeNum": 180_000.0, "endDate": "2026-09-10T00:00:00Z", "closed": False},
    {"question": "Will BMO fail by end of 2026?",
     "outcomes": '["Yes", "No"]', "outcomePrices": '["0.0275", "0.9725"]',
     "volumeNum": 900.0, "endDate": "2026-12-31T00:00:00Z", "closed": False},
]


def client_returning(payload, status: int = 200) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- reading the venue -------------------------------------------------------------

def test_a_market_becomes_a_question_and_a_price():
    odds = pm.fetch(client=client_returning(PAYLOAD))
    assert odds is not None
    first = odds[0]
    assert first.question.startswith("Fed Rate Hike")
    assert first.yes == pytest.approx(0.505)


def test_prices_arrive_as_json_inside_json_and_are_unwrapped():
    """The venue serialises `outcomes` and `outcomePrices` as strings containing JSON.
    Read naively that is a price of `["0.505", "0.495"]`, which is not a number."""
    odds = pm.fetch(client=client_returning(PAYLOAD))
    assert all(isinstance(o.yes, float) for o in odds)


def test_a_market_too_thin_to_price_is_left_out():
    """A 0.0275 quote on nine hundred dollars of volume is not a probability anyone
    staked anything on. Carrying it would put a confident-looking number in front of
    the model with almost nothing behind it."""
    odds = pm.fetch(client=client_returning(PAYLOAD))
    assert not any("BMO" in o.question for o in odds)


def test_the_deepest_markets_come_first():
    odds = pm.fetch(client=client_returning(PAYLOAD))
    assert [o.volume_usd for o in odds] == sorted(
        (o.volume_usd for o in odds), reverse=True)


# --- degrading to silence ------------------------------------------------------------

def test_a_venue_that_is_down_is_silence_not_an_exception():
    """It sits inside the read that feeds every cycle. A prediction market being
    unreachable must not stop the agent trading options."""
    def handler(_r):
        raise httpx.ConnectError("no route")
    assert pm.fetch(client=httpx.Client(transport=httpx.MockTransport(handler))) is None


@pytest.mark.parametrize("status", [400, 429, 500, 503])
def test_an_error_status_is_silence(status):
    assert pm.fetch(client=client_returning([], status=status)) is None


@pytest.mark.parametrize("junk", ['{"not": "a list"}', "[]", '[{"question": "x"}]',
                                  '[{"question": "x", "outcomePrices": "oops"}]'])
def test_a_payload_it_cannot_read_yields_nothing_rather_than_guessing(junk):
    payload = json.loads(junk)
    assert pm.fetch(client=client_returning(payload)) in (None, [])


def test_none_and_empty_are_different_answers():
    """`None` is "could not ask". `[]` is "asked, nothing deep enough to report". The
    catalyst must be able to tell those apart — Article VII."""
    assert pm.fetch(client=client_returning([])) == []


# --- the shape the model sees ---------------------------------------------------------

def test_the_prompt_carries_the_price_the_venue_and_the_depth():
    """A probability with no source and no size is a number to be trusted blindly."""
    odds = pm.fetch(client=client_returning(PAYLOAD))
    shape = odds[0].to_prompt()
    assert shape["yes_pct"] == 50.5
    assert shape["venue"] == "polymarket"
    assert shape["volume_usd"] >= 1_000_000


def test_it_cannot_be_mistaken_for_something_tradeable():
    """The one confusion worth engineering against. This agent trades US equity
    options and nothing else; these are evidence about the macro backdrop."""
    shape = pm.fetch(client=client_returning(PAYLOAD))[0].to_prompt()
    assert "not tradeable" in shape["note"].lower()


# --- reaching the cycle -----------------------------------------------------------

def test_the_odds_are_fetched_once_for_the_pass_not_once_per_name():
    """A claim about the macro backdrop is not per-symbol work. Fetched inside the
    per-underlying loop it would be six identical HTTP calls for one answer."""
    import inspect

    from halstreet.agent.cerebellum import loop
    once = inspect.getsource(loop.Agent.run_once)
    cycle = inspect.getsource(loop.Agent.run_cycle)
    assert "polymarket.fetch" in once
    assert "polymarket" not in cycle


def test_the_fetch_is_kept_off_the_event_loop():
    """`httpx.Client` is blocking. Called directly it stops every other coroutine —
    including the one that would notice a stop signal."""
    import inspect

    from halstreet.agent.cerebellum import loop
    source = inspect.getsource(loop.Agent.run_once)
    assert "asyncio.to_thread(polymarket.fetch)" in source


def test_a_single_cycle_has_no_macro_read_rather_than_a_stale_one():
    """`run_cycle` alone — which is what the tests and a one-symbol run use — never
    sets it. None is the honest answer there, and it is not the same as `[]`."""
    import inspect

    from halstreet.agent.cerebellum.loop import Agent
    assert "self.macro: list | None = None" in inspect.getsource(Agent.__init__)


def test_the_catalyst_is_told_which_kind_of_nothing_it_is_looking_at():
    """None is "could not ask the venue". [] is "asked, nothing deep enough". A
    backdrop that could not be read must not render as a quiet one — Article VII."""
    import inspect

    from halstreet.agent.cerebellum import loop
    source = inspect.getsource(loop.Agent._committee_proposal)
    assert "None if self.macro is None" in source
