"""The telemetry panel's API — and the fact that it cannot trade."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

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


def test_the_server_exposes_no_write_route():
    # A dashboard that can trade is a second path to the broker that does not go
    # through gates/, and the whole argument of this project is that there is exactly
    # one such path. Every HTTP route is a GET; nothing accepts a body.
    from fastapi.routing import APIRoute

    for route in server.app.routes:
        if isinstance(route, APIRoute):
            assert route.methods <= {"GET", "HEAD"}, f"{route.path} accepts {route.methods}"


def test_the_socket_is_send_only():
    """The one place a read-only surface could quietly grow a write path.

    A WebSocket is duplex, so `/ws` is the only route where a client frame could
    reach code at all. It cannot, because there is no code to reach: this module
    never receives. That is the whole guarantee, and it is one grep wide — which is
    exactly why it is worth pinning, since adding a receive is a one-line change that
    reads as harmless.
    """
    import ast

    # The AST, not a grep over the text: the module's own docstring names these
    # methods in order to say it never calls them, and a substring search cannot tell
    # the difference between a promise and a violation.
    tree = ast.parse(Path(server.__file__).read_text())
    reads = {"receive", "receive_text", "receive_bytes", "receive_json",
             "iter_text", "iter_bytes", "iter_json"}
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (called & reads), f"the socket must never read: {called & reads}"


def test_the_websocket_route_exists_and_is_the_only_one():
    from starlette.routing import WebSocketRoute

    sockets = [r for r in server.app.routes if isinstance(r, WebSocketRoute)]
    assert [r.path for r in sockets] == ["/ws"]


def test_it_never_sends_a_cors_header():
    # Allowing another origin would let any page in the browser read the account's
    # live position.
    source = Path(server.__file__).read_text()
    assert "Access-Control-Allow-Origin" not in source


def test_serve_binds_localhost_by_default():
    import inspect
    assert inspect.signature(server.serve).parameters["host"].default == "127.0.0.1"


def test_the_snapshot_survives_an_empty_run(tmp_path):
    state = _run(tmp_path, [])
    assert state["decisions"] == [] and state["positions"] == []
    assert state["circuit"]["halted"] is False


def test_gate_decisions_carry_every_verdict_not_just_rejections(tmp_path):
    state = _run(tmp_path, [
        ("gate_decision", {
            "structure": "SPY 765/770", "underlying": "SPY", "approved": False,
            "rejected_by": ["liquidity-floor"],
            "gates": [{"gate": "defined-risk-only", "passed": True, "reason": "ok"},
                      {"gate": "liquidity-floor", "passed": False, "reason": "thin"}],
        }),
    ])
    gates = state["decisions"][0]["gates"]
    assert len(gates) == 2
    assert [g["passed"] for g in gates] == [True, False]


def test_only_the_latest_menu_per_underlying_is_served(tmp_path):
    # The panel shows what is on the table now, not every menu ever built.
    state = _run(tmp_path, [
        ("candidates", {"underlying": "SPY", "count": 1, "candidates": [{"name": "old"}]}),
        ("candidates", {"underlying": "SPY", "count": 2, "candidates": [{"name": "new"}]}),
    ])
    assert len(state["menus"]) == 1
    assert state["menus"][0]["count"] == 2


def test_the_payload_carries_only_what_the_panel_renders(tmp_path):
    # It is polled every five seconds; unrendered history was a quarter of a megabyte
    # per request.
    state = _run(tmp_path, [("cycle_start", {"underlying": "SPY", "spot": "765",
                                             "dry_run": True}) for _ in range(50)])
    assert "events" not in state
    assert set(state) == {"circuit", "pnl", "positions", "closed", "decisions",
                          "views", "menus", "equity_curve",
                          "chain", "families", "limits"}


def test_no_floats_reach_the_wire(tmp_path):
    # Same rule as the journal: a price that has been through binary floating point
    # is not the price that was traded.
    state = _run(tmp_path, [("cycle_start", {"underlying": "SPY", "spot": Decimal("765.12"),
                                             "dry_run": True, "equity": Decimal(100000)})])
    def no_floats(node):
        assert not isinstance(node, float), f"float on the wire: {node}"
        if isinstance(node, dict):
            [no_floats(v) for v in node.values()]
        if isinstance(node, list):
            [no_floats(v) for v in node]
    no_floats(json.loads(json.dumps(state)))


def test_the_chain_is_served_with_a_family_on_every_gate():
    # The panel groups by the family the gate layer stamps, never by position. A
    # positional slice mislabels every gate after an insertion, confidently.
    state = server.snapshot(journal_path="/nonexistent", ledger_path="/nonexistent",
                            breaker_path="/nonexistent")
    from halstreet.gates import ALL_GATES
    assert len(state["chain"]) == len(ALL_GATES)
    assert all(g["family"] for g in state["chain"])
    assert {g["family"] for g in state["chain"]} <= set(state["families"])


def test_the_family_split_matches_the_gate_modules():
    # contract 3 / liquidity 2 / defined risk 4 / portfolio 3 / circuit 4 = 16.
    from collections import Counter

    from halstreet.gates import ALL_GATES
    from halstreet.gates.base import family_of
    counts = Counter(family_of(g) for g in ALL_GATES)
    assert counts == {"contract": 3, "liquidity": 2, "defined_risk": 4,
                      "portfolio": 3, "circuit": 4}


def test_limits_are_served_under_their_environment_variable_names():
    # The panel shows them read-only beside the name you would have to edit to change
    # one — raising a limit is a human act outside the app.
    state = server.snapshot(journal_path="/nonexistent", ledger_path="/nonexistent",
                            breaker_path="/nonexistent")
    assert "MAX_LOSS_PER_POSITION_USD" in state["limits"]
    assert all(k.isupper() for k in state["limits"])
