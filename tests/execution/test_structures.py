"""Structure construction, and the broker limits it has to enforce ahead of time.

These are not risk gates — max loss, DTE and liquidity live in gates/. These cover
what Alpaca itself will refuse, so a rejection arrives with a legible reason instead
of as an opaque error after the model has already committed to the trade.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.execution.structures import (
    MAX_LEGS,
    Leg,
    PositionIntent,
    Side,
    Structure,
    StructureError,
    can_roll,
    close,
    iron_condor,
    money,
    roll,
    vertical,
    whole,
)

LONG_CALL = "SPY261218C00600000"
SHORT_CALL = "SPY261218C00605000"
FAR_CALL = "SPY261218C00610000"
SHORT_PUT = "SPY261218P00595000"
LONG_PUT = "SPY261218P00590000"


def _leg(symbol: str) -> Leg:
    return Leg(symbol, 1, Side.BUY, PositionIntent.BUY_TO_OPEN)


# --- serialisation: everything crosses the wire as a string ------------------

def test_prices_serialise_as_plain_penny_strings():
    assert money(Decimal("1.5")) == "1.50"
    assert money(Decimal("0.05")) == "0.05"
    assert money(Decimal("1234.00")) == "1234.00"


def test_price_finer_than_a_penny_is_rejected_not_rounded():
    """A limit price the caller did not choose is a silent execution bug."""
    with pytest.raises(StructureError, match="finer than the penny"):
        money(Decimal("1.005"))


def test_large_prices_never_reach_the_wire_in_scientific_notation():
    assert "E" not in money(Decimal("1E+3")).upper()


def test_quantity_must_be_a_positive_whole_number_of_contracts():
    assert whole(3) == "3"
    for bad in (Decimal("1.5"), 0, -1):
        with pytest.raises(StructureError):
            whole(bad)


# --- what Alpaca will refuse -------------------------------------------------

def test_rejects_more_than_four_legs():
    """The ceiling is the wall, not headroom: an iron condor is exactly four."""
    legs = tuple(_leg(s) for s in (LONG_CALL, SHORT_CALL, FAR_CALL, SHORT_PUT, LONG_PUT))
    with pytest.raises(StructureError, match=f"exceeds Alpaca's hard ceiling of {MAX_LEGS}"):
        Structure(name="five-leg", legs=legs)


def test_rejects_duplicate_leg_symbols():
    with pytest.raises(StructureError, match="unique symbol"):
        Structure(name="dupe", legs=(_leg(LONG_CALL), _leg(LONG_CALL)))


def test_rejects_a_leg_with_neither_side_nor_position_intent():
    with pytest.raises(StructureError, match="side or position_intent"):
        Leg(LONG_CALL, 1)


def test_rejects_an_empty_structure():
    with pytest.raises(StructureError, match="at least one leg"):
        Structure(name="empty", legs=())


def test_rejects_a_leg_without_a_symbol():
    with pytest.raises(StructureError, match="OCC symbol"):
        Leg("  ", 1, Side.BUY)


# --- wire form ---------------------------------------------------------------

def test_vertical_produces_a_two_leg_mleg_payload():
    wire = vertical("v", LONG_CALL, SHORT_CALL, qty=2, limit_price=Decimal("1.25")).to_wire()
    assert wire["qty"] == "2"
    assert wire["type"] == "limit"
    assert wire["limit_price"] == "1.25"
    assert [leg["symbol"] for leg in wire["legs"]] == [LONG_CALL, SHORT_CALL]
    assert [leg["side"] for leg in wire["legs"]] == ["buy", "sell"]
    assert all(leg["ratio_qty"] == "1" for leg in wire["legs"])


def test_order_class_is_left_to_the_server():
    """The MCP override sets order_class="mleg" itself whenever legs are supplied.
    Setting it here too is one more thing to keep in sync with a tool we do not own."""
    assert "order_class" not in vertical("v", LONG_CALL, SHORT_CALL).to_wire()


def test_iron_condor_is_exactly_four_legs_and_survives_construction():
    condor = iron_condor("ic", LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL)
    wire = condor.to_wire()
    assert len(wire["legs"]) == MAX_LEGS
    assert condor.is_multileg
    # Bought wings bound the sold body — the defined-risk reading, on the wire.
    assert [leg["side"] for leg in wire["legs"]] == ["buy", "sell", "sell", "buy"]


def test_single_leg_uses_symbol_not_legs():
    wire = Structure(name="single", legs=(_leg(LONG_CALL),)).to_wire()
    assert wire["symbol"] == LONG_CALL
    assert "legs" not in wire
    assert wire["type"] == "market"


def test_ratio_qty_is_proportional_not_absolute():
    """Fifty spreads is qty=50 with ratio_qty 1 per leg, not ratio_qty 50."""
    wire = vertical("v", LONG_CALL, SHORT_CALL, qty=50).to_wire()
    assert wire["qty"] == "50"
    assert all(leg["ratio_qty"] == "1" for leg in wire["legs"])


# --- exits: the roll rule ----------------------------------------------------
#
# Settled policy: a roll is one order or it is not a roll. Closing legs + opening
# legs must fit in four, which admits 2-leg structures and excludes condors.

NEXT_LONG_CALL = "SPY270115C00600000"
NEXT_SHORT_CALL = "SPY270115C00605000"


def test_two_leg_roll_fits_in_one_four_leg_order():
    old = vertical("Dec vertical", LONG_CALL, SHORT_CALL)
    new = vertical("Jan vertical", NEXT_LONG_CALL, NEXT_SHORT_CALL)
    assert can_roll(old, new)

    rolled = roll(old, new, limit_price=Decimal("0.40"))
    wire = rolled.to_wire()
    assert len(wire["legs"]) == MAX_LEGS
    # Closing legs first, inverted; then the replacement's opening legs untouched.
    assert [leg["symbol"] for leg in wire["legs"]] == [
        LONG_CALL, SHORT_CALL, NEXT_LONG_CALL, NEXT_SHORT_CALL
    ]
    assert [leg["side"] for leg in wire["legs"]] == ["sell", "buy", "buy", "sell"]
    assert [leg["position_intent"] for leg in wire["legs"]] == [
        "sell_to_close", "buy_to_close", "buy_to_open", "sell_to_open"
    ]


def test_condor_roll_is_refused_at_construction():
    """The headline case: 4 + 4 is 8 legs, so a condor has no roll primitive."""
    old = iron_condor("Dec condor", LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL)
    new = iron_condor("Jan condor", LONG_PUT, SHORT_PUT, SHORT_CALL, NEXT_LONG_CALL)
    assert not can_roll(old, new)
    with pytest.raises(StructureError, match="8 legs exceeds the 4-leg ceiling"):
        roll(old, new)


def test_condor_roll_rejection_names_the_alternative():
    """A rejection that does not say what to do instead just gets retried."""
    old = iron_condor("Dec condor", LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL)
    new = vertical("Jan vertical", NEXT_LONG_CALL, NEXT_SHORT_CALL)
    with pytest.raises(StructureError, match="Close the position instead"):
        roll(old, new)


def test_roll_refuses_a_qty_mismatch():
    """One order carries one qty; a silent resize would change the position."""
    old = vertical("old", LONG_CALL, SHORT_CALL, qty=2)
    new = vertical("new", NEXT_LONG_CALL, NEXT_SHORT_CALL, qty=3)
    with pytest.raises(StructureError, match="roll qty mismatch"):
        roll(old, new)


# --- exits: closing ----------------------------------------------------------

def test_closing_a_condor_is_four_legs_and_always_available():
    """A condor cannot roll but must always be able to exit."""
    condor = iron_condor("ic", LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL, qty=3)
    wire = close(condor).to_wire()
    assert len(wire["legs"]) == MAX_LEGS
    assert wire["qty"] == "3"
    # Every leg inverted: the bought wings are sold, the sold body is bought back.
    assert [leg["side"] for leg in wire["legs"]] == ["sell", "buy", "buy", "sell"]
    assert all(leg["position_intent"].endswith("_to_close") for leg in wire["legs"])


def test_close_preserves_symbols_and_ratios():
    condor = iron_condor("ic", LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL)
    assert [leg.symbol for leg in close(condor).legs] == [
        LONG_PUT, SHORT_PUT, SHORT_CALL, FAR_CALL
    ]
    assert all(leg.ratio_qty == 1 for leg in close(condor).legs)


def test_cannot_close_a_leg_that_is_already_closing():
    already = Structure(
        name="closing",
        legs=(Leg(LONG_CALL, 1, Side.SELL, PositionIntent.SELL_TO_CLOSE),),
    )
    with pytest.raises(StructureError, match="already a closing leg"):
        close(already)
