"""Per-leg fill prices, and the identity that lets them sit beside the net.

The panel now shows a P&L per leg next to the position's own. Those are two numbers
derived from the same trade, and the only thing that makes it safe to print both is
that they agree: the leg fills sum to the net fill, the leg mids sum to the net mark,
so the per-leg P&L sums to the structure P&L exactly. The moment that stops holding,
one of the two is wrong and the screen gives no way to tell which.

The fixture is the real thing — the entry of the position open while this was written,
copied from Alpaca's own order record.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.agent.manager import mark_legs, mark_structure
from halstreet.execution.fills import leg_fills

SHORT = "QQQ261016C00765000"
LONG = "QQQ261016C00775000"

#: Alpaca's answer to the `mleg` order that opened the live QQQ call credit spread.
#: Trimmed to the fields anything reads; the shape is otherwise verbatim.
REAL_ORDER = {
    "id": "1a056844-cb6b-4331-b630-cd786e08f886",
    "status": "filled",
    "order_class": "mleg",
    "filled_avg_price": "-1.51",
    "legs": [
        {"symbol": SHORT, "side": "sell", "status": "filled",
         "filled_qty": "1", "filled_avg_price": "4.51"},
        {"symbol": LONG, "side": "buy", "status": "filled",
         "filled_qty": "1", "filled_avg_price": "3"},
    ],
}


def structure(**over) -> OpenStructure:
    base = {
        "structure_id": "ca119ed388d3",
        "name": "QQQ 2026-10-16 765/775 call credit spread",
        "underlying": "QQQ", "qty": 1,
        "legs": {SHORT: -1, LONG: 1},
        "opened_at": "2026-08-27T16:40:25+00:00",
        "entry_price": Decimal("-1.51"), "entry_filled": True,
        "order_id": "1a056844-cb6b-4331-b630-cd786e08f886",
    }
    return OpenStructure(**{**base, **over})


def chain(short_bid="4.55", short_ask="4.65", long_bid="2.94", long_ask="3.04"):
    return {
        SHORT: {"latestQuote": {"bp": short_bid, "ap": short_ask}},
        LONG: {"latestQuote": {"bp": long_bid, "ap": long_ask}},
    }


# --- reading the order --------------------------------------------------------


def test_the_real_order_yields_both_leg_prices():
    assert leg_fills(REAL_ORDER) == {SHORT: Decimal("4.51"), LONG: Decimal(3)}


def test_the_leg_prices_reconstruct_the_net_the_broker_reported():
    """3.00 - 4.51 = -1.51. This is why the legs can be trusted beside the net.

    If Alpaca ever reported legs that did not sum to its own `filled_avg_price`, every
    per-leg figure downstream would be quietly describing a different trade.
    """
    fills = leg_fills(REAL_ORDER)
    legs = structure().legs
    net = sum(fills[symbol] * signed for symbol, signed in legs.items())
    assert net == Decimal(REAL_ORDER["filled_avg_price"])


@pytest.mark.parametrize("order", [
    None, {}, [], "filled", 7,
    {"legs": None},
    {"legs": []},
    {"legs": "QQQ"},
    {"legs": [{"symbol": SHORT}]},                                  # no price yet
    {"legs": [{"symbol": SHORT, "filled_avg_price": None}]},
    {"legs": [{"symbol": SHORT, "filled_avg_price": ""}]},
    {"legs": [{"symbol": "", "filled_avg_price": "1"}]},
    {"legs": [{"symbol": None, "filled_avg_price": "1"}]},
    {"legs": [{"filled_avg_price": "1"}]},
    {"legs": [{"symbol": SHORT, "filled_avg_price": "N/A"}]},
    {"legs": ["QQQ261016C00765000"]},
])
def test_anything_unreadable_yields_nothing_rather_than_something_partial(order):
    assert leg_fills(order) == {}


def test_one_unpriced_leg_discards_the_priced_one_too():
    """All or nothing. A leg table with one price missing is worse than one with none.

    It also keeps the sum identity intact: a partial map would produce leg P&Ls that
    silently fail to add up to the position's.
    """
    half = {"legs": [
        {"symbol": SHORT, "filled_avg_price": "4.51"},
        {"symbol": LONG, "filled_avg_price": None},
    ]}
    assert leg_fills(half) == {}


def test_the_same_contract_twice_is_refused():
    """A ratio the ledger cannot express: it keys legs by symbol, so one price wins."""
    doubled = {"legs": [
        {"symbol": SHORT, "filled_avg_price": "4.51"},
        {"symbol": SHORT, "filled_avg_price": "4.60"},
    ]}
    assert leg_fills(doubled) == {}


def test_a_pending_order_gives_nothing_and_a_filled_one_gives_everything():
    pending = {"legs": [dict(leg, filled_avg_price=None, status="pending_new")
                        for leg in REAL_ORDER["legs"]]}
    assert leg_fills(pending) == {}
    assert leg_fills(REAL_ORDER) != {}


# --- the identity -------------------------------------------------------------


def test_leg_pnl_sums_to_the_structure_pnl_exactly():
    """The property the whole feature rests on. Not "close to" — equal."""
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    quotes = chain()
    net = mark_structure(s, quotes)
    whole = (net.value - s.entry_price) * 100 * s.qty
    parts = sum(leg.pnl(s.qty) for leg in mark_legs(s, quotes))
    assert parts == whole


@pytest.mark.parametrize("qty", [1, 2, 7])
def test_the_identity_holds_at_any_size(qty):
    s = structure(qty=qty, entry_legs=leg_fills(REAL_ORDER))
    quotes = chain()
    whole = (mark_structure(s, quotes).value - s.entry_price) * 100 * qty
    assert sum(leg.pnl(qty) for leg in mark_legs(s, quotes)) == whole


def test_the_identity_holds_when_the_position_is_winning_too():
    """A credit spread wins as its mark falls toward zero, and both legs move."""
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    quotes = chain(short_bid="2.00", short_ask="2.10", long_bid="1.40", long_ask="1.50")
    whole = (mark_structure(s, quotes).value - s.entry_price) * 100
    parts = [leg.pnl(1) for leg in mark_legs(s, quotes)]
    assert sum(parts) == whole
    assert whole > 0, "bought back cheaper than it was sold — this is the winning case"


def test_the_short_leg_makes_money_when_its_price_falls():
    """Sold at 4.51, marked at 2.05. `signed` is negative, and that is the whole trick."""
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    legs = {leg.symbol: leg for leg in mark_legs(s, chain(short_bid="2.00", short_ask="2.10"))}
    assert legs[SHORT].pnl(1) == Decimal(246)   # (2.05 - 4.51) * -1 * 100


def test_the_long_leg_loses_money_when_its_price_falls():
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    legs = {leg.symbol: leg for leg in mark_legs(s, chain(long_bid="1.40", long_ask="1.50"))}
    assert legs[LONG].pnl(1) == Decimal(-155)   # (1.45 - 3.00) * 1 * 100


def test_the_signs_match_what_alpaca_reported_for_this_position():
    """Measured against the broker's own per-contract P&L, 2026-08-27.

    Alpaca said -9 on the short and -1 on the long, at 4.60 and 2.99. Reproduced from
    the same mids to prove the sign convention here is the broker's and not a guess.
    """
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    quotes = chain(short_bid="4.60", short_ask="4.60", long_bid="2.99", long_ask="2.99")
    legs = {leg.symbol: leg for leg in mark_legs(s, quotes)}
    assert legs[SHORT].pnl(1) == Decimal(-9)
    assert legs[LONG].pnl(1) == Decimal(-1)


# --- refusing rather than guessing --------------------------------------------


def test_a_leg_with_no_fill_recorded_has_no_pnl_rather_than_a_guessed_one():
    """The state every position opened before this existed is in.

    The tempting wrong answer is to split the net across the legs, or to take the
    broker's `avg_entry_price` — which is netted across every structure holding that
    contract and answers a different question.
    """
    legs = mark_legs(structure(entry_legs=None), chain())
    assert all(leg.basis is None for leg in legs)
    assert all(leg.pnl(1) is None for leg in legs)
    assert all(leg.priced for leg in legs), "still priced — only the basis is missing"


def test_a_leg_with_no_quote_has_no_pnl_and_no_value():
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    quotes = chain()
    del quotes[LONG]
    legs = {leg.symbol: leg for leg in mark_legs(s, quotes)}
    assert legs[LONG].mid is None
    assert legs[LONG].pnl(1) is None
    assert legs[LONG].value(1) is None
    assert legs[SHORT].pnl(1) is not None, "the other leg is still readable"


def test_the_legs_a_net_refuses_are_exactly_the_legs_shown_unpriced():
    """One definition of "usable quote", not two.

    `mark_structure` is the sum of `mark_legs`, so the panel cannot show four prices
    under a mark that says it only has three.
    """
    s = structure(entry_legs=leg_fills(REAL_ORDER))
    quotes = chain(long_ask="0")          # zero ask is not a price
    net = mark_structure(s, quotes)
    unpriced = [leg.symbol for leg in mark_legs(s, quotes) if not leg.priced]
    assert net.missing == unpriced == [LONG]
    assert not net.complete


def test_a_one_sided_quote_is_not_a_price():
    s = structure()
    legs = {leg.symbol: leg for leg in mark_legs(s, {SHORT: {"latestQuote": {"bp": "4.55"}}})}
    assert legs[SHORT].mid is None


# --- the ledger's three states ------------------------------------------------


def test_never_asked_and_asked_with_nothing_back_are_different_states(tmp_path):
    """`None` is not `{}`, and the round trip through disk must keep them apart.

    Collapsing them means either never backfilling a structure recorded before this
    field existed, or asking the broker about a legless order once per cycle forever.
    """
    led = Ledger(path=tmp_path / "ledger.json", structures=[
        structure(structure_id="never", entry_legs=None),
        structure(structure_id="empty", entry_legs={}),
        structure(structure_id="known", entry_legs={SHORT: Decimal("4.51")}),
    ])
    led.save()
    back = {s.structure_id: s for s in Ledger.load(led.path).structures}
    assert back["never"].entry_legs is None
    assert back["empty"].entry_legs == {}
    assert back["known"].entry_legs == {SHORT: Decimal("4.51")}


def test_a_ledger_written_before_the_field_existed_reads_as_never_asked(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"structures": [{
        "structure_id": "old", "name": "n", "underlying": "QQQ", "qty": 1,
        "legs": {SHORT: -1}, "opened_at": "2026-08-26T00:00:00+00:00",
        "entry_price": "-1.6", "entry_filled": True, "order_id": "o1",
    }]}))
    (old,) = Ledger.load(path).structures
    assert old.entry_legs is None
    assert old.entry_filled, "its net fill was confirmed; only the legs were never kept"
    assert old in Ledger.load(path).awaiting_leg_prices()


def test_only_never_asked_structures_are_offered_for_backfill(tmp_path):
    led = Ledger(path=tmp_path / "ledger.json", structures=[
        structure(structure_id="never", entry_legs=None),
        structure(structure_id="empty", entry_legs={}),
        structure(structure_id="known", entry_legs={SHORT: Decimal("4.51")}),
    ])
    assert [s.structure_id for s in led.awaiting_leg_prices()] == ["never"]


def test_a_structure_with_no_order_id_is_not_offered(tmp_path):
    """There is no handle to ask about. Offering it would be one failed call a cycle."""
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs=None, order_id=None)])
    assert led.awaiting_leg_prices() == []


def test_a_closed_structure_is_asked_about_its_exit_not_its_entry(tmp_path):
    led = Ledger(path=tmp_path / "ledger.json", structures=[structure(
        entry_legs={SHORT: Decimal("4.51")}, exit_legs=None,
        closed_at="2026-08-27T19:00:00+00:00", exit_order_id="x1")])
    assert led.awaiting_leg_prices() == led.structures


def test_recording_an_empty_map_stops_the_asking(tmp_path):
    """The termination guarantee. A single-leg order costs one lookup, not one a cycle."""
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs=None)])
    assert led.record_leg_fills("ca119ed388d3", {}, entry=True) is False
    assert led.structures[0].entry_legs == {}
    assert led.awaiting_leg_prices() == []


def test_recording_real_prices_reports_that_something_was_learned(tmp_path):
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs=None)])
    assert led.record_leg_fills("ca119ed388d3", leg_fills(REAL_ORDER), entry=True) is True
    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51"), LONG: Decimal(3)}
    assert Ledger.load(led.path).structures[0].entry_legs[SHORT] == Decimal("4.51")


def test_recording_the_exit_side_leaves_the_entry_alone(tmp_path):
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs={SHORT: Decimal("4.51")})])
    led.record_leg_fills("ca119ed388d3", {SHORT: Decimal("2.05")}, entry=False)
    assert led.structures[0].entry_legs == {SHORT: Decimal("4.51")}
    assert led.structures[0].exit_legs == {SHORT: Decimal("2.05")}


def test_recording_against_an_unknown_id_changes_nothing(tmp_path):
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs=None)])
    assert led.record_leg_fills("nobody", {SHORT: Decimal(1)}, entry=True) is False
    assert led.structures[0].entry_legs is None


def test_prices_survive_disk_without_becoming_floats(tmp_path):
    """`0.1 + 0.2` is why. A cent lost in serialization breaks the sum identity."""
    led = Ledger(path=tmp_path / "ledger.json",
                 structures=[structure(entry_legs={SHORT: Decimal("4.515"),
                                                   LONG: Decimal("3.005")})])
    led.save()
    back = Ledger.load(led.path).structures[0].entry_legs
    assert back == {SHORT: Decimal("4.515"), LONG: Decimal("3.005")}
    assert all(isinstance(v, Decimal) for v in back.values())
