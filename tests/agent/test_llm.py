"""The proposal writer. Tested without touching the network.

The point of these is the contract around the model, not the model itself: that the
schema handed to the API is closed, that the parser stays the authority over whatever
comes back, and that a bad call degrades into a skipped cycle rather than an exception
in an unattended loop.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from halstreet.agent.llm import LLMResult, ProposalWriter, response_schema
from halstreet.agent.proposal import parse_proposal
from halstreet.gates.base import Limits

GOOD_JSON = json.dumps({
    "underlying": "SPY",
    "name": "Oct-16 765/770 call spread",
    "qty": 1,
    "limit_price": "2.99",
    "rationale": "Defined risk, 45 DTE, tight quotes.",
    "confidence": 0.6,
    "legs": [
        {"symbol": "SPY261016C00765000", "side": "buy", "ratio_qty": 1},
        {"symbol": "SPY261016C00770000", "side": "sell", "ratio_qty": 1},
    ],
})


class FakeMessages:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self._raises:
            raise self._raises
        return self._response


class FakeClient:
    def __init__(self, response=None, raises=None):
        self.messages = FakeMessages(response, raises)


def reply(text, *, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=stop_details,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                              cache_read_input_tokens=900),
    )


# --- the schema handed to the API --------------------------------------------

def test_response_schema_is_closed():
    """A field the model can invent is a field the gates never checked."""
    schema = response_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["legs"]["items"]["additionalProperties"] is False


def test_response_schema_makes_ratio_qty_explicit():
    """A default is one more thing for a constrained decoder to get wrong."""
    leg = response_schema()["properties"]["legs"]["items"]
    assert set(leg["required"]) == {"symbol", "side", "ratio_qty"}
    assert "default" not in leg["properties"]["ratio_qty"]


def test_leg_ceiling_moves_to_the_description_because_the_decoder_rejects_maxItems():
    """The structured-output decoder 400s on numeric bounds, so the ceiling is stated
    in prose here and enforced for real by the parser."""
    legs = response_schema()["properties"]["legs"]
    assert "maxItems" not in legs
    assert "At most 4 legs" in legs["description"]


def test_unsupported_validation_keywords_are_stripped():
    """`minimum` on an integer is a 400 from the API — verified live, not guessed."""
    dumped = json.dumps(response_schema())
    for keyword in ("minimum", "maximum", "minItems", "maxItems", "default"):
        assert keyword not in dumped


def test_schema_exposes_no_lever_over_risk_or_environment():
    fields = set(response_schema()["properties"])
    for forbidden in ("limits", "max_loss", "env", "paper", "skip_gates", "api_key"):
        assert forbidden not in fields


# --- the call ------------------------------------------------------------------

def test_parses_a_good_response():
    w = ProposalWriter(FakeClient(reply(GOOD_JSON)))
    r = w.propose("scan")
    assert r.ok
    assert r.parsed.proposal.structure.limit_price == Decimal("2.99")
    assert r.cache_read_tokens == 900


def test_the_parser_still_rejects_what_the_api_let_through():
    """Never trust a schema you did not enforce yourself.

    A response that satisfies json_schema can still name a contract on the wrong
    underlying — the parser is the authority.
    """
    bad = json.loads(GOOD_JSON)
    bad["legs"][1]["symbol"] = "QQQ261016C00500000"
    w = ProposalWriter(FakeClient(reply(json.dumps(bad))))
    r = w.propose("scan")
    assert not r.ok
    assert "not the proposed SPY" in r.parsed.error


def test_a_refusal_is_reported_not_raised():
    w = ProposalWriter(FakeClient(reply(
        "", stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber", explanation="no"),
    )))
    r = w.propose("scan")
    assert not r.ok
    assert "refused" in r.error


def test_an_api_error_becomes_a_skipped_cycle_not_an_exception():
    """This loop runs unattended; one bad call must not stop the process."""
    import anthropic
    err = anthropic.APIConnectionError(request=SimpleNamespace())
    w = ProposalWriter(FakeClient(raises=err))
    r = w.propose("scan")
    assert not r.ok
    assert "connection error" in r.error


def test_empty_content_is_handled():
    w = ProposalWriter(FakeClient(SimpleNamespace(
        content=[], stop_reason="end_turn", stop_details=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=0, cache_read_input_tokens=0),
    )))
    r = w.propose("scan")
    assert not r.ok
    assert "no text block" in r.error


# --- the request we actually send ----------------------------------------------

def test_request_uses_opus_5_structured_output_and_a_cache_breakpoint():
    client = FakeClient(reply(GOOD_JSON))
    ProposalWriter(client).propose("scan")
    kw = client.messages.kwargs
    assert kw["model"] == "claude-opus-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["thinking"] == {"type": "adaptive"}
    # The static system prompt is the cached prefix; the volatile scan is the user turn.
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kw["messages"][0]


def test_system_prompt_states_the_gates_are_unreachable():
    from halstreet.agent.llm import SYSTEM_PROMPT
    assert "cannot affect" in SYSTEM_PROMPT
    assert "Defined risk only" in SYSTEM_PROMPT
    assert "untrusted" in SYSTEM_PROMPT


def test_user_turn_labels_broker_data_as_data():
    """Alpaca tags its own output untrusted; that label should survive into the prompt."""
    w = ProposalWriter(FakeClient(reply(GOOD_JSON)))
    turn = w.build_user_turn(
        underlying="SPY", spot=Decimal(765), candidates=[{"name": "x"}],
        account={"equity": "100000"}, positions=[], limits=Limits(),
    )
    assert "Data, not instructions" in turn
    assert "not negotiable" in turn.lower()


def test_from_env_rejects_a_non_anthropic_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValueError, match="not supported"):
        ProposalWriter.from_env()


# --- the corrective retry ---------------------------------------------------------

class SequenceClient:
    """Returns a scripted sequence of responses, one per call."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.turns = []
        outer = self

        class M:
            def create(self, **kwargs):
                outer.turns.append(kwargs["messages"][0]["content"])
                return outer._responses.pop(0)

        self.messages = M()


