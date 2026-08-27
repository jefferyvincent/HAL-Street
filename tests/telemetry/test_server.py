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
                          "views", "menus", "equity_curve", "market",
                          "activity", "committees",
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


def test_the_bell_is_absent_rather_than_guessed_when_nothing_wrote_one(tmp_path):
    # A `--once` run never observes the closed half of a session, and the panel must
    # not infer one from a local clock that knows no holidays or early closes.
    assert _run(tmp_path, [])["market"] is None


def test_the_latest_session_transition_is_the_one_served(tmp_path):
    state = _run(tmp_path, [
        ("session", {"state": "closed", "session_date": "2026-08-26", "observed": True}),
        ("session", {"state": "open", "session_date": "2026-08-27", "observed": False}),
    ])
    assert state["market"]["state"] == "open"
    assert state["market"]["session_date"] == "2026-08-27"
    assert state["market"]["observed"] is False


def test_a_bell_that_rang_is_distinguishable_from_the_state_we_arrived_in(tmp_path):
    # `observed` is what lets a consumer sound the bell for one and merely label the
    # other. Without it, starting the panel during a session would replay the open.
    state = _run(tmp_path, [
        ("session", {"state": "open", "session_date": "2026-08-27", "observed": True}),
    ])
    assert state["market"]["observed"] is True


# --- what the panel shows when nothing has been gated --------------------------

def test_the_activity_pulse_shows_work_that_is_not_a_decision(tmp_path):
    """The panel was built around gate decisions, and most cycles produce none.

    An agent that declines every cycle writes no `gate_decision` at all, so every
    view was empty and the whole thing read as broken while the agent was scanning,
    reading headlines, deliberating and declining. None of that was visible.
    """
    state = _run(tmp_path, [
        ("cycle_start", {"underlying": "SPY", "spot": "768", "dry_run": False}),
        ("candidates", {"underlying": "SPY", "count": 6, "candidates": []}),
        ("committee", {"underlying": "SPY", "headlines": 12,
                       "catalyst": {"lean": "bearish", "confidence": 0.4, "note": "n"},
                       "bull": "b", "bear": "r", "errors": [], "reflection": [],
                       "tokens": {"in": 1, "out": 2, "cache_read": 0}}),
        ("proposal", {"underlying": "SPY", "ok": False, "passed": True,
                      "rationale": "Nothing clears friction."}),
    ])
    details = [a["detail"] for a in state["activity"]]
    assert any("scanning at 768" in d for d in details)
    assert any("6 structure(s) built" in d for d in details)
    assert any("committee read bearish on 12 headline(s)" in d for d in details)
    # The rationale, because on a passing cycle it is the only thing that survives.
    assert any("Nothing clears friction." in d for d in details)


def test_a_cycle_that_built_nothing_says_so_rather_than_showing_a_zero(tmp_path):
    state = _run(tmp_path, [("candidates", {"underlying": "SPY", "count": 0,
                                            "candidates": []})])
    assert state["activity"][0]["detail"] == "nothing worth building"


def test_a_missing_committee_stage_reaches_the_pulse(tmp_path):
    # A researcher that did not answer means the judge decided having heard one
    # side. That is a fact about the decision, not a glitch to hide.
    state = _run(tmp_path, [("committee", {
        "underlying": "SPY", "headlines": 3, "catalyst": {"lean": "neutral"},
        "bull": "", "bear": "r", "errors": ["bull: truncated at max_tokens=4000"],
        "reflection": [], "tokens": {}})])
    assert "1 stage(s) unavailable" in state["activity"][0]["detail"]


def test_the_pulse_is_bounded(tmp_path):
    state = _run(tmp_path, [("cycle_start", {"underlying": "SPY", "spot": "1",
                                             "dry_run": True}) for _ in range(200)])
    assert len(state["activity"]) == server.RECENT_ACTIVITY


