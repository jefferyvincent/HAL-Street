"""The event-risk term, which was a constant across the entire traded universe.

`event_risk_for(underlying)` answered from a frozen set of tickers that do not report
earnings. Every symbol this agent trades — SPY, QQQ, IWM — was in that set, so the
term returned `none` on every candidate ever scored. One of six weighted terms,
inert, for the whole life of the project.

The reasoning behind the set was not wrong; it was answering a narrower question than
the term's name. An index does not report earnings. That says nothing about a macro
print, and nothing about a single holding large enough to move the index by itself —
which is what a live committee run flagged: a Fed decision and an NVDA report inside a
51-DTE window, against `event_risk 0.0` on all six candidates.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from halstreet.marketdata import events
from halstreet.strategy import scoring

TODAY = date(2026, 8, 26)


# --- the window, which is the part that makes the term discriminate ----------------

def test_two_expiries_on_one_underlying_no_longer_score_the_same():
    """The whole point. An event 20 days out is inside a 45-DTE structure and outside
    a 7-DTE one, and until now both got the same answer."""
    window = scoring.EventWindow(known=True, days_out=(20,))
    assert window.risk_for(7) == scoring.EVENT_NONE
    assert window.risk_for(45) == scoring.EVENT_PRESENT


def test_an_unread_calendar_is_not_a_clear_calendar():
    """`known=False` and `known=True, days_out=()` are different answers.

    Collapsing them is precisely the bug: one says the window was checked and is
    clear, the other says it could not be checked. Only the first removes a penalty.
    """
    assert scoring.EventWindow(known=False).risk_for(45) == scoring.EVENT_UNKNOWN
    assert scoring.EventWindow(known=True).risk_for(45) == scoring.EVENT_NONE
    assert scoring.event_penalty(scoring.EVENT_UNKNOWN) == 1.0
    assert scoring.event_penalty(scoring.EVENT_NONE) == 0.0


def test_an_event_already_past_does_not_count():
    assert scoring.EventWindow(known=True, days_out=(-3,)).risk_for(45) == scoring.EVENT_NONE


def test_the_penalty_actually_moves_a_score():
    """Guard against the term being wired up but weighted to nothing."""
    common = {"kind": "put_credit_spread", "max_gain_usd": 60.0, "max_loss_usd": 440.0,
              "slippage_usd": 8.0, "pop": 0.78}
    clear = scoring.score(**common, dte=30,
                          ctx=scoring.Context(events=scoring.EventWindow(known=True)))
    spanned = scoring.score(**common, dte=30,
                            ctx=scoring.Context(
                                events=scoring.EventWindow(known=True, days_out=(10,))))
    assert spanned.total < clear.total, "an event inside the window must cost something"


# --- who is watched ---------------------------------------------------------------

def test_an_index_watches_the_names_that_can_move_it_alone():
    """QQQ is roughly a tenth NVDA. That is concentration wearing a diversified name."""
    watching = events.watch_list("QQQ")
    assert "NVDA" in watching and "AVGO" in watching
    assert "QQQ" in watching


def test_a_single_name_watches_only_itself():
    assert events.watch_list("NVDA") == {"NVDA"}


# --- failure is `unknown`, never `none` -------------------------------------------

def test_a_failed_lookup_reports_unknown_rather_than_a_clear_window(monkeypatch):
    """A network error must never read as good news.

    `events_between` returning None and returning [] are the two answers the caller
    has to keep apart, and this is the case where getting it wrong removes a penalty
    on exactly the day it was there to apply.
    """
    def boom(*_a, **_k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(events.httpx.Client, "get", boom)
    monkeypatch.setattr(events, "_cached", lambda _day: None)
    got = events.events_between("QQQ", TODAY, TODAY + timedelta(days=10))
    assert got is None
    assert scoring.EventWindow(known=got is not None).risk_for(45) == scoring.EVENT_UNKNOWN
    assert "unavailable" in events.describe(got)


def test_a_hole_in_the_window_is_not_a_clear_window(monkeypatch):
    """One unreadable day poisons the whole answer, deliberately.

    Reporting the days that did load would be a calendar with a gap in it presented
    as a calendar — and the gap is exactly where an unnoticed event would sit.
    """
    calls = {"n": 0}

    def flaky(day, **_):
        calls["n"] += 1
        return [] if calls["n"] < 3 else None

    monkeypatch.setattr(events, "fetch_day", flaky)
    assert events.events_between("QQQ", TODAY, TODAY + timedelta(days=10)) is None


def test_a_small_constituent_is_not_an_index_event(monkeypatch):
    """Only a holding big enough to move the index counts as one of its events."""
    rows = [{"symbol": "AVGO", "marketCap": "$1,697,219,159,835", "time": "time-after-hours"},
            {"symbol": "NVDA", "marketCap": "$8,000,000,000", "time": "time-after-hours"}]
    monkeypatch.setattr(events, "fetch_day",
                        lambda day, **_: rows if day == TODAY else [])
    got = events.events_between("QQQ", TODAY, TODAY + timedelta(days=3))
    assert [e.symbol for e in got] == ["AVGO"], "a $8bn NVDA does not move QQQ"


def test_an_underlying_reporting_for_itself_is_flagged_as_itself(monkeypatch):
    monkeypatch.setattr(events, "fetch_day",
                        lambda day, **_: [{"symbol": "NVDA", "marketCap": "$5,155,810,000,000",
                                           "time": "time-after-hours"}] if day == TODAY else [])
    got = events.events_between("NVDA", TODAY, TODAY + timedelta(days=3))
    assert got and got[0].via == "itself"


@pytest.mark.parametrize("cap,counts", [("$5,155,810,000,000", True), ("$1,000", False)])
def test_market_cap_parses_out_of_nasdaqs_formatting(cap, counts):
    assert (events._cap(cap) >= events.MIN_MARKET_CAP_USD) is counts
