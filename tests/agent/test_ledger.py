"""The ledger, and the netting problem it exists to solve.

The central case is `test_two_structures_sharing_a_short_strike_net`: it reproduces
exactly what the live paper run showed on 2026-08-26, where a vertical and a condor
both sold the Oct-16 770 call and the broker reported one position at qty -2.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from halstreet.agent.ledger import Ledger
from halstreet.execution.structures import iron_condor, vertical

C765 = "SPY261016C00765000"
C770 = "SPY261016C00770000"
C775 = "SPY261016C00775000"
P755 = "SPY261016P00755000"
P760 = "SPY261016P00760000"


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(path=tmp_path / "ledger.json")


@pytest.fixture
def loaded(ledger: Ledger) -> Ledger:
    """The exact book the live run produced: a vertical and a condor sharing C770."""
    ledger.record_open(
        vertical("Oct vertical", C765, C770), "SPY",
        structure_id="v1", entry_price=Decimal("2.99"),
    )
    ledger.record_open(
        iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
        structure_id="c1", entry_price=Decimal("-4.04"),
    )
    return ledger


# --- the netting problem ---------------------------------------------------------

def test_two_structures_sharing_a_short_strike_net(loaded):
    """C770 is sold by both, so the broker reports -2 and the ledger must agree."""
    assert loaded.expected_positions()[C770] == -2
    assert loaded.expected_positions()[C765] == 1
    assert loaded.expected_positions()[C775] == 1


def test_a_netted_contract_maps_back_to_both_parents(loaded):
    """The attribution the broker cannot give you — the reason this module exists."""
    holders = {s.structure_id for s in loaded.structures_holding(C770)}
    assert holders == {"v1", "c1"}


def test_reconciles_clean_against_the_brokers_netted_view(loaded):
    broker = [
        {"symbol": C765, "qty": "1"},
        {"symbol": C770, "qty": "-2"},
        {"symbol": C775, "qty": "1"},
        {"symbol": P755, "qty": "1"},
        {"symbol": P760, "qty": "-1"},
    ]
    assert loaded.reconcile(broker) == []


def test_reports_divergence_rather_than_repairing_it(loaded):
    """A partial fill leaves the ledger ahead of the account. The broker wins, and
    the disagreement is surfaced — not silently written away."""
    broker = [
        {"symbol": C765, "qty": "1"},
        {"symbol": C770, "qty": "-1"},   # one leg short of what we think we hold
        {"symbol": C775, "qty": "1"},
        {"symbol": P755, "qty": "1"},
        {"symbol": P760, "qty": "-1"},
    ]
    divergences = loaded.reconcile(broker)
    assert len(divergences) == 1
    assert divergences[0].symbol == C770
    assert "ledger says -2, broker says -1" in str(divergences[0])
    # And nothing was changed to hide it.
    assert loaded.expected_positions()[C770] == -2


def test_detects_a_position_the_agent_never_opened(loaded):
    broker = [
        {"symbol": C765, "qty": "1"}, {"symbol": C770, "qty": "-2"},
        {"symbol": C775, "qty": "1"}, {"symbol": P755, "qty": "1"},
        {"symbol": P760, "qty": "-1"},
        {"symbol": "QQQ261016C00500000", "qty": "3"},
    ]
    assert [d.symbol for d in loaded.reconcile(broker)] == ["QQQ261016C00500000"]


# --- closing ---------------------------------------------------------------------

def test_closing_removes_a_structure_from_the_expected_book(loaded):
    loaded.record_close("v1", exit_price=Decimal("-2.84"))
    expected = loaded.expected_positions()
    assert C765 not in expected          # only the vertical held it
    assert expected[C770] == -1          # the condor's short leg survives
    assert len(loaded.open_structures) == 1


def test_closing_an_unknown_structure_raises(loaded):
    with pytest.raises(KeyError):
        loaded.record_close("nope")


def test_realized_pnl_matches_the_live_round_trip(loaded):
    """Opened at 2.99 debit, closed at 2.84 credit: a $15 loss, as actually filled."""
    loaded.record_close("v1", exit_price=Decimal("-2.84"))
    v1 = next(s for s in loaded.structures if s.structure_id == "v1")
    assert v1.realized() == Decimal("-15.00")


def test_condor_credit_round_trip_pnl(loaded):
    """Opened for 4.04 credit, closed for 4.27 debit: a $23 loss."""
    loaded.record_close("c1", exit_price=Decimal("4.27"))
    c1 = next(s for s in loaded.structures if s.structure_id == "c1")
    assert c1.realized() == Decimal("-23.00")


def test_a_half_vanished_structure_is_not_marked_closed(loaded):
    """Some legs gone is a divergence for a human, not a tidy expiry.

    Here the vertical has lost C765 but still shows C770. Closing it would assert an
    exit that never happened and would discard the evidence that something is wrong.
    """
    partial = [{"symbol": C770, "qty": "-2"}, {"symbol": C775, "qty": "1"},
               {"symbol": P755, "qty": "1"}, {"symbol": P760, "qty": "-1"}]
    assert loaded.mark_closed_where_flat(partial) == []
    assert len(loaded.open_structures) == 2
    # ...and it surfaces as a divergence instead.
    assert [d.symbol for d in loaded.reconcile(partial)] == [C765]


def test_marks_closed_when_every_leg_is_gone(loaded):
    """The condor survives; the vertical's legs are both absent, so it closed."""
    # Drop the condor's shared C770 contribution out of the vertical by closing it
    # through the broker view: C765 gone entirely means the vertical is flat.
    loaded.record_close("c1", exit_price=Decimal("4.27"))
    assert [s.structure_id for s in loaded.mark_closed_where_flat([])] == ["v1"]


