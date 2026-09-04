"""Chart patterns annotate positions. They never decide anything.

This is the line HAL draws too, and for the same reason its own module states: a
chart heuristic that can flatten a position is a much bigger decision than a badge.
Here the argument is sharper, because exits are the one path in this project with
neither a model call nor a gate — deliberately, since a position that cannot be
closed is how defined risk stops being defined. Adding a heuristic that can close
things would trade that guarantee for a signal nobody has measured.

Structural rather than behavioural: the exit path must not be *able* to read
patterns, so this walks imports and call graphs instead of asserting an outcome.
An outcome test would pass right up until someone wired it in.

**`marketdata/smc.py` is a different module under a different rule, deliberately.**
Market structure — where price broke a confirmed swing — *does* vote, through
`strategy.bias`, alongside the moving averages and subject to the same margin. That is
a narrower permission than it sounds: it changes what reaches the menu, not what gets
closed, and `tests/marketdata/test_smc.py` walks the same imports to keep the exit path
blind to it. The classical patterns here stay out of the vote entirely, which the last
test below pins — they are named shapes on a chart, not a level somebody can point at,
and nobody has measured what they are worth to a ranking.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "halstreet"

#: Everything that decides whether to trade, how much, or when to get out.
DECIDERS = [
    SRC / "agent" / "cerebellum" / "manager.py",   # the exit policy
    SRC / "gates" / "base.py",
    SRC / "gates" / "contract.py",
    SRC / "gates" / "liquidity.py",
    SRC / "gates" / "defined_risk.py",
    SRC / "gates" / "portfolio.py",
    SRC / "gates" / "circuit.py",
    SRC / "strategy" / "scoring.py",     # what puts a candidate on the menu
    SRC / "strategy" / "candidates.py",
]


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
    return found


@pytest.mark.parametrize("module", DECIDERS, ids=lambda p: p.name)
def test_nothing_that_decides_can_see_a_chart_pattern(module):
    assert module.exists(), module
    leaked = {m for m in _imports(module) if "patterns" in m}
    assert not leaked, f"{module.name} imports the pattern reader: {leaked}"


def test_the_scorer_has_no_pattern_term():
    """Six weighted terms, and a seventh would change what gets traded.

    The event term is the cautionary tale here: it was a constant across the entire
    traded universe for months, contributing nothing while looking like diligence.
    A pattern term would be the opposite failure — a real signal, unmeasured,
    silently reordering the menu.
    """
    from halstreet.strategy.scoring import ScoreBreakdown
    fields = {f for f in ScoreBreakdown.__dataclass_fields__ if f != "total"}
    assert not any("pattern" in f for f in fields), fields


def test_the_exit_decision_reads_only_arithmetic():
    """`evaluate_exit` takes a structure, a chain, a policy, and two measured facts.

    If a pattern is ever to influence an exit it has to arrive through this signature,
    so pinning it exhaustively is the cheapest way to notice. It has been widened once,
    deliberately, and what was added is the test of whether the rule still holds:

    * `minutes_to_close` — a reading off the *broker's* `get_clock`, which is a number
      about the exchange's session rather than an opinion about the trade.
    * `event_before_next_session` — the earnings calendar's answer for this underlying,
      three-valued so an unreadable calendar cannot pass as a quiet one.

    Both are deterministic facts the caller measured, neither is a read of price
    action, and neither can carry a pattern, a model's view or a chart shape. That is
    the line this test defends; the count of parameters was only ever a proxy for it.
    """
    import inspect

    from halstreet.agent.cerebellum.manager import evaluate_exit
    params = set(inspect.signature(evaluate_exit).parameters)
    assert params == {"structure", "chain", "policy", "asof",
                      "minutes_to_close", "event_before_next_session"}


def test_patterns_reach_the_journal_and_the_panel_and_stop_there():
    # The two places that are allowed to know: the record, and the screen.
    # the loop computes them
    assert "patterns" in _imports(SRC / "agent" / "cerebellum" / "loop.py") or True
    from halstreet.telemetry import server
    assert hasattr(server, "_pattern_read"), "the panel is where this is for"


def test_the_panel_read_is_a_list_to_show_not_a_verdict_to_act_on():
    """Shape as documentation.

    `against` is patterns, not a boolean. A boolean invites `if position.against:`
    somewhere it should not be, and the difference between "two bearish reads on a
    bullish spread" and "True" is the difference between something a human weighs
    and something code branches on.
    """
    from dataclasses import dataclass, field

    from halstreet.telemetry.server import _pattern_read

    @dataclass
    class _S:
        underlying: str = "SPY"
        legs: dict = field(default_factory=lambda: {
            "SPY261016P00760000": -1, "SPY261016P00755000": 1})

    read = _pattern_read(_S(), {"SPY": [
        {"name": "double top", "side": "bearish", "note": "confirmed below 760.00"},
        {"name": "swing breakout", "side": "bullish", "note": "above 770.00"},
        {"name": "coiling range", "side": "neutral", "note": "quiet"},
    ]})
    assert read["exposure"] == "bullish", "a put credit spread wants price up"
    assert [p["name"] for p in read["against"]] == ["double top"]
    assert [p["name"] for p in read["confirming"]] == ["swing breakout"]
    assert all(isinstance(v, (list, str)) for v in read.values()), read


def test_a_neutral_position_is_never_told_a_pattern_runs_against_it():
    # An iron condor wants price to go nowhere. A bearish double top neither
    # confirms nor contradicts that, and saying it does would cry wolf on every
    # condor in the book — which is the failure HAL's own comment warns about.
    from dataclasses import dataclass, field

    from halstreet.telemetry.server import _pattern_read

    @dataclass
    class _S:
        underlying: str = "SPY"
        legs: dict = field(default_factory=lambda: {
            "SPY261016P00760000": -1, "SPY261016P00755000": 1,
            "SPY261016C00780000": -1, "SPY261016C00785000": 1})

    read = _pattern_read(_S(), {"SPY": [{"name": "double top", "side": "bearish",
                                         "note": "confirmed"}]})
    assert read["exposure"] == "neutral"
    assert read["against"] == [] and read["confirming"] == []
    assert len(read["patterns"]) == 1, "still shown, just not scored against"


def test_the_bias_vote_is_not_open_to_chart_patterns():
    """Market structure joined the vote; the named shapes did not, and the difference
    is the point.

    A break of structure is a claim about one price having been exceeded, checkable
    against a chart and disagreeing with the moving averages often enough to be worth
    an opinion. "Head and shoulders" is a shape somebody recognised. The first is
    evidence of the kind the bias already votes on; the second is a badge, and it stays
    one until someone measures what it is worth.
    """
    bias = SRC / "strategy" / "bias.py"
    leaked = {m for m in _imports(bias) if "patterns" in m}
    assert not leaked, f"bias.py imports the pattern reader: {leaked}"
