"""A structure the broker has not filled is not a position the account is carrying.

The ledger records on *acceptance*, deliberately: an accepted order is a position you
may hold, and a ledger that only learns about filled orders cannot explain a partial
fill it never knew to expect. That is right, and it means `open_structures` contains
things the account does not own yet.

The panel drew them all as OPEN. Reported live on 2026-08-31: the SPY 765/763 spread
rested unfilled at its limit for ten minutes while the console showed it as held, its
legs reading "not recorded", and a DIVERGENCE line every cycle saying the ledger and
the broker disagreed. Every one of those was correct on its own; together they said a
position existed.

`entry_filled` is on the ledger and was not on the wire.
"""

from __future__ import annotations

import json


def _snapshot(tmp_path, structures):
    (tmp_path / "ledger.json").write_text(json.dumps({"structures": structures}))
    from halstreet.telemetry import server
    return server.snapshot(journal_path=str(tmp_path / "run.jsonl"),
                           ledger_path=str(tmp_path / "ledger.json"),
                           breaker_path=str(tmp_path / "circuit.json"))


def _structure(**over):
    base = {
        "structure_id": "abc123", "name": "SPY 2026-10-16 765/763 put credit spread",
        "underlying": "SPY", "qty": 2, "legs": {"SPY261016P00765000": -2,
                                                "SPY261016P00763000": 2},
        "opened_at": "2026-08-31T14:15:57+00:00", "entry_price": "-1.02",
        "order_id": "e1711e67", "rationale": "", "entry_filled": True,
    }
    return {**base, **over}


def test_a_filled_structure_is_reported_as_held(tmp_path):
    state = _snapshot(tmp_path, [_structure()])
    assert state["positions"][0]["entry_filled"] is True


def test_an_unfilled_structure_says_so_rather_than_looking_held(tmp_path):
    """The whole point. A resting order and a carried position are different facts and
    the console had one word for both."""
    state = _snapshot(tmp_path, [_structure(entry_filled=False)])
    assert state["positions"][0]["entry_filled"] is False


def test_a_ledger_that_never_wrote_the_flag_does_not_claim_a_fill(tmp_path):
    """Older records predate it. Absent is not evidence of a fill, and defaulting to
    True would quietly re-assert the thing this exists to stop asserting."""
    s = _structure()
    del s["entry_filled"]
    state = _snapshot(tmp_path, [s])
    assert state["positions"][0]["entry_filled"] is False


def test_the_working_order_is_still_a_position_for_every_other_purpose(tmp_path):
    """It is not filtered out. The account may end up holding it, the exit policy has
    to see it, and hiding it would be the opposite mistake."""
    state = _snapshot(tmp_path, [_structure(entry_filled=False)])
    assert len(state["positions"]) == 1
    assert state["positions"][0]["structure_id"] == "abc123"


def test_the_flag_survives_the_json_the_panel_actually_receives(tmp_path):
    """`_plain` walks the payload; a bool that becomes a string is a bool the panel
    reads as truthy either way."""
    state = _snapshot(tmp_path, [_structure(entry_filled=False)])
    wire = json.loads(json.dumps(state))
    assert wire["positions"][0]["entry_filled"] is False
