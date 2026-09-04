"""The judged deliverable, checked against the code it describes.

`docs/WRITEUP.md` is the one artifact a judge reads in full, and it is the only
description of this system that no test was watching. It drifted exactly as you would
expect: it counted fifteen gates against sixteen in three places, and had no idea the
agent had grown a committee, a news feed, an earnings calendar or a chart.

Prose cannot be pinned and should not be. What can be pinned is every load-bearing
*claim of fact* — a count, a table, a filename, a threshold — because those are what a
judge will check and what silently stops being true when the code moves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from halstreet.gates import ALL_GATES

WRITEUP = Path(__file__).resolve().parents[1] / "docs" / "WRITEUP.md"


@pytest.fixture(scope="module")
def text() -> str:
    return WRITEUP.read_text()


def _table_gates(text: str) -> list[str]:
    """The gate ids in the risk-gate table — the leading `code` cell of each row."""
    return re.findall(r"^\| `([a-z-]+)` \|", text, re.MULTILINE)


def test_the_gate_table_lists_every_gate_and_no_others(text):
    """The failure this file exists for.

    A gate added to the chain and not to the table is a safety layer the write-up
    does not claim to have; one in the table and not in the chain is a claim the code
    does not support. The second is worse, and neither announces itself.
    """
    assert set(_table_gates(text)) == {g.gate_name for g in ALL_GATES}


def test_the_stated_gate_count_matches_the_chain(text):
    """It said "Fifteen gates" for as long as there were fifteen, and then kept saying it.

    Written as a word, not a numeral, so no amount of grepping for "16" would have
    caught it — which is how it survived three separate appearances.

    This matches the *claim* shapes rather than the bare word, because the build log
    at the end has to be able to say what the count used to be. "Fifteen gates" as an
    assertion is the bug; "counted fifteen gates against sixteen" is the correction,
    and a check that cannot tell them apart forbids describing the mistake.
    """
    words = {13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
             17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty"}
    correct = words[len(ALL_GATES)]

    # Whitespace-normalized first: this is a hard-wrapped document, and two of these
    # claims had a line break inside them. Matching the raw text found three of five
    # and reported the other two as absent, which is the same failure the test is for.
    flat = " ".join(text.split())

    # Every place the document states the count as a fact about the current system.
    claims = re.findall(r"\*\*(\w+) gates\.", flat)                      # the headline
    claims += re.findall(r"all (\w+) (?:gate )?verdicts", flat)          # journal + panel
    claims += re.findall(r"the same (\w+) gates", flat)                  # the committee section
    claims += re.findall(r"case (\w+) deterministic gates", flat)        # the injection posture
    assert len(claims) >= 5, f"expected the count stated in at least 5 places, found {claims}"

    wrong = {c for c in claims if c.lower() != correct}
    assert not wrong, (
        f"the write-up claims {wrong} gates in {len(claims)} places where there are "
        f"{len(ALL_GATES)} ({correct})")


def test_every_row_in_the_table_says_what_it_rejects(text):
    # A gate row with an empty "Rejects" cell is a gate nobody can evaluate. The whole
    # table exists to answer "what would this have stopped".
    rows = re.findall(r"^\| `([a-z-]+)` \| ([^|]+) \| ([^|]+) \|", text, re.MULTILINE)
    assert len(rows) == len(ALL_GATES)
    for name, rule, rejects in rows:
        assert rule.strip(), f"{name} states no rule"
        assert rejects.strip(), f"{name} states nothing it rejects"


def test_the_test_count_is_not_stale(text):
    """A number a judge can check in one command, and the easiest one to leave behind.

    Held to the nearest fifty rather than exact: a write-up that must be edited on
    every green test run is a write-up that gets edited carelessly.
    """
    import subprocess
    out = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "tests", "--collect-only", "-q"],
        capture_output=True, text=True, cwd=WRITEUP.parents[1])
    actual = sum(int(m) for m in re.findall(r"^tests.*: (\d+)$", out.stdout, re.MULTILINE))
    if not actual:
        pytest.skip("could not collect the suite to compare against")
    claimed = [int(n) for n in re.findall(r"\b(\d{3,4}) tests\b", text)]
    assert claimed, "the write-up states no test count"
    assert any(abs(c - actual) <= 50 for c in claimed), \
        f"the write-up claims {claimed} tests; the suite has {actual}"


@pytest.mark.parametrize("subject", [
    "committee",      # four calls per underlying, the default proposal path
    "catalyst",       # the analyst that reads the tape
    "news",           # the one input a rules engine cannot derive
    "from-the-menu",  # the sixteenth gate
    "untrusted",      # the injection posture, stated rather than assumed
    "earnings",       # the event term that used to be a constant
])
def test_the_writeup_knows_about_the_agent_it_describes(subject, text):
    # Each of these is a system the agent has and the write-up did not mention once.
    # Not a prose check — a check that the subject appears at all.
    assert subject.lower() in text.lower(), f"the write-up never mentions {subject!r}"


def test_every_file_the_writeup_names_exists(text):
    """A judge following a path that is not there learns something about the rest of it."""
    root = WRITEUP.parents[1]
    named = set(re.findall(r"`((?:src|tests|scripts|docs|apps)/[\w./-]+\.\w+)`", text))
    named |= set(re.findall(r"`(\./start\.sh|install\.sh)`", text))
    missing = [n for n in named if not (root / n.lstrip("./")).exists()]
    assert not missing, f"the write-up names files that do not exist: {missing}"


def test_the_limits_it_quotes_are_the_defaults_the_code_ships(text):
    # A write-up quoting a 5% daily loss floor against a code default of 10% is worse
    # than one quoting nothing: it is a specific, checkable, wrong claim about a
    # safety limit.
    from halstreet.gates.base import Limits
    limits = Limits()
    assert f"{limits.daily_loss_limit_pct:g}%" in text, \
        f"the daily-loss floor is {limits.daily_loss_limit_pct:g}%; the write-up says otherwise"


def test_the_three_sections_the_judges_asked_for_are_present_in_their_order(text):
    # The brief named them: AI logic, risk gates, Alpaca infrastructure.
    heads = re.findall(r"^## (.+)$", text, re.MULTILINE)
    lowered = [h.lower() for h in heads]
    for wanted in ("ai logic", "risk gates", "alpaca infrastructure"):
        assert wanted in lowered, f"missing section: {wanted}"
    assert (lowered.index("ai logic") < lowered.index("risk gates")
            < lowered.index("alpaca infrastructure")), "the judges named an order"
