"""The proposal parser. Every test here is a model output that must be refused.

These are the failure modes an LLM actually produces: a strike that was never listed,
a leg on the wrong ticker, a missing price, a fifth leg, an invented field. The parser
rejects each with a reason rather than repairing it — repairing model output means
inventing a trade nobody proposed and then trading it.
"""

from __future__ import annotations

import json
from decimal import Decimal

from halstreet.agent.proposal import SCHEMA, parse_proposal

GOOD = {
    "underlying": "SPY",
    "name": "Oct-16 765/770 call spread",
    "qty": 1,
    "limit_price": "2.99",
    "rationale": "Mildly bullish into a low-IV tape; defined risk.",
    "confidence": 0.6,
    "legs": [
        {"symbol": "SPY261016C00765000", "side": "buy"},
        {"symbol": "SPY261016C00770000", "side": "sell"},
    ],
}


def test_parses_a_well_formed_proposal():
    r = parse_proposal(GOOD)
    assert r.ok
    p = r.proposal
    assert p.underlying == "SPY"
    assert p.structure.qty == 1
    assert p.structure.limit_price == Decimal("2.99")
    assert [leg.side.value for leg in p.structure.legs] == ["buy", "sell"]
    assert p.confidence == 0.6


def test_accepts_a_json_string_too():
    assert parse_proposal(json.dumps(GOOD)).ok


def test_negative_limit_price_is_a_credit_not_an_error():
    """The live fills confirmed the convention: negative is a credit received."""
    r = parse_proposal({**GOOD, "limit_price": "-4.04"})
    assert r.ok
    assert r.proposal.structure.limit_price == Decimal("-4.04")


# --- what a model actually gets wrong -------------------------------------------

def test_rejects_a_hallucinated_strike_format():
    bad = {**GOOD, "legs": [{"symbol": "SPY 765 CALL 10/16", "side": "buy"}]}
    r = parse_proposal(bad)
    assert not r.ok
    assert "not a valid OCC option symbol" in r.error


def test_rejects_a_leg_on_a_different_underlying():
    bad = {**GOOD, "legs": [
        {"symbol": "SPY261016C00765000", "side": "buy"},
        {"symbol": "QQQ261016C00500000", "side": "sell"},
    ]}
    r = parse_proposal(bad)
    assert not r.ok
    assert "is on QQQ, not the proposed SPY" in r.error


def test_rejects_a_fifth_leg():
    bad = {**GOOD, "legs": [{"symbol": f"SPY261016C0076{i}000", "side": "buy"} for i in range(5)]}
    r = parse_proposal(bad)
    assert not r.ok
    assert "4-leg ceiling" in r.error


def test_rejects_a_missing_limit_price():
    bad = {k: v for k, v in GOOD.items() if k != "limit_price"}
    r = parse_proposal(bad)
    assert not r.ok
    assert "limit_price" in r.error


def test_rejects_an_unparseable_price():
    r = parse_proposal({**GOOD, "limit_price": "about two dollars"})
    assert not r.ok
    assert "not a decimal" in r.error


def test_rejects_a_sub_penny_price():
    """Alpaca quotes options in pennies; a price we cannot send is not a proposal."""
    r = parse_proposal({**GOOD, "limit_price": "2.9912"})
    assert not r.ok
    assert "penny" in r.error


def test_rejects_zero_and_negative_quantity():
    for qty in (0, -3):
        r = parse_proposal({**GOOD, "qty": qty})
        assert not r.ok
        assert "positive integer" in r.error


def test_rejects_an_invented_field():
    """The schema is closed. A field the parser does not know is one the gates
    never checked, and 'override_risk_limit' is exactly the field to worry about."""
    r = parse_proposal({**GOOD, "override_risk_limit": True})
    assert not r.ok
    assert "override_risk_limit" in r.error


def test_rejects_an_empty_leg_list():
    r = parse_proposal({**GOOD, "legs": []})
    assert not r.ok
    assert "non-empty" in r.error


def test_rejects_a_bad_side():
    bad = {**GOOD, "legs": [{"symbol": "SPY261016C00765000", "side": "long"}]}
    r = parse_proposal(bad)
    assert not r.ok
    assert "'buy' or 'sell'" in r.error


def test_rejects_malformed_json_without_raising():
    r = parse_proposal("{not json")
    assert not r.ok
    assert r.error


def test_rejects_a_json_array():
    r = parse_proposal("[1, 2, 3]")
    assert not r.ok
    assert "expected a JSON object" in r.error


# --- what the model is structurally unable to say --------------------------------

def test_the_schema_offers_no_way_to_touch_risk_or_environment():
    """The strongest guarantee is a field that does not exist."""
    fields = set(SCHEMA["properties"])
    for forbidden in ("env", "environment", "paper", "limits", "max_loss",
                      "skip_gates", "gates", "account", "api_key"):
        assert forbidden not in fields


def test_confidence_is_carried_but_is_not_a_lever():
    """A limit a confident model can talk past is not a limit — the gates never
    read this field; it exists for the journal."""
    high = parse_proposal({**GOOD, "confidence": 1.0}).proposal
    assert high.confidence == 1.0
    import inspect

    from halstreet.gates import contract, defined_risk, liquidity, portfolio
    for module in (defined_risk, liquidity, portfolio, contract):
        assert "confidence" not in inspect.getsource(module)


# --- declining to trade --------------------------------------------------------

def test_a_pass_is_a_considered_outcome_not_a_parse_failure():
    # Without this, the instruction to propose nothing and a schema requiring a
    # priced structure cannot both be satisfied. What came back from live runs was
    # qty 0 or an empty legs array — which read as a broken model rather than as the
    # deliberate decline it actually was.
    result = parse_proposal({
        "action": "pass",
        "underlying": "QQQ", "name": "", "legs": [], "qty": 0,
        "limit_price": "0", "rationale": "entry slippage exceeds max gain on all three",
    })
    assert result.abstained
    assert not result.ok
    assert result.error is None
    assert "slippage" in result.rationale


def test_a_pass_needs_no_valid_structure_around_it():
    # The other fields are explicitly ignored, so a decline cannot fail on them.
    result = parse_proposal({"action": "pass", "underlying": "", "name": "",
                             "legs": [], "qty": 0, "limit_price": "not a price",
                             "rationale": ""})
    assert result.abstained
    assert result.rationale == "(no reason given)"


def test_a_degenerate_structure_is_still_a_failure_not_a_pass():
    # Expressing a decline by proposing nothing-shaped-like-something must keep
    # failing loudly, or the explicit pass has no reason to be used.
    for bad in ({"legs": []}, {"qty": 0}):
        payload = {"action": "trade", "underlying": "SPY", "name": "x",
                   "legs": [{"symbol": "SPY261016C00765000", "side": "sell"}],
                   "qty": 1, "limit_price": "-0.50", "rationale": "r", **bad}
        result = parse_proposal(payload)
        assert not result.ok and not result.abstained
        assert result.error


def test_a_proposal_without_an_action_is_still_a_trade():
    # Refusing an otherwise complete proposal over a field describing what it
    # already obviously is would be pedantry with a cost.
    result = parse_proposal({
        "underlying": "SPY", "name": "Oct-16 765/770 call spread",
        "legs": [{"symbol": "SPY261016C00765000", "side": "sell", "ratio_qty": 1},
                 {"symbol": "SPY261016C00770000", "side": "buy", "ratio_qty": 1}],
        "qty": 2, "limit_price": "-0.50", "rationale": "premium",
    })
    assert result.ok and not result.abstained
