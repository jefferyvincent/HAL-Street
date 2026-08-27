"""What the panel is handed for each leg, and what it is deliberately not handed.

Two routes carry leg detail and they carry different halves. `/api/marks` prices them
live; the chart route carries the fills, which come off the order and never change. The
split matters: the snapshot is polled every five seconds and must not reach the broker,
and the chart route is opened only when someone looks at a position.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.ledger import OpenStructure
from halstreet.agent.manager import ExitPolicy
from halstreet.telemetry import structure_chart
from halstreet.telemetry.server import _legs_view

SHORT, LONG = "QQQ261016C00765000", "QQQ261016C00775000"
FILLS = {SHORT: Decimal("4.51"), LONG: Decimal(3)}


def structure(**over) -> OpenStructure:
    base = {
        "structure_id": "s1", "name": "QQQ 2026-10-16 765/775 call credit spread",
        "underlying": "QQQ", "qty": 1, "legs": {SHORT: -1, LONG: 1},
        "opened_at": "2026-08-27T16:40:25+00:00", "entry_price": Decimal("-1.51"),
        "entry_filled": True, "order_id": "ord-1", "entry_legs": dict(FILLS),
    }
    return OpenStructure(**{**base, **over})


CHAIN = {
    SHORT: {"latestQuote": {"bp": "4.55", "ap": "4.65"}},
    LONG: {"latestQuote": {"bp": "2.94", "ap": "3.04"}},
}


def by_symbol(rows):
    return {r["symbol"]: r for r in rows}


# --- /api/marks -----------------------------------------------------------------

def test_each_leg_carries_its_fill_its_mid_and_its_pnl():
    legs = by_symbol(_legs_view(structure(), CHAIN))

    assert legs[SHORT]["basis"] == Decimal("4.51")
    assert legs[SHORT]["mid"] == Decimal("4.60")
    assert legs[SHORT]["unrealized_usd"] == Decimal(-9)
    assert legs[LONG]["unrealized_usd"] == Decimal(-1)


def test_dollar_figures_are_scaled_by_size_and_the_basis_is_not():
    """A price does not change when you trade ten; a P&L does."""
    one = by_symbol(_legs_view(structure(qty=1), CHAIN))
    ten = by_symbol(_legs_view(structure(qty=10), CHAIN))

    assert one[SHORT]["basis"] == ten[SHORT]["basis"] == Decimal("4.51")
    assert ten[SHORT]["unrealized_usd"] == one[SHORT]["unrealized_usd"] * 10
    assert ten[SHORT]["value_usd"] == one[SHORT]["value_usd"] * 10
    assert ten[SHORT]["contracts"] == -10
    assert ten[SHORT]["signed"] == -1, "the ratio, unscaled — the panel shows contracts"


def test_a_short_legs_value_is_negative_because_closing_it_costs_money():
    legs = by_symbol(_legs_view(structure(), CHAIN))
    assert legs[SHORT]["value_usd"] < 0
    assert legs[LONG]["value_usd"] > 0


def test_a_leg_with_no_recorded_fill_reports_no_pnl_rather_than_a_guess():
    legs = by_symbol(_legs_view(structure(entry_legs=None), CHAIN))
    assert all(row["basis"] is None for row in legs.values())
    assert all(row["unrealized_usd"] is None for row in legs.values())
    assert all(row["mid"] is not None for row in legs.values()), "still priced"


def test_a_leg_with_no_quote_reports_no_mid_and_no_pnl():
    chain = {SHORT: CHAIN[SHORT]}
    legs = by_symbol(_legs_view(structure(), chain))
    assert legs[LONG]["mid"] is legs[LONG]["unrealized_usd"] is None
    assert legs[LONG]["basis"] == Decimal(3), "the fill is a record, not a quote"
    assert legs[SHORT]["mid"] is not None


def test_the_legs_are_in_the_ledgers_own_order():
    """So the table does not reshuffle between polls."""
    assert [r["symbol"] for r in _legs_view(structure(), CHAIN)] == [SHORT, LONG]


def test_bid_and_ask_are_carried_so_a_wide_market_is_visible():
    legs = by_symbol(_legs_view(structure(), CHAIN))
    assert (legs[SHORT]["bid"], legs[SHORT]["ask"]) == (Decimal("4.55"), Decimal("4.65"))


# --- the chart route ------------------------------------------------------------

def build(s):
    return structure_chart.build(s, {}, ExitPolicy())


def test_the_chart_carries_the_entry_fill_with_no_broker_call():
    """The fills are on the ledger, so a chart drawn with no price history still has them."""
    legs = by_symbol(build(structure())["legs"])
    assert legs[SHORT]["basis"] == "4.51"
    assert legs[LONG]["basis"] == "3"
    assert legs[SHORT]["exit"] is None


def test_a_closed_structure_carries_its_exit_and_its_realized_pnl_per_leg():
    closed = structure(closed_at="2026-08-27T19:30:00+00:00",
                       exit_price=Decimal("1.20"), exit_filled=True,
                       exit_legs={SHORT: Decimal("2.05"), LONG: Decimal("0.85")})
    legs = by_symbol(build(closed)["legs"])

    # Sold at 4.51, bought back at 2.05: a gain, and `signed` is negative.
    assert legs[SHORT]["realized_usd"] == "246.00"
    assert legs[LONG]["realized_usd"] == "-215.00"


def test_the_legs_realized_sums_to_the_structures_realized():
    """Same identity as the live side, on the closed side. Not "close to" — equal."""
    closed = structure(closed_at="2026-08-27T19:30:00+00:00",
                       exit_price=Decimal("1.20"), exit_filled=True,
                       exit_legs={SHORT: Decimal("2.05"), LONG: Decimal("0.85")})
    parts = sum(Decimal(r["realized_usd"]) for r in build(closed)["legs"])
    assert parts == closed.realized()


@pytest.mark.parametrize("qty", [1, 3])
def test_the_closed_identity_holds_at_any_size(qty):
    closed = structure(qty=qty, closed_at="2026-08-27T19:30:00+00:00",
                       exit_price=Decimal("1.20"), exit_filled=True,
                       exit_legs={SHORT: Decimal("2.05"), LONG: Decimal("0.85")})
    assert sum(Decimal(r["realized_usd"]) for r in build(closed)["legs"]) == closed.realized()


def test_a_half_known_round_trip_reports_no_realized_per_leg():
    """An exit whose legs were never read must not be silently valued at the entry."""
    closed = structure(closed_at="2026-08-27T19:30:00+00:00",
                       exit_price=Decimal("1.20"), exit_legs=None)
    assert all(r["realized_usd"] is None for r in build(closed)["legs"])


def test_prices_reach_the_wire_as_strings():
    """`float` would round a cent away, and the sums above are asserted exact."""
    legs = build(structure())["legs"]
    assert all(isinstance(r["basis"], str) for r in legs)


def test_the_chart_never_carries_a_live_price():
    """It is built from the ledger and the bars. Live marks are the other route's job.

    Folding them in would put a broker round trip behind a chart, and the chart is
    already the slow route.
    """
    assert not {"mid", "bid", "ask", "unrealized_usd"} & set(build(structure())["legs"][0])
