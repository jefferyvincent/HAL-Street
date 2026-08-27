"""Which model runs which stage, and where the tokens actually went.

The committee costs four calls where the single-call path costs one, and three of
those four decide nothing: the catalyst turns headlines into a lean against a closed
schema, and the two researchers write a paragraph each for something else to read.
Only the judge picks a structure and writes the rationale that reaches the ledger.

Two things follow, and both are tested here. The three research stages drop a model
tier and the judge does not. And the spend is recorded per stage with the model that
produced it, because one aggregate had no price the moment the four calls stopped
being the same model.
"""

from __future__ import annotations

import json

import pytest

from halstreet.agent import committee as C
from halstreet.marketdata.news import Headline


class _Usage:
    input_tokens, output_tokens, cache_read_input_tokens = 10, 20, 0


class _Block:
    def __init__(self, type_, text=""):
        self.type, self.text = type_, text


class _Recording:
    """Answers anything, and keeps the model each call asked for."""

    def __init__(self, text='{"lean": "bullish", "confidence": 0.6, "note": "n"}'):
        self.messages = self
        self.models: list[str] = []
        self._text = text

    def create(self, **kwargs):
        self.models.append(kwargs["model"])
        return type("R", (), {
            "usage": _Usage(), "stop_reason": "end_turn",
            "content": [_Block("text", self._text)],
        })()


#: What the judge returns when it declines. The schema is closed and its required
#: fields are checked before `action`, so a pass carries them too — this is the shape
#: structured output actually emits, not a minimal hand-written one.
PASSED = json.dumps({
    "action": "pass", "underlying": "SPY", "name": "none", "legs": [], "qty": 0,
    "limit_price": "0",
    # Long enough to clear MIN_PASS_RATIONALE_CHARS. A shorter one is an
    # *unexplained* pass, which is the other case entirely and is tested below.
    "rationale": "The chain is thin and the desk is already long this name.",
})

#: The same, with the rationale missing — the one case the judge reopens.
UNEXPLAINED = json.dumps({"action": "pass", "rationale": "",
                          "underlying": "SPY", "name": "none", "legs": [], "qty": 0,
                          "limit_price": "0"})


def committee(client, **kw):
    return C.Committee(client, model="judge-model", analyst_model="analyst-model", **kw)


# --- who runs what --------------------------------------------------------------

def test_the_catalyst_runs_on_the_analyst_model():
    client = _Recording()
    news = [Headline(headline="h", ts="2026-08-27T16:00:00+00:00", source="wire")]
    committee(client).catalyst(underlying="SPY", evidence={}, headlines=news)
    assert client.models == ["analyst-model"]


def test_both_researchers_run_on_the_analyst_model():
    client = _Recording("a case")
    committee(client).debate("brief")
    assert client.models == ["analyst-model", "analyst-model"]


def test_the_judge_runs_on_the_strongest_model():
    """The one stage that picks a structure. Everything else feeds it."""
    client = _Recording(PASSED)
    committee(client).judge(system="sys", brief="brief")
    assert client.models == ["judge-model"]


def test_the_default_analyst_tier_is_below_the_default_judge():
    assert C.ANALYST_MODEL != C.DEFAULT_MODEL


