"""Whether the strategy engines have earned their vote.

Five engines read the tape every cycle and none of them was ever marked. The journal
already holds what each one said and what the underlying did next, so this is a
measurement the system can take on itself — and the numbers it produces are only worth
anything if the ways of flattering an engine are closed off first. Most of the tests
below are those ways.
"""
from datetime import UTC, datetime
from decimal import Decimal

from halstreet.telemetry import scorecard


def _at(day, hour=14):
    return datetime(2026, 8, day, hour, tzinfo=UTC).isoformat()


def _start(day, underlying="SPY", spot="500", hour=14):
    return {"event": "cycle_start", "ts": _at(day, hour),
            "underlying": underlying, "spot": spot}


def _view(day, underlying="SPY", *, bias="bullish", hour=14, persistence=None,
          structure=None, patterns=None):
    return {"event": "market_view", "ts": _at(day, hour), "underlying": underlying,
            "bias": bias, "persistence": persistence, "structure": structure,
            "patterns": patterns or []}


# --- reading the calls out of the journal --------------------------------------------

def test_each_engine_is_read_as_its_own_call():
    events = [_start(26), _view(26, bias="bullish",
                                persistence={"current_state": "down",
                                             "label": "persistent"},
                                structure={"direction": "bearish"},
                                patterns=[{"side": "bullish"}])]
    by = {c.engine: c.side for c in scorecard.calls(events)}
    assert by == {"bias": "bullish", "markov": "bearish",
                  "smc": "bearish", "patterns": "bullish"}


def test_a_memoryless_chain_is_not_a_prediction():
    """The Markov module says so itself: past `informative_for_days` it tells you
    nothing the base rate does not. Scoring that as a directional call would credit or
    blame it for a coin flip it declined to call."""
    events = [_start(26), _view(26, persistence={"current_state": "up",
                                                 "label": "memoryless"})]
    assert [c for c in scorecard.calls(events) if c.engine == "markov"] == []


def test_patterns_that_disagree_make_no_call():
    """Two patterns pointing opposite ways is not a bullish read with a caveat. It is
    the detector declining, and averaging it into a side invents an opinion."""
    events = [_start(26), _view(26, patterns=[{"side": "bullish"},
                                              {"side": "bearish"}])]
    assert [c for c in scorecard.calls(events) if c.engine == "patterns"] == []


def test_a_view_with_no_price_beside_it_is_not_scored():
    """No spot, no move, no verdict. Constitution VII: the answer is that we could not
    tell, which is not the same as the engine being wrong."""
    assert scorecard.calls([_view(26)]) == []


def test_the_price_comes_from_this_underlyings_own_cycle():
    """A SPY read priced off the QQQ cycle that happened to run first would measure the
    wrong instrument and never announce it."""
    events = [_start(26, "QQQ", "400"), _start(26, "SPY", "500"), _view(26, "SPY")]
    spy = [c for c in scorecard.calls(events) if c.underlying == "SPY"]
    assert all(c.spot == Decimal(500) for c in spy)


# --- judging them --------------------------------------------------------------------

def _bias_call(day, side, spot):
    return scorecard.Call(engine="bias", underlying="SPY", ts=_at(day),
                          side=side, spot=Decimal(spot))


def _prices(pairs):
    return {"SPY": [(datetime.fromisoformat(_at(d)), Decimal(p)) for d, p in pairs]}


def test_a_call_is_right_when_price_went_its_way():
    judged = scorecard.judge([_bias_call(26, "bullish", "500")],
                             _prices([(26, "500"), (28, "510")]), horizon_days=1)
    assert [j.right for j in judged] == [True]


def test_a_call_is_wrong_when_it_did_not():
    judged = scorecard.judge([_bias_call(26, "bearish", "500")],
                             _prices([(26, "500"), (28, "510")]), horizon_days=1)
    assert [j.right for j in judged] == [False]


def test_a_call_with_no_price_at_the_horizon_yet_is_not_counted_either_way():
    """The most recent session's calls have no future to be measured against. Counting
    them as wrong would make every engine look worse the more recently it ran."""
    judged = scorecard.judge([_bias_call(26, "bullish", "500")],
                             _prices([(26, "500")]), horizon_days=1)
    assert judged == []


