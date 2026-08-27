"""What the model calls cost, and the two ways that number goes wrong quietly.

The committee is four calls where the single-call path is one. That is a defensible
trade only if somebody can see the bill, and the bill was in the journal and on no
screen.

Both failure modes here are silent. Double-counting reads as a plausible number that
happens to be twice the truth — I reported 1.39M input against a real 693K on exactly
this data before noticing the committee and the proposal carry one spend between them.
And a cost that omits an unpriced tier reads as a total while being a fraction, which
is worse, because the tiering deliberately moved most of the input onto the tier this
project cannot cite a price for.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.telemetry import pricing
from halstreet.telemetry.server import _spend

#: So a test can pass `None` and mean it. The first version of this helper used
#: `None` as its own default, which quietly turned the malformed-record case into the
#: well-formed one and passed while testing nothing.
UNSET = object()


def proposal(tokens: object = UNSET, **over) -> dict:
    return {"event": "proposal", "underlying": "SPY", "ts": "2026-08-27T20:00:00+00:00",
            "tokens": {"in": 100, "out": 10, "cache_read": 5}
            if tokens is UNSET else tokens, **over}


def committee(stages: dict, **over) -> dict:
    return {"event": "committee", "underlying": "SPY", "ts": "2026-08-27T20:00:00+00:00",
            "tokens": {"in": 100, "out": 10, "cache_read": 5}, "stages": stages, **over}


TIERED = {
    "catalyst": {"in": 10, "out": 2, "cache_read": 0, "model": "analyst"},
    "debate": {"in": 60, "out": 4, "cache_read": 0, "model": "analyst"},
    "judge": {"in": 30, "out": 4, "cache_read": 5, "model": "judge"},
}


@pytest.fixture(autouse=True)
def _no_price_env(monkeypatch):
    monkeypatch.delenv("LLM_PRICES", raising=False)


# --- the double count ------------------------------------------------------------

def test_one_cycle_is_counted_once_not_twice():
    """The committee journals its session total and the loop journals the same figure
    again on the proposal. Summing both doubles the spend, which is what I did."""
    spent = _spend([committee(TIERED), proposal()])
    assert spent["total"]["in"] == 100
    assert spent["cycles"] == 1


def test_the_proposal_is_the_record_counted():
    """It is the only one present on both paths: with the committee off there is no
    committee record at all, and the single call still journals its usage there."""
    assert _spend([proposal()])["total"]["in"] == 100
    assert _spend([committee(TIERED)])["total"]["in"] == 0


def test_cycles_are_counted_from_proposals_too():
    assert _spend([proposal(), proposal(), proposal()])["cycles"] == 3


# --- the split -------------------------------------------------------------------

def test_the_stages_supply_the_model_split():
    models = {m["model"]: m for m in _spend([committee(TIERED), proposal()])["models"]}
    assert models["analyst"]["in"] == 70
    assert models["judge"]["in"] == 30
    assert models["judge"]["out"] == 4


def test_a_committee_cycle_is_fully_attributed():
    """The stages sum to the proposal total by construction, so nothing is stray."""
    spent = _spend([committee(TIERED), proposal()])
    assert spent["unattributed"] == {"in": 0, "out": 0, "cache_read": 0}


def test_a_cycle_with_no_stages_is_reported_as_unattributed_not_assigned():
    """Every cycle run before per-stage accounting existed, and every cycle run with
    the committee off. Counted in the totals, absent from the split, and named."""
    spent = _spend([proposal()])
    assert spent["total"]["in"] == 100
    assert spent["models"] == []
    assert spent["unattributed"]["in"] == 100
    assert spent["partial"] is True


def test_a_stage_that_made_no_call_names_no_model_and_is_skipped():
    """"No headlines" is a real outcome that costs nothing. A zero-token row against
    a model that never ran is worse than no row."""
    spent = _spend([committee({
        "catalyst": {"in": 0, "out": 0, "cache_read": 0, "model": None},
        "judge": {"in": 30, "out": 4, "cache_read": 0, "model": "judge"},
    }), proposal({"in": 30, "out": 4, "cache_read": 0})])
    assert [m["model"] for m in spent["models"]] == ["judge"]


def test_the_split_is_ordered_so_the_card_does_not_reshuffle():
    spent = _spend([committee(TIERED), proposal()])
    assert [m["model"] for m in spent["models"]] == sorted(m["model"] for m in spent["models"])


# --- the money -------------------------------------------------------------------

def test_a_priced_model_gets_a_cost(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", '{"judge": [5, 25]}')
    (row,) = [m for m in _spend([committee(TIERED), proposal()])["models"]
              if m["model"] == "judge"]
    # 30 in at $5/MTok plus 4 out at $25/MTok.
    assert row["cost_usd"] == (Decimal(30) * 5 + Decimal(4) * 25) / pricing.PER


def test_an_unpriced_model_costs_none_rather_than_zero(monkeypatch):
    """Zero is a claim, and it is the wrong one."""
    monkeypatch.setenv("LLM_PRICES", '{"judge": [5, 25]}')
    (row,) = [m for m in _spend([committee(TIERED), proposal()])["models"]
              if m["model"] == "analyst"]
    assert row["cost_usd"] is None


def test_a_total_missing_a_tier_is_marked_partial(monkeypatch):
    """The failure this exists to prevent. The tiering moved most of the input onto
    the tier whose price this project cannot cite, so a total that quietly omitted it
    would be a fraction wearing the word 'total'."""
    monkeypatch.setenv("LLM_PRICES", '{"judge": [5, 25]}')
    spent = _spend([committee(TIERED), proposal()])
    assert spent["partial"] is True
    assert Decimal(spent["cost_usd"]) >= 0


def test_a_fully_priced_run_is_not_partial(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", '{"judge": [5, 25], "analyst": [3, 15]}')
    spent = _spend([committee(TIERED), proposal()])
    assert spent["partial"] is False


def test_cached_reads_are_counted_and_left_out_of_the_cost(monkeypatch):
    """Anthropic bills them at a discount this project has no sourced figure for.
    Charging list price overstates; guessing a discount is a guess with a dollar sign
    in front of it. Counted, shown, excluded — the only one of the three that is true.
    """
    monkeypatch.setenv("LLM_PRICES", '{"judge": [5, 25], "analyst": [3, 15]}')
    spent = _spend([committee(TIERED), proposal()])
    assert spent["total"]["cache_read"] == 5

    heavy = dict(TIERED, judge={**TIERED["judge"], "cache_read": 10_000_000})
    inflated = _spend([committee(heavy), proposal()])
    assert inflated["cost_usd"] == spent["cost_usd"]


def test_the_price_table_is_reported_so_the_figure_can_be_checked(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", '{"analyst": [3, 15]}')
    prices = _spend([proposal()])["prices"]
    assert prices["analyst"] == {"in": "3", "out": "15"}
    assert "claude-opus-5" in prices, "the shipped default survives the merge"


# --- shapes it must survive ------------------------------------------------------

@pytest.mark.parametrize("tokens", [None, "lots", 7, [], {"in": "many"}, {}])
def test_a_malformed_token_record_is_ignored_rather_than_fatal(tokens):
    """This route is polled every five seconds. A raise here empties the whole panel."""
    spent = _spend([proposal(tokens)])
    assert spent["total"]["in"] == 0


@pytest.mark.parametrize("stages", [None, "judge", 7, {"judge": "opus"}, {"judge": None}])
def test_a_malformed_stage_record_is_ignored(stages):
    assert _spend([committee(stages)])["models"] == []


def test_an_empty_journal_costs_nothing_and_says_so():
    spent = _spend([])
    assert spent["total"] == {"in": 0, "out": 0, "cache_read": 0}
    assert spent["cycles"] == 0
    assert spent["partial"] is False, "nothing counted, so nothing is missing a price"


def test_unattributed_never_goes_negative():
    """If the stages ever exceeded the proposal total, a subtraction would report a
    negative token count — which is not a thing."""
    spent = _spend([committee(TIERED), proposal({"in": 1, "out": 1, "cache_read": 0})])
    assert all(v >= 0 for v in spent["unattributed"].values())


# --- the price table itself ------------------------------------------------------

def test_only_sourced_prices_ship(monkeypatch):
    """Opus 5 is documented at $5/$25 per MTok. The analyst tier's price is not in
    anything this project can cite, so it is absent rather than approximated — a
    visible gap beats a silent understatement."""
    monkeypatch.delenv("LLM_PRICES", raising=False)
    assert pricing.from_env() == {"claude-opus-5": (Decimal(5), Decimal(25))}


def test_the_environment_can_add_a_price(monkeypatch):
    monkeypatch.setenv("LLM_PRICES", '{"claude-sonnet-5": [3, 15]}')
    table = pricing.from_env()
    assert table["claude-sonnet-5"] == (Decimal(3), Decimal(15))
    assert table["claude-opus-5"] == (Decimal(5), Decimal(25))


def test_the_environment_can_correct_a_shipped_price(monkeypatch):
    """Prices change. A constant nobody can override is a constant that goes stale."""
    monkeypatch.setenv("LLM_PRICES", '{"claude-opus-5": [6, 30]}')
    assert pricing.from_env()["claude-opus-5"] == (Decimal(6), Decimal(30))


@pytest.mark.parametrize("raw", [
    "not json", "[]", '"a string"', "7",
    '{"m": 5}', '{"m": [5]}', '{"m": [5, 25, 100]}',
    '{"m": ["free", "cheap"]}', '{"m": [-5, 25]}', '{"m": null}',
])
def test_a_malformed_price_is_ignored_rather_than_fatal(monkeypatch, raw):
    """A typo in an environment variable must not stop the agent reporting, and an
    unpriced model is already a state the console renders."""
    monkeypatch.setenv("LLM_PRICES", raw)
    assert pricing.from_env() == {"claude-opus-5": (Decimal(5), Decimal(25))}


def test_a_model_with_no_price_costs_none():
    assert pricing.cost("nobody", tokens_in=1000, tokens_out=1000, table={}) is None


def test_the_arithmetic_is_per_million():
    table = {"m": (Decimal(5), Decimal(25))}
    assert pricing.cost("m", tokens_in=1_000_000, tokens_out=0, table=table) == 5
    assert pricing.cost("m", tokens_in=0, tokens_out=1_000_000, table=table) == 25


def test_the_cost_is_exact_rather_than_floating():
    """Same rule as every other money figure here: a price through binary floating
    point is not the price."""
    table = {"m": (Decimal("0.1"), Decimal("0.2"))}
    got = pricing.cost("m", tokens_in=3_000_000, tokens_out=0, table=table)
    assert got == Decimal("0.3")
    assert isinstance(got, Decimal)