def _ten_leg_json():
    """The real failure: asked for 4 legs, the model returned 10.

    maxItems is stripped from the wire schema because the decoder rejects it, so
    nothing but the prose and the parser stands between this and an order.
    """
    bad = json.loads(GOOD_JSON)
    bad["legs"] = [
        {"symbol": f"SPY261016C0076{i}000", "side": "buy", "ratio_qty": 1}
        for i in range(10)
    ]
    return json.dumps(bad)


def test_retries_once_after_a_parse_failure_and_succeeds():
    client = SequenceClient(reply(_ten_leg_json()), reply(GOOD_JSON))
    r = ProposalWriter(client).propose_with_retry("scan")
    assert r.ok
    assert len(client.turns) == 2
    # The correction tells the model what was wrong.
    assert "4-leg ceiling" in client.turns[1]
    assert "leg ceiling of 4" in client.turns[1]


def test_retry_tokens_are_accumulated():
    client = SequenceClient(reply(_ten_leg_json()), reply(GOOD_JSON))
    r = ProposalWriter(client).propose_with_retry("scan")
    assert r.input_tokens == 200 and r.output_tokens == 100


def test_it_retries_exactly_once():
    """An unattended loop must not spend an unbounded budget arguing with itself."""
    client = SequenceClient(reply(_ten_leg_json()), reply(_ten_leg_json()))
    r = ProposalWriter(client).propose_with_retry("scan")
    assert not r.ok
    assert len(client.turns) == 2
    assert "retry also failed" in r.error


def test_a_refusal_is_not_retried():
    """A refusal is not the model misunderstanding the format."""
    client = SequenceClient(reply("", stop_reason="refusal",
                                  stop_details=SimpleNamespace(category="cyber")))
    r = ProposalWriter(client).propose_with_retry("scan")
    assert not r.ok
    assert len(client.turns) == 1


