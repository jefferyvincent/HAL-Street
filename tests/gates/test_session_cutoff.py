"""Do not open what the close is about to shut.

The flatten rule means every position is closed before the bell. Without a matching
entry rule the agent spends the last half hour opening spreads it will pay to unwind
minutes later — two crossings of the spread bought for no holding period at all.

Fail-closed like every gate here: an unknown time to close is not an open session.
"""
from datetime import date

from halstreet.gates.base import GateContext, Limits
from halstreet.gates.circuit import session_cutoff

from .conftest import leg, proposal


def _ctx(minutes, *, cutoff=45):
    return GateContext(account={}, limits=Limits(entry_cutoff_minutes=cutoff),
                       asof=date(2026, 9, 1), minutes_to_close=minutes)


def test_an_entry_well_before_the_close_passes():
    assert session_cutoff(proposal(leg(770)), _ctx(180)).passed


def test_an_entry_inside_the_cutoff_is_rejected():
    result = session_cutoff(proposal(leg(770)), _ctx(30))
    assert not result.passed
    assert "30" in result.reason


def test_an_unknown_time_to_close_fails_closed():
    """Every other gate here reads a missing input as a reason to refuse. A session
    whose end nobody could establish is exactly when not to open a short option."""
    result = session_cutoff(proposal(leg(770)), _ctx(None))
    assert not result.passed


def test_no_cutoff_configured_lets_everything_through():
    """Off by default. A gate that starts refusing the moment it is added is a gate
    that changes behaviour without anyone choosing it."""
    assert session_cutoff(proposal(leg(770)), _ctx(5, cutoff=None)).passed