def test_expired_worthless_structure_is_marked_closed(ledger):
    ledger.record_open(vertical("v", C765, C770), "SPY", structure_id="v1")
    assert ledger.mark_closed_where_flat([]) != []
    assert ledger.open_structures == []


# --- persistence & views ----------------------------------------------------------

def test_survives_a_round_trip_to_disk(loaded):
    loaded.save()
    again = Ledger.load(loaded.path)
    assert again.expected_positions() == loaded.expected_positions()
    assert again.structures[0].entry_price == Decimal("2.99")


def test_loading_a_missing_file_gives_an_empty_ledger(tmp_path):
    assert Ledger.load(tmp_path / "nope.json").structures == []


def test_contracts_by_underlying_is_gross_for_the_concentration_gate(loaded):
    """Six legs across two structures, netted to five contracts of SPY exposure."""
    assert loaded.contracts_by_underlying() == {"SPY": 6}


def test_dte_is_taken_from_the_nearest_leg(loaded):
    from datetime import date
    v1 = next(s for s in loaded.structures if s.structure_id == "v1")
    assert v1.dte(date(2026, 10, 1)) == 15


def test_opening_a_structure_is_durable_immediately(tmp_path):
    # An order accepted by the broker with no ledger record is an untracked position:
    # reconciliation reports it as a divergence forever and nothing knows when to
    # close it. Durability must not depend on the caller remembering to save.
    from halstreet.agent.ledger import Ledger
    path = tmp_path / "ledger.json"
    led = Ledger.load(path)
    led.record_open(_spread(), "SPY", structure_id="abc123",
                    entry_price=Decimal("-1.00"), order_id="o-1")
    assert len(Ledger.load(path).open_structures) == 1


def test_closing_a_structure_is_durable_immediately(tmp_path):
    # Mirrored: a structure whose closing order was accepted must not come back as
    # open after a restart, or the next cycle tries to close it a second time.
    from halstreet.agent.ledger import Ledger
    path = tmp_path / "ledger.json"
    led = Ledger.load(path)
    led.record_open(_spread(), "SPY", structure_id="abc123",
                    entry_price=Decimal("-1.00"), order_id="o-1")
    led.record_close("abc123", exit_price=Decimal("0.50"))
    assert Ledger.load(path).open_structures == []


def _spread():
    from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
    return Structure(
        name="SPY 765/770 call spread",
        legs=(Leg("SPY261016C00765000", 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
              Leg("SPY261016C00770000", 1, Side.BUY, PositionIntent.BUY_TO_OPEN)),
        qty=1, limit_price=Decimal("-1.00"))


def test_a_fill_price_replaces_the_provisional_limit(tmp_path):
    # Entry price is written at submission, when the order is pending_new and the only
    # number available is the limit. Limits and fills differ, and always in the
    # direction that flatters the ledger — a limit is the worst price you were willing
    # to take. The first live round trip: limit -1.59, fill -1.60.
    from halstreet.agent.ledger import Ledger
    path = tmp_path / "ledger.json"
    led = Ledger.load(path)
    led.record_open(_spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.59"), order_id="o-1")
    assert led.record_fill("s1", Decimal("-1.60")) is True
    assert Ledger.load(path).structures[0].entry_price == Decimal("-1.60")


def test_an_unchanged_fill_is_not_reported_as_a_correction(tmp_path):
    # The caller journals on True, so a no-op must not manufacture a record.
    from halstreet.agent.ledger import Ledger
    led = Ledger.load(tmp_path / "ledger.json")
    led.record_open(_spread(), "QQQ", structure_id="s1",
                    entry_price=Decimal("-1.60"), order_id="o-1")
    assert led.record_fill("s1", Decimal("-1.60")) is False


def test_a_fill_for_an_unknown_structure_is_ignored(tmp_path):
    from halstreet.agent.ledger import Ledger
    led = Ledger.load(tmp_path / "ledger.json")
    assert led.record_fill("nope", Decimal("-1.60")) is False