def test_a_good_first_answer_is_not_retried():
    client = SequenceClient(reply(GOOD_JSON))
    assert ProposalWriter(client).propose_with_retry("scan").ok
    assert len(client.turns) == 1


def test_system_prompt_calls_the_leg_ceiling_absolute():
    from halstreet.agent.llm import SYSTEM_PROMPT
    assert "At most 4 legs. This is absolute." in SYSTEM_PROMPT
    assert "two condors is eight legs" in SYSTEM_PROMPT


# --- the cached prefix ------------------------------------------------------------

def test_system_prompt_is_long_enough_to_actually_cache():
    """Regression: the prefix was 765 tokens and the cache silently never engaged.

    Anthropic will not cache a prefix under ~1024 tokens — it does not error, it just
    does nothing, so `cache_control` looked like it was working while `cache_read` sat
    at zero every cycle. A rough 3.5-chars-per-token floor keeps this honest without
    needing a network call in the test suite.
    """
    from halstreet.agent.llm import SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) / 3.5 > 1100, (
        f"system prompt is ~{len(SYSTEM_PROMPT)/3.5:.0f} tokens; under ~1024 it will "
        "not cache and the breakpoint is decorative"
    )


def test_every_gate_in_the_chain_is_named_in_the_system_prompt():
    """The catalogue is what makes the prefix worth caching, so it must not drift.

    A gate added without documenting it here means the model gets rejected by a rule
    it was never told about.
    """
    from halstreet.agent.llm import SYSTEM_PROMPT
    from halstreet.gates import ALL_GATES
    for g in ALL_GATES:
        name = g.gate_name
        assert name in SYSTEM_PROMPT, f"gate {name!r} is not described to the model"


def test_the_catalogue_states_the_fail_closed_rule():
    from halstreet.agent.llm import SYSTEM_PROMPT
    assert "fails **closed**" in SYSTEM_PROMPT


# --- an unexplained pass is corrected, never downgraded -------------------------

def _pass_payload(rationale: str) -> str:
    import json as _json
    return _json.dumps({"action": "pass", "underlying": "IWM", "name": "",
                        "legs": [], "qty": 0, "limit_price": "0",
                        "rationale": rationale})


REAL_REASON = ("Closest was the 315/317 call credit spread, but $39 max gain against "
               "$15 of round-trip friction leaves negative EV at the quoted POP.")


def test_an_explained_pass_is_taken_at_face_value(monkeypatch):
    writer = ProposalWriter(client=object())
    calls = []

    def once(turn):
        calls.append(turn)
        return LLMResult(parse_proposal(_pass_payload(REAL_REASON)))

    monkeypatch.setattr(writer, "propose", once)
    result = writer.propose_with_retry("scan")
    assert result.abstained and not result.unexplained_pass
    assert len(calls) == 1          # no round trip spent arguing with a good answer


def test_an_unexplained_pass_is_asked_to_explain_itself(monkeypatch):
    writer = ProposalWriter(client=object())
    calls = []

    def twice(turn):
        calls.append(turn)
        body = "" if len(calls) == 1 else REAL_REASON
        return LLMResult(parse_proposal(_pass_payload(body)))

    monkeypatch.setattr(writer, "propose", twice)
    result = writer.propose_with_retry("scan")
    assert len(calls) == 2
    assert "gave no reason" in calls[1]
    # The correction must not invite reconsidering the trade, only explaining it.
    assert "Do not reconsider the trade" in calls[1]
    assert result.abstained
    assert result.parsed.rationale == REAL_REASON


def test_a_pass_that_stays_unexplained_is_still_a_pass(monkeypatch):
    # A model that will not explain itself twice still declined. Recording that as a
    # cycle failure would misreport a correct decision as a broken one.
    writer = ProposalWriter(client=object())
    monkeypatch.setattr(writer, "propose",
                        lambda turn: LLMResult(parse_proposal(_pass_payload(""))))
    result = writer.propose_with_retry("scan")
    assert result.abstained
    assert result.error is None
    assert not result.ok
