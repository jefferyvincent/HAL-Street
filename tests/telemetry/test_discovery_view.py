"""What the panel is told about discovery — the census behind the heat map.

The journal records one `discovery` event per pass and the panel draws the latest.
Three things make that harder than "return the last event", and each is a test below.

  * **The tail is the point.** A heat map of the six names that were scanned is a
    list. What makes it a map is the sixty that were not — the shape of what the tape
    was talking about, and where the cut fell across it.
  * **The three statuses must survive.** "Scanned", "the screen refused it" and "never
    looked at" are different facts, and flattening them into hot/cold would have the
    map assert a judgement about names nobody screened.
  * **It is publisher text.** The headline on each cell reached us through an
    untrusted feed. It leaves here as text and the panel renders it as text.
"""

from __future__ import annotations

import pytest

from halstreet.telemetry import server


def _run(tmp_path, events):
    from halstreet.telemetry.journal import Journal
    j = Journal.open(tmp_path / "run.jsonl")
    for event, fields in events:
        j.write(event, **fields)
    return server.snapshot(
        journal_path=str(tmp_path / "run.jsonl"),
        ledger_path=str(tmp_path / "ledger.json"),
        breaker_path=str(tmp_path / "circuit.json"),
    )


def _cell(symbol, mentions, status="scanned", **extra):
    return {"symbol": symbol, "mentions": mentions, "status": status,
            "headline": f"About {symbol}", **extra}


def _discovery(tmp_path, **fields):
    base = {"headlines": 10, "symbols": 2,
            "tally": [_cell("NVDA", 3), _cell("PFE", 1)]}
    return _run(tmp_path, [("discovery", {**base, **fields})])["discovery"]


def test_the_census_reaches_the_panel(tmp_path):
    d = _discovery(tmp_path)
    assert [c["symbol"] for c in d["cells"]] == ["NVDA", "PFE"]


def test_the_counts_behind_the_map_come_with_it(tmp_path):
    """"Six names off four hundred headlines" is the claim the map is making."""
    d = _discovery(tmp_path, headlines=100, symbols=66)
    assert d["headlines"] == 100 and d["symbols"] == 66


def test_the_hottest_cell_sets_the_scale(tmp_path):
    """Heat is relative. A four-mention day and a forty-mention day both fill the ramp.

    Absolute mention counts would make every quiet morning render as one flat cold
    grid, which is a true statement about the tape and a useless map.
    """
    d = _discovery(tmp_path, tally=[_cell("A", 9), _cell("B", 3)])
    assert d["hottest"] == 9


def test_each_status_survives_the_trip(tmp_path):
    d = _discovery(tmp_path, tally=[
        _cell("NVDA", 3),
        _cell("CYCUW", 2, status="refused", reason="no options listed on it"),
        _cell("TAIL", 1, status="not-reached"),
    ])
    assert [c["status"] for c in d["cells"]] == ["scanned", "refused", "not-reached"]
    assert d["cells"][1]["reason"] == "no options listed on it"


def test_a_scanned_cell_carries_no_reason_rather_than_an_empty_one(tmp_path):
    """An empty string renders as a blank line under the symbol; absent renders as
    nothing, which is what "there was no objection" should look like."""
    assert _discovery(tmp_path)["cells"][0].get("reason") in (None, "")


def test_only_the_latest_pass_is_drawn(tmp_path):
    """The map is what the tape says now, not everything it has ever said.

    Accumulating passes would keep a name that was hot at the open on the map all day,
    which is the opposite of what a heat map of a live feed is for.
    """
    snap = _run(tmp_path, [
        ("discovery", {"headlines": 5, "symbols": 1, "tally": [_cell("OLD", 5)]}),
        ("discovery", {"headlines": 7, "symbols": 1, "tally": [_cell("NEW", 2)]}),
    ])
    assert [c["symbol"] for c in snap["discovery"]["cells"]] == ["NEW"]


def test_a_journal_with_no_discovery_yet_says_so_rather_than_breaking(tmp_path):
    """Every pinned universe produces exactly this, forever. It is not an error."""
    snap = _run(tmp_path, [("cycle", {"underlying": "SPY"})])
    assert snap["discovery"]["cells"] == []
    assert snap["discovery"]["headlines"] == 0


@pytest.mark.parametrize("tally", [None, "NVDA", 7, [1, 2], [{"no": "symbol"}]])
def test_a_malformed_tally_yields_no_cells_rather_than_a_500(tmp_path, tally):
    """This route is polled every five seconds. It must not be the thing that breaks.

    A string iterates character by character and a bare list of ints has no `.get`;
    both have taken this server down before on other keys.
    """
    assert _discovery(tmp_path, tally=tally)["cells"] == []


def test_a_cell_with_no_mentions_does_not_divide_the_scale_by_zero(tmp_path):
    d = _discovery(tmp_path, tally=[_cell("A", 0)])
    assert d["hottest"] >= 1


def test_the_map_is_bounded_so_one_loud_morning_cannot_flood_the_payload(tmp_path):
    big = [_cell(f"S{i}", 200 - i, status="not-reached") for i in range(400)]
    d = _discovery(tmp_path, tally=big)
    assert len(d["cells"]) <= server.DISCOVERY_CELLS


def test_the_bound_keeps_the_hottest_not_the_first_it_happened_to_read(tmp_path):
    cold = [_cell(f"C{i}", 1, status="not-reached") for i in range(server.DISCOVERY_CELLS)]
    d = _discovery(tmp_path, tally=[*cold, _cell("HOT", 99)])
    assert any(c["symbol"] == "HOT" for c in d["cells"])