def test_setting_one_variable_puts_the_whole_committee_back_on_one_model(monkeypatch):
    """So the tiering can be measured against the thing it replaced, not argued about."""
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5")
    monkeypatch.delenv("COMMITTEE_ANALYST_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    made = C.Committee.from_env()
    assert made.model == made.analyst_model == "claude-opus-5"


def test_the_analyst_tier_can_be_pushed_further_down_on_its_own(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5")
    monkeypatch.setenv("COMMITTEE_ANALYST_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    made = C.Committee.from_env()
    assert made.model == "claude-opus-5"
    assert made.analyst_model == "claude-haiku-4-5-20251001"


def test_an_unset_environment_still_tiers(monkeypatch):
    for name in ("LLM_MODEL", "COMMITTEE_ANALYST_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    made = C.Committee.from_env()
    assert (made.model, made.analyst_model) == (C.DEFAULT_MODEL, C.ANALYST_MODEL)


# --- where the tokens went ------------------------------------------------------

def test_every_call_reports_the_model_that_spent_the_tokens():
    """5,000 tokens has no price until you know what spent them."""
    client = _Recording("case")
    _, counts, _ = committee(client)._call("sys", "user", max_tokens=100,
                                           model="analyst-model")
    assert counts["model"] == "analyst-model"
    assert (counts["in"], counts["out"]) == (10, 20)


def test_a_stage_that_made_no_call_names_no_model():
    """"No headlines" is a real outcome and it costs nothing. Attributing it to a
    model would put a zero-token row against a name that never ran."""
    _, counts = C.Committee(_Recording()).catalyst(underlying="SPY", headlines=[],
                                                   evidence={})
    assert counts["model"] is None
    assert counts["in"] == counts["out"] == 0


def test_the_session_keeps_the_total_and_the_breakdown():
    s = C.Session()
    s.spend({"in": 100, "out": 10, "cache_read": 0, "model": "analyst-model"}, "catalyst")
    s.spend({"in": 900, "out": 40, "cache_read": 0, "model": "judge-model"}, "judge")

    assert s.tokens == {"in": 1000, "out": 50, "cache_read": 0}
    assert s.stages["catalyst"]["model"] == "analyst-model"
    assert s.stages["judge"]["in"] == 900


def test_the_total_has_no_room_for_a_model_name():
    """The bug this shape invites is a one-word edit: `for key in counts`.

    What prevents it is that the total is keyed by its own three fields, so a name in
    the incoming dictionary has nowhere to land. Asserting the *keys* is what pins
    that; asserting the values are ints passes either way, because summing "a" + "b"
    would raise rather than produce a non-int.
    """
    s = C.Session()
    s.spend({"in": 1, "out": 1, "cache_read": 0, "model": "a"}, "catalyst")
    s.spend({"in": 1, "out": 1, "cache_read": 0, "model": "b"}, "judge")

    assert set(s.tokens) == {"in", "out", "cache_read"}
    assert s.tokens["in"] == 2


def test_summing_two_different_models_would_raise_rather_than_corrupt():
    """Belt and braces on the same edit: if the loop ever did walk `counts`, this is
    what it would do — and a TypeError in the middle of a cycle is a lost decision."""
    s = C.Session()
    s.spend({"in": 1, "out": 1, "cache_read": 0, "model": "a"}, "catalyst")
    with pytest.raises(TypeError):
        {**s.tokens, "model": "a"}["model"] + 1


def test_an_unattributed_spend_still_counts_toward_the_total():
    """The total is what the panel shows. A stage nobody named must not go missing."""
    s = C.Session()
    s.spend({"in": 7, "out": 3, "cache_read": 0})
    assert s.tokens["in"] == 7
    assert s.stages == {}


def test_the_breakdown_reaches_the_journal():
    s = C.Session()
    s.spend({"in": 100, "out": 10, "cache_read": 0, "model": "analyst-model"}, "debate")
    written = json.loads(json.dumps(s.to_journal()))

    assert written["stages"]["debate"]["model"] == "analyst-model"
    assert written["tokens"]["in"] == 100, "the old field is still there for old readers"


def test_the_debate_attributes_both_researchers_to_the_analyst_model():
    client = _Recording("case")
    _, _, counts, _ = committee(client).debate("brief")
    assert counts["model"] == "analyst-model"
    assert counts["in"] == 20, "both sides, summed"


def test_the_judges_follow_up_is_billed_to_the_judge_not_averaged():
    """A pass with no rationale is asked to explain itself, and that second call is
    the judge's too. Summing the counts must not lose or blend the model name."""
    client = _Recording(UNEXPLAINED)
    _, counts = committee(client).judge(system="sys", brief="brief")

    assert client.models == ["judge-model", "judge-model"]
    assert counts["model"] == "judge-model"
    assert counts["in"] == 20, "two calls, summed"


@pytest.mark.parametrize("stage", ["catalyst", "debate", "judge"])
def test_the_loop_names_every_stage_it_spends_on(stage):
    """An unnamed stage lands in the total and vanishes from the breakdown, which is
    exactly the state this replaced — and it looks like a stage that costs nothing."""
    from pathlib import Path

    source = Path("src/halstreet/agent/loop.py").read_text()
    assert f'session.spend(counts, "{stage}")' in source
