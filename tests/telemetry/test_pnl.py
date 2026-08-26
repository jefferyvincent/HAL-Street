"""The numbers the write-up publishes. Anchored to the live round trip where possible."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from halstreet.agent.ledger import Ledger
from halstreet.execution.structures import iron_condor, vertical
from halstreet.telemetry import pnl
from halstreet.telemetry.journal import Journal

C765, C770 = "SPY261016C00765000", "SPY261016C00770000"
P755, P760, C775 = "SPY261016P00755000", "SPY261016P00760000", "SPY261016C00775000"


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    led = Ledger(path=tmp_path / "l.json")
    led.record_open(vertical("Oct vertical", C765, C770), "SPY",
                    structure_id="v1", entry_price=Decimal("2.99"),
                    rationale="Defined risk, 51 DTE.")
    led.record_open(iron_condor("Oct condor", P755, P760, C770, C775), "SPY",
                   structure_id="c1", entry_price=Decimal("-4.04"))
    return led


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    return Journal.open(tmp_path / "j.jsonl")


# --- realized P&L, from the ledger rather than the broker --------------------------

def test_realized_matches_the_live_round_trip(ledger, journal):
    """The real fills: vertical closed at 2.84 (-$15), condor at 4.27 (-$23)."""
    ledger.record_close("v1", exit_price=Decimal("-2.84"))
    ledger.record_close("c1", exit_price=Decimal("4.27"))
    report = pnl.build(ledger, journal)
    assert report.realized_usd == Decimal("-38.00")
    assert report.closed_count == 2
    assert report.losses == 2 and report.wins == 0


def test_a_scratch_counts_as_neither_a_win_nor_a_loss(ledger, journal):
    """Counting a flat trade as a win flatters the record."""
    ledger.record_close("v1", exit_price=Decimal("-2.99"))
    report = pnl.build(ledger, journal)
    assert report.positions[0].realized_usd == Decimal("0.00")
    assert report.wins == 0 and report.losses == 0
    assert report.win_rate is None


def test_win_rate_ignores_open_positions(ledger, journal):
    ledger.record_close("v1", exit_price=Decimal("-3.99"))   # +$100
    report = pnl.build(ledger, journal)
    assert report.wins == 1 and report.losses == 0
    assert report.win_rate == Decimal(100)
    assert report.open_count == 1


# --- unrealized ----------------------------------------------------------------------

def test_unrealized_uses_supplied_marks(ledger, journal):
    report = pnl.build(ledger, journal, marks={"v1": Decimal("3.99")})
    assert report.unrealized_usd == Decimal("100.00")
    assert report.total_usd == Decimal("100.00")


def test_an_unmarked_position_contributes_nothing_rather_than_zero(ledger, journal):
    """Omitting is honest; counting it as flat would be a claim we cannot support."""
    report = pnl.build(ledger, journal, marks={})
    assert report.unrealized_usd == Decimal(0)
    assert report.positions[0].unrealized_usd is None


# --- drawdown -------------------------------------------------------------------------

def test_drawdown_is_peak_to_trough():
    curve = [Decimal(x) for x in ("100000", "101000", "99000", "100500", "97000")]
    peak, fall, pct = pnl.drawdown(curve)
    assert peak == Decimal(101000)
    assert fall == Decimal(4000)            # 101000 -> 97000
    assert round(pct, 2) == Decimal("3.96")


def test_drawdown_of_a_rising_curve_is_zero():
    _, fall, _ = pnl.drawdown([Decimal(1), Decimal(2), Decimal(3)])
    assert fall == Decimal(0)


def test_drawdown_of_nothing_is_none():
    assert pnl.drawdown([]) is None


def test_equity_curve_comes_from_recorded_cycle_starts(ledger, journal):
    for equity in ("100000", "99000", "101000", "98000"):
        journal.cycle_start(underlying="SPY", spot="765", dry_run=True, equity=equity)
    report = pnl.build(ledger, journal)
    assert report.equity_samples == 4
    assert report.equity_start == Decimal(100000)
    assert report.equity_last == Decimal(98000)
    assert report.max_drawdown_usd == Decimal(3000)   # 101000 -> 98000


def test_drawdown_is_labelled_by_its_sampling(ledger, journal):
    """It is scan-resolution, not tick-resolution, and the output says so."""
    journal.cycle_start(underlying="SPY", spot="765", dry_run=True, equity="100000")
    text = pnl.render(pnl.build(ledger, journal))
    assert "scan samples" in text


# --- gate counts, which are the write-up's headline ------------------------------------

def test_rejection_counts_come_through(ledger, journal):
    from halstreet.execution.structures import vertical as v
    from halstreet.gates.base import Decision, GateResult, Proposal
    proposal = Proposal(v("x", C765, C770, limit_price=Decimal("1.00")), "SPY")
    journal.decision(Decision(proposal, [
        GateResult("liquidity-floor", False, "thin"),
        GateResult("dte-floor", True, ""),
    ]))
    journal.decision(Decision(proposal, [GateResult("liquidity-floor", False, "thin")]))
    report = pnl.build(ledger, journal)
    assert report.rejections_by_gate == {"liquidity-floor": 2}
    assert report.rejected == 2
    assert "liquidity-floor" in pnl.render(report)


# --- exports ----------------------------------------------------------------------------

def test_csv_has_one_row_per_structure(ledger, journal):
    rows = pnl.to_csv(pnl.build(ledger, journal)).strip().splitlines()
    assert len(rows) == 3          # header + 2
    assert "Oct vertical" in rows[1]


def test_csv_rationale_survives_a_newline(ledger, journal):
    ledger.structures[0].rationale = "line one\nline two"
    body = pnl.to_csv(pnl.build(ledger, journal))
    assert "line one line two" in body


def test_export_writes_all_three_files(ledger, journal, tmp_path):
    paths = pnl.write_exports(pnl.build(ledger, journal), tmp_path / "out")
    assert set(paths) == {"json", "csv", "txt"}
    assert all(p.exists() for p in paths.values())
    data = json.loads(paths["json"].read_text())
    assert data["realized_usd"] == "0"
    assert len(data["positions"]) == 2


def test_json_export_carries_no_floats(ledger, journal, tmp_path):
    """A price that round-trips through binary floating point is not the price traded."""
    ledger.record_close("v1", exit_price=Decimal("-2.84"))
    paths = pnl.write_exports(pnl.build(ledger, journal), tmp_path / "out")

    def no_floats(node):
        if isinstance(node, float):
            raise TypeError(f"float in export: {node}")
        if isinstance(node, dict):
            [no_floats(v) for v in node.values()]
        if isinstance(node, list):
            [no_floats(v) for v in node]

    no_floats(json.loads(paths["json"].read_text()))
