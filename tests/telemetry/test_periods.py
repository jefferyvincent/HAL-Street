"""P&L over the windows a trader asks for.

Two numbers per window and they are not the same number. Realized is what closed
trades made — exact, off the ledger, and zero on a day the desk held rather than a day
it lost. Equity change is mark-to-market: it moves with open positions, which is what
most people mean by "today's P&L", and it is the one that can be quietly wrong.

The quiet wrongness is the point of most of these tests. A journal that begins on the
27th cannot say what the month did, and computing it anyway produces a figure labelled
MTD that means "since this file was created" — plausible, precise, and false.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from halstreet.agent.hippocampus.ledger import Ledger, OpenStructure
from halstreet.telemetry import pnl

TODAY = date(2026, 8, 27)          # a Thursday
MONDAY = date(2026, 8, 24)


def closed(when: str, realized_entry: str = "-1.60", exit_price: str = "1.69",
           **over) -> OpenStructure:
    base = {
        "structure_id": when, "name": "spread", "underlying": "SPY", "qty": 1,
        "legs": {"SPY261016C00755000": -1}, "opened_at": "2026-08-01T14:00:00+00:00",
        "entry_price": Decimal(realized_entry), "exit_price": Decimal(exit_price),
        "closed_at": when,
    }
    return OpenStructure(**{**base, **over})


def ledger_of(*structures) -> Ledger:
    return Ledger(path=None, structures=list(structures))  # type: ignore[arg-type]


def equity(*pairs) -> list[tuple[str, Decimal]]:
    return [(ts, Decimal(v)) for ts, v in pairs]


# --- the windows ----------------------------------------------------------------

@pytest.mark.parametrize("period,start", [
    ("day", TODAY),
    ("week", MONDAY),
    ("month", date(2026, 8, 1)),
    ("year", date(2026, 1, 1)),
    ("all", None),
])
def test_windows_are_calendar_not_trailing(period, start):
    """"This month" means since the first, not the last thirty days. A figure labelled
    MTD that quietly means the latter is the kind of wrong nobody catches."""
    assert pnl.period_start(period, TODAY) == start


def test_the_week_starts_on_monday_even_on_a_monday():
    assert pnl.period_start("week", MONDAY) == MONDAY


def test_every_window_is_reported_even_when_empty():
    rows = pnl.by_period(ledger_of(), [], today=TODAY)
    assert [r["period"] for r in rows] == list(pnl.PERIODS)


# --- realized -------------------------------------------------------------------

def test_realized_counts_only_what_closed_inside_the_window():
    led = ledger_of(closed("2026-08-27T18:00:00+00:00"),      # today
                    closed("2026-08-26T18:00:00+00:00"),      # yesterday, same week
                    closed("2026-07-15T18:00:00+00:00"))      # last month
    rows = {r["period"]: r for r in pnl.by_period(led, [], today=TODAY)}

    assert rows["day"]["closed"] == 1
    assert rows["week"]["closed"] == 2
    assert rows["month"]["closed"] == 2
    assert rows["year"]["closed"] == 3
    assert rows["all"]["closed"] == 3


def test_a_window_with_nothing_closed_made_nothing():
    """Zero rather than absent. A day the desk held is a fact, not a gap."""
    led = ledger_of(closed("2026-07-15T18:00:00+00:00"))
    (day,) = [r for r in pnl.by_period(led, [], today=TODAY) if r["period"] == "day"]
    assert day["realized_usd"] == 0
    assert day["closed"] == 0


def test_an_open_position_contributes_no_realized():
    """It has not realized anything. That is what open means."""
    still_on = OpenStructure(structure_id="x", name="n", underlying="SPY", qty=1,
                             legs={"SPY261016C00755000": -1},
                             opened_at="2026-08-27T14:00:00+00:00",
                             entry_price=Decimal("-1.51"))
    (day,) = [r for r in pnl.by_period(ledger_of(still_on), [], today=TODAY)
              if r["period"] == "day"]
    assert day["realized_usd"] == 0
    assert day["closed"] == 0


def test_a_structure_with_no_exit_price_counts_as_closed_but_adds_nothing():
    """Closed with an unknown fill. Counting it as a trade is true; inventing its P&L
    is not."""
    half = closed("2026-08-27T18:00:00+00:00", exit_price="0")
    half.exit_price = None
    (day,) = [r for r in pnl.by_period(ledger_of(half), [], today=TODAY)
              if r["period"] == "day"]
    assert day["closed"] == 1
    assert day["realized_usd"] == 0


@pytest.mark.parametrize("when", [None, "", "not-a-date", 17])
def test_a_structure_with_an_unreadable_close_date_is_skipped(when):
    """Rather than counted in every window, or crashing a route polled every five
    seconds."""
    bad = closed("2026-08-27T18:00:00+00:00")
    bad.closed_at = when
    rows = pnl.by_period(ledger_of(bad), [], today=TODAY)
    assert all(r["closed"] == 0 for r in rows)


# --- mark to market -------------------------------------------------------------

def test_the_day_is_measured_from_the_last_reading_before_it():
    """Not the first reading inside it. On a day with one scan those are the same
    sample, and the day would always show exactly zero."""
    rows = {r["period"]: r for r in pnl.by_period(ledger_of(), equity(
        ("2026-08-26T19:00:00+00:00", "100000"),
        ("2026-08-27T14:00:00+00:00", "99000"),
        ("2026-08-27T19:00:00+00:00", "99500"),
    ), today=TODAY)}
    assert rows["day"]["equity_change_usd"] == Decimal(-500)


def test_a_window_the_samples_do_not_reach_reports_nothing():
    """The whole point. A journal that starts today cannot say what the month did."""
    rows = {r["period"]: r for r in pnl.by_period(ledger_of(), equity(
        ("2026-08-27T14:00:00+00:00", "89816.97"),
        ("2026-08-27T19:00:00+00:00", "89795.92"),
    ), today=TODAY)}

    assert rows["day"]["equity_change_usd"] == Decimal("-21.05")
    assert rows["day"]["covered"] is True
    for window in ("week", "month", "year"):
        assert rows[window]["equity_change_usd"] is None, window
        assert rows[window]["covered"] is False, window


def test_all_is_measured_from_the_first_sample_there_is():
    """It has no start to sit before. Treating it like the others made every sample
    both the opening and the closing, and reported a flat zero over the whole
    journal — which it did, until this test."""
    (row,) = [r for r in pnl.by_period(ledger_of(), equity(
        ("2026-08-27T14:00:00+00:00", "89816.97"),
        ("2026-08-27T19:00:00+00:00", "89795.92"),
    ), today=TODAY) if r["period"] == "all"]
    assert row["equity_change_usd"] == Decimal("-21.05")


def test_a_window_the_samples_do_reach_is_measured():
    rows = {r["period"]: r for r in pnl.by_period(ledger_of(), equity(
        ("2026-08-20T19:00:00+00:00", "100000"),
        ("2026-08-27T19:00:00+00:00", "101000"),
    ), today=TODAY)}
    assert rows["week"]["equity_change_usd"] == Decimal(1000)
    assert rows["month"]["equity_change_usd"] is None, "August 1 is before the samples"


def test_no_equity_at_all_covers_nothing():
    rows = pnl.by_period(ledger_of(), [], today=TODAY)
    assert all(r["equity_change_usd"] is None for r in rows)
    assert all(r["covered"] is False for r in rows)


def test_the_first_session_is_reported_so_the_panel_can_say_why():
    (row,) = [r for r in pnl.by_period(ledger_of(), equity(
        ("2026-08-27T14:00:00+00:00", "100")), today=TODAY) if r["period"] == "week"]
    assert row["since"] == "2026-08-27"


def test_realized_and_marked_are_kept_apart():
    """A held position moves one and not the other, and collapsing them would make a
    drift look like a booked loss."""
    led = ledger_of(closed("2026-08-27T18:00:00+00:00"))
    (day,) = [r for r in pnl.by_period(led, equity(
        ("2026-08-26T19:00:00+00:00", "100000"),
        ("2026-08-27T19:00:00+00:00", "99000"),
    ), today=TODAY) if r["period"] == "day"]

    assert day["realized_usd"] == Decimal("-9.00")
    assert day["equity_change_usd"] == Decimal(-1000)
