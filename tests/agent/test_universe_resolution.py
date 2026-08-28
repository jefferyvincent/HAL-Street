"""Where the universe comes from — the one setting this change is really about.

`UNIVERSE=SPY,QQQ,IWM` was a list of three tickers a person typed, and typing it was
the only reason those three. The setting still exists and still pins exactly what it
says; what is new is that it does not have to say anything, and `auto` hands the
choice to `Agent.discover`.

Three properties matter here and none of them is about discovery itself:

  * **An explicit list is still obeyed exactly.** Anyone judging a run, reproducing a
    result, or debugging one name needs to be able to nail the universe down. A
    discovery mode that could not be turned off would make every run unrepeatable.
  * **Auto is re-resolved every pass, not once at startup.** A universe fixed at 09:30
    from the overnight tape is a hardcoded list with extra steps by 15:00.
  * **An empty discovery is an empty scan, not a fallback to something.** Silently
    substituting yesterday's names, or a built-in default, would mean the agent
    trades a universe nobody chose on exactly the cycles where the evidence for it is
    missing.
"""

from __future__ import annotations

import pytest

from halstreet.agent.run import AUTO, universe_from_env


@pytest.mark.parametrize("raw,expected", [
    ("SPY,QQQ,IWM", ["SPY", "QQQ", "IWM"]),
    ("spy, qqq ", ["SPY", "QQQ"]),
    ("SPY", ["SPY"]),
])
def test_an_explicit_list_is_taken_exactly_as_written(raw, expected):
    assert universe_from_env({"UNIVERSE": raw}) == expected


@pytest.mark.parametrize("raw", ["auto", "AUTO", " Auto ", ""])
def test_auto_and_silence_both_mean_let_the_agent_choose(raw):
    """Empty means auto too.

    The alternative is falling back to a built-in list, which is how a shipped
    default becomes three tickers nobody remembers choosing — which is the thing
    being removed.
    """
    assert universe_from_env({"UNIVERSE": raw}) == []


def test_a_missing_setting_means_auto():
    assert universe_from_env({}) == []


def test_auto_mixed_into_a_list_is_refused_rather_than_half_honoured():
    """"SPY,auto" cannot mean both. Guessing which half wins is worse than refusing.

    Raising here is safe: this runs once at startup, before any broker call, and a
    universe the operator did not mean is the kind of mistake that is only visible
    afterwards in the journal.
    """
    with pytest.raises(ValueError, match="auto"):
        universe_from_env({"UNIVERSE": "SPY,auto"})


def test_the_sentinel_is_the_word_the_operator_actually_types():
    assert AUTO == "auto"