def test_a_committee_session_is_paired_with_what_it_decided(tmp_path):
    """The tree has to end somewhere.

    The loop writes `committee` then `proposal` back to back; joining them here
    saves the panel from re-deriving an ordering it cannot see, and means a session
    that produced nothing shows *why* rather than trailing off.
    """
    state = _run(tmp_path, [
        ("committee", {"underlying": "QQQ", "headlines": 12,
                       "catalyst": {"lean": "neutral", "confidence": 0.6, "note": "n"},
                       "bull": "b", "bear": "r", "errors": [], "reflection": [],
                       "tokens": {"in": 1, "out": 14698, "cache_read": 0}}),
        ("proposal", {"underlying": "QQQ", "ok": False, "passed": False,
                      "error": "truncated at max_tokens=12000"}),
    ])
    session = state["committees"][0]
    assert session["underlying"] == "QQQ" and session["headlines"] == 12
    assert session["outcome"]["error"] == "truncated at max_tokens=12000"
    assert session["outcome"]["approved"] is None, "nothing was gated, so nothing to say"


def test_a_committee_whose_proposal_was_gated_carries_the_verdict(tmp_path):
    state = _run(tmp_path, [
        ("committee", {"underlying": "IWM", "headlines": 2,
                       "catalyst": {"lean": "bearish"}, "bull": "b", "bear": "r",
                       "errors": [], "reflection": [], "tokens": {}}),
        ("proposal", {"underlying": "IWM", "ok": True, "passed": False,
                      "structure": {"name": "IWM 316/320 call credit spread"}}),
        ("gate_decision", {"underlying": "IWM", "structure": "IWM 316/320",
                           "approved": False, "rejected_by": ["underlying-concentration"],
                           "gates": []}),
    ])
    outcome = state["committees"][0]["outcome"]
    assert outcome["approved"] is False
    assert outcome["rejected_by"] == ["underlying-concentration"]


def test_another_underlyings_proposal_is_never_borrowed(tmp_path):
    # Cycles run back to back per underlying. Pairing on position alone would hang
    # QQQ's outcome off SPY's committee.
    state = _run(tmp_path, [
        ("committee", {"underlying": "SPY", "headlines": 1, "catalyst": {},
                       "bull": "", "bear": "", "errors": [], "reflection": [],
                       "tokens": {}}),
        ("cycle_start", {"underlying": "QQQ", "spot": "1", "dry_run": True}),
        ("proposal", {"underlying": "QQQ", "ok": True, "passed": False,
                      "structure": {"name": "QQQ spread"}}),
    ])
    assert state["committees"][0]["outcome"]["structure"] == "", "SPY proposed nothing"


def test_the_committee_list_is_bounded_and_newest_first(tmp_path):
    state = _run(tmp_path, [
        ("committee", {"underlying": f"S{i}", "headlines": i, "catalyst": {},
                       "bull": "", "bear": "", "errors": [], "reflection": [],
                       "tokens": {}})
        for i in range(30)
    ])
    assert len(state["committees"]) == server.RECENT_COMMITTEES
    assert state["committees"][0]["headlines"] == 29, "newest first"


# --- the numbers on the screen must not contradict each other ---------------------

def test_the_headline_unrealized_matches_the_number_beside_the_position(tmp_path):
    """One source, or two numbers argue on the same screen.

    `build` was called with no marks at all, so it reported unrealized as zero
    while the holdings strip beside it — reading the same journal — showed
    -$12.50. Either being absent would have been better than both being present
    and different.

    This process still never asks the broker. The agent prices the whole book each
    cycle and writes it down; the snapshot is polled every five seconds and reads.
    """
    from decimal import Decimal

    from halstreet.agent.ledger import Ledger, OpenStructure

    ledger = Ledger.load(tmp_path / "ledger.json")
    ledger.structures.append(OpenStructure(
        structure_id="s1", name="QQQ 2026-10-16 765/775 call credit spread",
        underlying="QQQ", qty=1, legs={"QQQ261016C00765000": -1, "QQQ261016C00775000": 1},
        opened_at="2026-08-27T16:40:00", entry_price=Decimal("-1.51"),
        entry_filled=True))
    ledger.save()

    from halstreet.telemetry.journal import Journal
    j = Journal.open(tmp_path / "run.jsonl")
    j.write("exit_decision", structure_id="s1", structure="QQQ spread", action="hold",
            reason="50 DTE", unrealized_usd=Decimal("-12.50"),
            mark=Decimal("-1.635"), dte=50)

    state = server.snapshot(journal_path=str(tmp_path / "run.jsonl"),
                            ledger_path=str(tmp_path / "ledger.json"),
                            breaker_path=str(tmp_path / "circuit.json"))
    beside = state["positions"][0]["read"]["unrealized_usd"]
    assert Decimal(state["pnl"]["unrealized"]) == Decimal(beside)
    assert Decimal(state["pnl"]["unrealized"]) != 0