def test_a_neutral_call_is_kept_but_makes_no_directional_claim():
    """It is a real thing an engine said and the count should show it. It is not a
    prediction, so it cannot be right or wrong."""
    judged = scorecard.judge([_bias_call(26, "neutral", "500")],
                             _prices([(26, "500"), (28, "510")]), horizon_days=1)
    assert [j.right for j in judged] == [None]


def test_price_that_did_not_move_is_not_a_win_for_either_side():
    judged = scorecard.judge([_bias_call(26, "bullish", "500")],
                             _prices([(26, "500"), (28, "500")]), horizon_days=1)
    assert [j.right for j in judged] == [None]


# --- the score ------------------------------------------------------------------------

def _judged(engine, rights):
    out = []
    for r in rights:
        call = scorecard.Call(engine=engine, underlying="SPY", ts=_at(26),
                              side="bullish", spot=Decimal(500))
        out.append(scorecard.Judged(call=call, later=Decimal(505),
                                    move_pct=Decimal(1), right=r))
    return out


def test_accuracy_is_measured_against_the_base_rate_not_against_a_coin():
    """A tape that rose on nine days in ten makes every bullish engine look brilliant.
    Edge is the only honest figure: how much better than always saying "up"."""
    scores = scorecard.score(_judged("bias", [True] * 9 + [False]), base_rate=0.9,
                             min_calls=5)
    assert scores[0].accuracy == 0.9
    assert scores[0].edge == 0.0


def test_an_engine_below_the_sample_floor_reports_no_accuracy_at_all():
    """Three right out of four is 75% and means nothing. A number with no support is
    worse than a blank, because a blank cannot be acted on by mistake."""
    s = scorecard.score(_judged("bias", [True, True, True, False]), base_rate=0.5,
                        min_calls=20)[0]
    assert s.accuracy is None and s.edge is None
    assert s.calls == 4


def test_neutral_calls_count_as_calls_but_not_as_chances_to_be_right():
    s = scorecard.score(_judged("bias", [True, False, None, None]), base_rate=0.5,
                        min_calls=2)[0]
    assert s.calls == 4
    assert s.directional == 2
    assert s.accuracy == 0.5


def test_the_base_rate_is_taken_from_the_same_moves_being_scored():
    """Not from a constant, and not from a different window. Every judged call carries
    the move it was judged on, so the rate of up-moves among them is the thing an
    engine has to beat."""
    up = scorecard.Judged(call=_bias_call(26, "bullish", "500"),
                          later=Decimal(505), move_pct=Decimal(1), right=True)
    down = scorecard.Judged(call=_bias_call(26, "bullish", "500"),
                            later=Decimal(495), move_pct=Decimal(-1), right=False)
    assert scorecard.base_rate([up, up, up, down]) == 0.75
    assert scorecard.base_rate([]) is None


# --- what the table says when it has nothing to say ----------------------------------

def test_the_table_refuses_to_look_like_a_verdict_when_it_is_empty():
    """The failure mode this whole feature could have: an empty table read as "the
    engines scored zero" rather than "nothing has been measured yet"."""
    from halstreet.cli.scorecard import render
    text = render([], base=None, horizon=1, judged=0, days=["2026-08-26"])
    assert "No engine has been read against a later price yet" in text
    assert "Not a verdict on the engines" in text


def test_a_withheld_accuracy_prints_a_dash_and_not_a_zero():
    """Constitution VII. A 0% next to an engine name is a claim that it was wrong every
    time, which is the opposite of what a missing measurement means."""
    from halstreet.cli.scorecard import render
    row = scorecard.EngineScore(engine="markov", calls=3, directional=3, correct=2,
                                accuracy=None, edge=None, note="3 of 20 calls needed")
    text = render([row], base=0.5, horizon=1, judged=3, days=["2026-08-26"])
    line = next(row for row in text.splitlines() if row.startswith("markov"))
    assert "%" not in line, "a percentage here would be a measurement nobody took"
    assert line.count("—") == 2
