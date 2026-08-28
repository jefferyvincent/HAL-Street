"""The burn test — every structure family tried against the news, before the debate.

The committee used to receive one ranked menu and a catalyst's paragraph, and the
judge had to do two jobs at once: work out what the news implied about direction, and
work out which structure expresses that. The second of those is arithmetic. A put
credit spread wants the tape up or flat; a call credit spread wants it down or flat;
a condor wants it still. Nothing about that depends on the day, and it should not be
re-derived by a model every cycle at four calls a symbol.

So this module does the mechanical half deterministically and hands the committee a
comparison rather than a menu: here is the best candidate of each family, here is
whether the news points its way, and here is where the news and the chart disagree.

**It decides nothing.** No structure is chosen, none is removed, and the ranking is
untouched — `signal` and `Row.fit` are annotations. The judge still proposes and the
sixteen gates still dispose. What changes is that the judge argues against a table it
can check instead of an intuition it has to form.

**The conflict case is the reason this exists.** When the catalyst reads the news
bearish and the price trend reads bullish, every directional structure is a bet that
one of two disagreeing signals is the right one. The deterministic answer is that
neither has earned a direction, and saying so out loud is more useful than silently
scoring one of them slightly higher.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.strategy import burn
from halstreet.strategy import profiles as P
from halstreet.strategy.bias import BEARISH, BULLISH, NEUTRAL


def cand(kind: str, score: str = "0.5", name: str | None = None):
    from halstreet.strategy.candidates import Candidate
    return Candidate(name=name or f"a {kind}", kind=kind, legs=[],
                     net=Decimal("-1.00"), max_loss_usd=Decimal(400),
                     max_gain_usd=Decimal(100), dte=45, score=Decimal(score))


# --- the combined read ------------------------------------------------------------

def test_news_and_chart_agreeing_is_a_confirmed_direction():
    s = burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH)
    assert s.direction == BULLISH and s.agreement == burn.CONFIRMED


def test_news_and_chart_disagreeing_resolves_to_no_direction():
    """The case the whole module is for.

    Bearish news against a bullish trend is not a bearish signal at reduced
    confidence. It is two signals that cannot both be right, and taking a directional
    structure on it is picking one at random with money.
    """
    s = burn.signal(news=BEARISH, confidence=0.9, chart=BULLISH)
    assert s.direction == NEUTRAL and s.agreement == burn.CONFLICTED


def test_the_conflict_is_symmetric():
    a = burn.signal(news=BULLISH, confidence=0.9, chart=BEARISH)
    b = burn.signal(news=BEARISH, confidence=0.9, chart=BULLISH)
    assert a.agreement == b.agreement == burn.CONFLICTED


def test_a_quiet_tape_leaves_the_chart_to_speak_alone():
    s = burn.signal(news=NEUTRAL, confidence=0.9, chart=BULLISH)
    assert s.direction == BULLISH and s.agreement == burn.UNCONFIRMED


def test_a_directional_read_on_a_flat_chart_is_also_unconfirmed():
    s = burn.signal(news=BEARISH, confidence=0.9, chart=NEUTRAL)
    assert s.direction == BEARISH and s.agreement == burn.UNCONFIRMED


def test_an_unconfident_read_is_not_a_read_at_all():
    """The catalyst's own prompt says an honest shrug beats a confident guess.

    Below the floor the lean is discarded rather than downweighted. A 0.1-confidence
    "bearish" carries no more information than silence, and letting it flip a
    structure family means the news moves the trade on days it has nothing to say.
    """
    s = burn.signal(news=BEARISH, confidence=0.05, chart=BULLISH)
    assert s.direction == BULLISH and s.agreement == burn.UNCONFIRMED


def test_a_missing_catalyst_falls_back_to_the_chart_and_says_so():
    s = burn.signal(news=None, confidence=0.0, chart=BEARISH)
    assert s.direction == BEARISH and s.agreement == burn.NO_NEWS


def test_a_lean_the_catalyst_should_not_have_sent_is_ignored():
    """`Verdict.parse` already clamps this, so a surprise here means a new caller."""
    s = burn.signal(news="MOON", confidence=0.9, chart=BULLISH)
    assert s.direction == BULLISH


# --- the table --------------------------------------------------------------------

def test_every_family_on_the_menu_gets_a_row():
    rows = burn.table([cand(P.PUT_CREDIT), cand(P.CALL_CREDIT), cand(P.IRON_CONDOR)],
                      signal=burn.signal(news=NEUTRAL, confidence=0.0, chart=NEUTRAL))
    assert {r.kind for r in rows} == {P.PUT_CREDIT, P.CALL_CREDIT, P.IRON_CONDOR}


def test_a_family_the_menu_could_not_build_is_reported_as_absent_not_dropped():
    """"The chain offered no condor" and "a condor was never considered" differ.

    A judge reading a two-row table cannot tell which happened, and the difference
    matters: one is the market's answer and the other is a bug in the builder.
    """
    rows = burn.table([cand(P.PUT_CREDIT)],
                      signal=burn.signal(news=NEUTRAL, confidence=0.0, chart=NEUTRAL))
    absent = [r for r in rows if r.candidate is None]
    assert {r.kind for r in absent} == {P.CALL_CREDIT, P.IRON_CONDOR}


def test_the_best_scoring_candidate_of_each_family_is_the_one_shown():
    rows = burn.table([cand(P.PUT_CREDIT, "0.2", name="worse"),
                       cand(P.PUT_CREDIT, "0.9", name="better")],
                      signal=burn.signal(news=NEUTRAL, confidence=0.0, chart=NEUTRAL))
    row = next(r for r in rows if r.kind == P.PUT_CREDIT)
    assert row.candidate.name == "better"


def test_bullish_news_fits_the_structure_that_wants_the_tape_up():
    rows = burn.table([cand(P.PUT_CREDIT), cand(P.CALL_CREDIT)],
                      signal=burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH))
    fit = {r.kind: r.fit for r in rows}
    assert fit[P.PUT_CREDIT] == burn.FITS
    assert fit[P.CALL_CREDIT] == burn.AGAINST


def test_bearish_news_fits_the_structure_that_wants_the_tape_down():
    rows = burn.table([cand(P.PUT_CREDIT), cand(P.CALL_CREDIT)],
                      signal=burn.signal(news=BEARISH, confidence=0.9, chart=BEARISH))
    fit = {r.kind: r.fit for r in rows}
    assert fit[P.CALL_CREDIT] == burn.FITS
    assert fit[P.PUT_CREDIT] == burn.AGAINST


def test_no_direction_makes_the_condor_the_one_that_fits():
    rows = burn.table([cand(P.PUT_CREDIT), cand(P.CALL_CREDIT), cand(P.IRON_CONDOR)],
                      signal=burn.signal(news=NEUTRAL, confidence=0.0, chart=NEUTRAL))
    fit = {r.kind: r.fit for r in rows}
    assert fit[P.IRON_CONDOR] == burn.FITS
    assert fit[P.PUT_CREDIT] == fit[P.CALL_CREDIT] == burn.AMBIENT


def test_a_conflict_leaves_neither_directional_family_fitting():
    rows = burn.table([cand(P.PUT_CREDIT), cand(P.CALL_CREDIT), cand(P.IRON_CONDOR)],
                      signal=burn.signal(news=BEARISH, confidence=0.9, chart=BULLISH))
    fit = {r.kind: r.fit for r in rows}
    assert fit[P.PUT_CREDIT] == fit[P.CALL_CREDIT] == burn.AMBIENT
    assert fit[P.IRON_CONDOR] == burn.FITS


def test_the_fit_agrees_with_the_ranking_term_that_already_scores_direction():
    """Two definitions of "which way does this structure lean" would drift apart.

    `scoring.bias_fit` has scored exactly this since before the committee existed. The
    burn table must be a restatement of it, not a second opinion — if these ever
    disagree, the menu is ranked on one view of direction and argued on another.
    """
    from halstreet.strategy import scoring
    for direction in (BULLISH, BEARISH, NEUTRAL):
        sig = burn.signal(news=direction, confidence=0.9, chart=direction)
        for row in burn.table([cand(k) for k in P.VERTICALS_AND_CONDORS], signal=sig):
            score = scoring.bias_fit(row.kind, direction)
            assert (row.fit == burn.FITS) == (score == 1.0)
            assert (row.fit == burn.AGAINST) == (score == 0.0)


def test_the_table_is_ordered_fits_first_then_by_score():
    rows = burn.table([cand(P.PUT_CREDIT, "0.4"), cand(P.CALL_CREDIT, "0.9")],
                      signal=burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH))
    assert rows[0].kind == P.PUT_CREDIT


def test_an_absent_family_sorts_last_whatever_its_fit():
    rows = burn.table([cand(P.CALL_CREDIT, "0.1")],
                      signal=burn.signal(news=NEUTRAL, confidence=0.0, chart=NEUTRAL))
    assert rows[-1].candidate is None


def test_an_empty_menu_still_returns_a_full_table():
    """A cycle that built nothing has a reason worth showing, not a blank."""
    rows = burn.table([], signal=burn.signal(news=None, confidence=0.0, chart=NEUTRAL))
    assert len(rows) == len(P.VERTICALS_AND_CONDORS)
    assert all(r.candidate is None for r in rows)


# --- what the committee actually reads --------------------------------------------

def test_the_prompt_form_names_the_structure_the_fit_and_the_numbers():
    rows = burn.table([cand(P.PUT_CREDIT)],
                      signal=burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH))
    out = burn.to_prompt(rows)
    row = next(r for r in out["structures"] if r["kind"] == P.PUT_CREDIT)
    assert row["news_fit"] == burn.FITS
    assert row["max_loss_usd"] and row["score"]


def test_the_prompt_form_says_why_rather_than_only_what():
    """A verdict with no reason is a number the judge has to take on trust."""
    rows = burn.table([cand(P.CALL_CREDIT)],
                      signal=burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH))
    row = next(r for r in burn.to_prompt(rows)["structures"] if r["kind"] == P.CALL_CREDIT)
    assert row["why"]


def test_the_prompt_form_carries_the_conflict_where_it_cannot_be_missed():
    out = burn.to_prompt(burn.table(
        [cand(P.PUT_CREDIT)],
        signal=burn.signal(news=BEARISH, confidence=0.9, chart=BULLISH)))
    assert out["agreement"] == burn.CONFLICTED
    assert "disagree" in out["note"].lower()


def test_the_prompt_form_is_json_safe():
    """It is embedded in a prompt with `json.dumps`. A Decimal there raises."""
    import json
    json.dumps(burn.to_prompt(burn.table(
        [cand(P.PUT_CREDIT)],
        signal=burn.signal(news=BULLISH, confidence=0.9, chart=BULLISH))))


# --- the prose ----------------------------------------------------------------------
#
# `why` is read by three models and by whoever reads the journal afterwards. It came
# out of the first live run as "needs the tape does not fall and the read is bearish",
# which is two verb phrases welded together — one string was being used in a slot that
# needed the other grammatical form.

@pytest.mark.parametrize("direction", [BULLISH, BEARISH, NEUTRAL])
def test_no_row_explains_itself_ungrammatically(direction):
    """"needs/wants the tape" takes an infinitive; "profits while the tape" does not.

    One string was serving both slots, which reads correctly in the second and
    produces "needs the tape does not fall" in the first.
    """
    sig = burn.signal(news=direction, confidence=0.9, chart=direction)
    for row in burn.table([cand(k) for k in P.VERTICALS_AND_CONDORS], signal=sig):
        for verb in ("needs the tape", "wants the tape"):
            assert f"{verb} does" not in row.why, row.why


def test_the_structure_that_is_short_the_news_says_which_way_it_needed_the_tape():
    rows = burn.table([cand(P.PUT_CREDIT)],
                      signal=burn.signal(news=BEARISH, confidence=0.9, chart=BEARISH))
    why = next(r for r in rows if r.kind == P.PUT_CREDIT).why
    assert "not to fall" in why and "short the news" in why