def test_a_percentage_reaches_the_screen_rounded(tmp_path):
    # A Decimal ratio carries twenty-eight significant figures. Exact everywhere it
    # is computed, rounded once at the edge — 0.017869674294289820732% is not a
    # number anyone reads.
    from decimal import Decimal

    state = _run(tmp_path, [
        ("cycle_start", {"underlying": "SPY", "spot": "1", "dry_run": True,
                         "equity": Decimal(100000)}),
        ("cycle_start", {"underlying": "SPY", "spot": "1", "dry_run": True,
                         "equity": Decimal("99982.13")}),
    ])
    shown = str(state["pnl"]["max_drawdown_pct"])
    assert len(shown.rsplit(".", maxsplit=1)[-1]) <= 2, shown


def test_a_position_the_agent_has_not_priced_yet_reports_nothing(tmp_path):
    # Not zero. An unpriced position and a flat one are different facts, and the
    # panel says "not yet priced" for one of them.
    from decimal import Decimal

    from halstreet.agent.ledger import Ledger, OpenStructure

    ledger = Ledger.load(tmp_path / "ledger.json")
    ledger.structures.append(OpenStructure(
        structure_id="s1", name="QQQ spread", underlying="QQQ", qty=1,
        legs={"QQQ261016C00765000": -1}, opened_at="2026-08-27T16:40:00",
        entry_price=Decimal("-1.51")))
    ledger.save()

    state = server.snapshot(journal_path=str(tmp_path / "empty.jsonl"),
                            ledger_path=str(tmp_path / "ledger.json"),
                            breaker_path=str(tmp_path / "circuit.json"))
    assert state["positions"][0]["read"] is None


def test_an_approved_decision_carries_the_position_it_became(tmp_path):
    """A verdict and its trade were connected by nothing but a name.

    So the panel could show that something was approved and offer no way through to
    the position — and a name is not an identifier: two spreads a week apart can
    share one. The id was generated at submission and never written down.
    """
    state = _run(tmp_path, [
        ("gate_decision", {"underlying": "QQQ", "structure": "QQQ 765/775 call spread",
                           "approved": True, "rejected_by": [], "gates": []}),
        ("order", {"structure": "QQQ 765/775 call spread", "submitted": True,
                   "intent": "open", "structure_id": "ca119ed388d3",
                   "order_id": "1a05"}),
    ])
    assert state["decisions"][0]["structure_id"] == "ca119ed388d3"


def test_a_rejected_decision_links_to_nothing(tmp_path):
    # There is no position, so offering a way to one would be a dead link at best
    # and someone else's trade at worst.
    state = _run(tmp_path, [
        ("gate_decision", {"underlying": "IWM", "structure": "IWM 316/320",
                           "approved": False, "rejected_by": ["underlying-concentration"],
                           "gates": []}),
        ("order", {"structure": "SPY something else", "submitted": True,
                   "intent": "open", "structure_id": "other"}),
    ])
    assert state["decisions"][0]["structure_id"] is None


def test_a_closing_order_is_never_mistaken_for_the_position_being_opened(tmp_path):
    state = _run(tmp_path, [
        ("gate_decision", {"underlying": "QQQ", "structure": "QQQ spread",
                           "approved": True, "rejected_by": [], "gates": []}),
        ("order", {"structure": "close QQQ spread", "submitted": True,
                   "intent": "close", "structure_id": "older"}),
    ])
    assert state["decisions"][0]["structure_id"] is None


