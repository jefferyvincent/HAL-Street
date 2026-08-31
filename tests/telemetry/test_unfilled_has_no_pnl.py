"""An order that has not filled cannot have made or lost money.

`/api/marks` priced every open structure against `entry_price` and reported the
difference as unrealized P&L. For a structure the broker has not filled, `entry_price`
is the limit we *asked* for — a price nobody paid, on contracts the account does not
hold. The console showed a $23 gain on it, then $36, on a position that did not exist.

That is the worst kind of wrong number: it looks like money, it moves like money, and
in a competition scored on P&L it is the headline figure.

The mark itself stays. A working order's current net price is real and useful — it says
how far the market is from the limit, which is exactly what someone watching an unfilled
order wants to know. What it is not is a gain.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.telemetry.server import mark_pnl


class _Structure:
    def __init__(self, filled: bool, entry: str | None = "-1.02", qty: int = 2):
        self.entry_price = None if entry is None else Decimal(entry)
        self.qty = qty
        self.entry_filled = filled


def test_a_filled_structure_is_marked_to_market():
    assert mark_pnl(_Structure(True), Decimal("-0.78")) == Decimal("48.00")


def test_an_unfilled_order_has_no_gain_and_no_loss():
    """Not zero. Zero is a position that has not moved; this is not a position."""
    assert mark_pnl(_Structure(False), Decimal("-0.78")) is None


def test_it_is_still_none_when_the_phantom_gain_would_have_been_large():
    """The size of the number is the danger. A working order far from its limit would
    have shown the biggest 'profit' on the book."""
    assert mark_pnl(_Structure(False), Decimal("2.50")) is None


def test_a_filled_structure_with_no_entry_price_is_still_unpriceable():
    """Unchanged, and for the older reason: no basis, no P&L."""
    assert mark_pnl(_Structure(True, entry=None), Decimal("-0.78")) is None


def test_a_structure_predating_the_flag_is_not_assumed_filled():
    """Absent is not evidence. Defaulting the other way reinstates the phantom."""
    class Old:
        entry_price = Decimal("-1.02")
        qty = 2

    assert mark_pnl(Old(), Decimal("-0.78")) is None


def test_the_route_uses_it():
    """Otherwise the rule exists and the payload does not obey it."""
    import inspect

    from halstreet.telemetry import server
    assert "mark_pnl(" in inspect.getsource(server.api_marks)
