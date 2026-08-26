"""Merging the two endpoints a liquidity check needs."""

from __future__ import annotations

from halstreet.marketdata.chain import daily_volume, enrich

SYM = "SPY261016C00765000"
OTHER = "SPY261016C00770000"


def test_merges_open_interest_into_the_snapshot():
    chain = {SYM: {"latestQuote": {"bp": 1, "ap": 1.1}}}
    contracts = [{"symbol": SYM, "open_interest": "1234",
                  "open_interest_date": "2026-08-24", "tradable": True}]
    out = enrich(chain, contracts)
    assert out[SYM]["openInterest"] == 1234
    assert out[SYM]["openInterestDate"] == "2026-08-24"
    assert out[SYM]["latestQuote"] == {"bp": 1, "ap": 1.1}


def test_does_not_mutate_the_inputs():
    chain = {SYM: {"latestQuote": {}}}
    enrich(chain, [{"symbol": SYM, "open_interest": "5"}])
    assert "openInterest" not in chain[SYM]


def test_a_snapshot_with_no_contract_keeps_no_open_interest():
    """It must not become zero — the gate has to keep failing closed on it."""
    out = enrich({SYM: {"latestQuote": {}}}, [])
    assert "openInterest" not in out[SYM]


def test_a_contract_with_no_snapshot_is_ignored():
    out = enrich({SYM: {}}, [{"symbol": OTHER, "open_interest": "9"}])
    assert set(out) == {SYM}


def test_unparseable_open_interest_is_left_absent():
    out = enrich({SYM: {}}, [{"symbol": SYM, "open_interest": "n/a"}])
    assert "openInterest" not in out[SYM]


def test_daily_volume_reads_the_bar():
    assert daily_volume({"dailyBar": {"v": 3483}}) == 3483
    assert daily_volume({}) is None
    assert daily_volume({"dailyBar": {}}) is None