def test_a_dry_run_approval_links_to_nothing(tmp_path):
    # Approved and deliberately not sent. There is no trade to open.
    state = _run(tmp_path, [
        ("gate_decision", {"underlying": "QQQ", "structure": "QQQ spread",
                           "approved": True, "rejected_by": [], "gates": []}),
        ("order", {"structure": "QQQ spread", "submitted": False, "intent": "open",
                   "error": "dry run"}),
    ])
    assert state["decisions"][0]["structure_id"] is None


# --- live marks ------------------------------------------------------------------

def test_the_marks_route_is_a_get_like_everything_else():
    from fastapi.routing import APIRoute
    route = next(r for r in server.app.routes
                 if isinstance(r, APIRoute) and r.path == "/api/marks")
    assert route.methods <= {"GET", "HEAD"}


def test_marks_are_empty_and_quiet_when_nothing_is_open(tmp_path):
    # And crucially it does not launch anything: there is nothing to price, so the
    # broker is never asked.
    import asyncio

    server.PATHS.ledger = str(tmp_path / "ledger.json")
    body = asyncio.run(server.api_marks())
    assert json.loads(body.body) == {"marks": {}, "as_of": json.loads(body.body)["as_of"]}


def test_a_broker_failure_leaves_the_panel_its_last_known_number(tmp_path, monkeypatch):
    """Not an error state.

    The caller falls back to the agent's own mark, which the journal already carries
    and which the panel labels with its age. A stale number that says it is stale
    beats a blank space that looks like a bug.
    """
    import asyncio
    from decimal import Decimal

    from halstreet.agent.ledger import Ledger, OpenStructure

    ledger = Ledger.load(tmp_path / "ledger.json")
    ledger.structures.append(OpenStructure(
        structure_id="s1", name="QQQ spread", underlying="QQQ", qty=1,
        legs={"QQQ261016C00765000": -1}, opened_at="2026-08-27T16:40:00",
        entry_price=Decimal("-1.51")))
    ledger.save()
    server.PATHS.ledger = str(tmp_path / "ledger.json")

    import halstreet.execution.mcp_client as mcp

    def boom(_env="dev"):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(mcp.AlpacaMCP, "from_env", staticmethod(boom))
    body = json.loads(asyncio.run(server.api_marks()).body)
    assert body["marks"] == {}
    assert "broker unreachable" in body["error"]


def test_a_structure_that_cannot_be_fully_priced_reports_the_missing_legs(monkeypatch,
                                                                         tmp_path):
    # The same refusal `evaluate_exit` makes. A mark from three of four legs is not
    # a mark, and showing one would put a number on screen the exit policy would not
    # act on.
    import asyncio
    from decimal import Decimal

    from halstreet.agent.ledger import Ledger, OpenStructure

    ledger = Ledger.load(tmp_path / "ledger.json")
    ledger.structures.append(OpenStructure(
        structure_id="s1", name="QQQ spread", underlying="QQQ", qty=1,
        legs={"QQQ261016C00765000": -1, "QQQ261016C00775000": 1},
        opened_at="2026-08-27T16:40:00", entry_price=Decimal("-1.51")))
    ledger.save()
    server.PATHS.ledger = str(tmp_path / "ledger.json")

    import halstreet.execution.mcp_client as mcp

    class _Half:
        async def get_option_snapshot(self, symbols, **_):
            return {"snapshots": {"QQQ261016C00765000": {
                "latestQuote": {"bp": 4.4, "ap": 4.6}}}}

    monkeypatch.setattr(mcp.AlpacaMCP, "from_env", staticmethod(lambda _e="dev": _Half()))
    body = json.loads(asyncio.run(server.api_marks()).body)
    assert body["marks"]["s1"]["missing"] == ["QQQ261016C00775000"]
    assert "mark" not in body["marks"]["s1"]
