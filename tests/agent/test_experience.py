"""What the desk has learned from its own closed trades.

The agent already *tells the model* about past losses — `committee.reflection` puts
closed structures with their realized P&L in front of the judge. That is advice, and a
confident model can talk its way past advice. This is the deterministic half: a record
of which (underlying, family) pairs have been losing, computed from the ledger, that a
gate can refuse on.

Computed rather than stored, on purpose. The ledger is already the record of what
happened; a second file tracking streaks would be a second claim to keep in sync, and
the day they disagreed the agent would bench a pair that had just won.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from halstreet.agent.hippocampus.experience import benched_pairs
from halstreet.strategy.profiles import CALL_CREDIT, PUT_CREDIT

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)
TODAY = date(2026, 9, 1)
P750, P760 = "SPY261016P00750000", "SPY261016P00760000"
C770, C780 = "SPY261016C00770000", "SPY261016C00780000"


class _Closed:
    """The three fields this reads. Deliberately not the whole OpenStructure."""

    def __init__(self, underlying, legs, realized, *, hours_ago=1.0):
        self.underlying = underlying
        self.legs = legs
        self._realized = Decimal(str(realized))
        self.closed_at = (NOW - timedelta(hours=hours_ago)).isoformat()

    def realized(self):
        return self._realized


def _put(underlying="SPY", realized=-50, hours_ago=1.0):
    return _Closed(underlying, {P760: -1, P750: 1}, realized, hours_ago=hours_ago)


def _call(underlying="SPY", realized=-50, hours_ago=1.0):
    return _Closed(underlying, {C770: -1, C780: 1}, realized, hours_ago=hours_ago)


def bench(structures, after=2, days=1):
    return benched_pairs(structures, after=after, days=days, today=TODAY)


class TestWhenAPairIsBenched:
    def test_a_single_loss_is_not_a_pattern(self):
        assert bench([_put()]) == {}

    def test_the_configured_run_of_losses_benches_the_pair(self):
        out = bench([_put(hours_ago=3), _put(hours_ago=2)])
        assert ("SPY", PUT_CREDIT) in out
        assert "2 losing" in out[("SPY", PUT_CREDIT)]

    def test_a_win_clears_the_run(self):
        """The streak is consecutive, not cumulative. A pair that just worked is not a
        pair to stop trading, however badly it did last week."""
        out = bench([_put(hours_ago=4), _put(hours_ago=3), _put(realized=80, hours_ago=2)])
        assert out == {}

    def test_the_bench_lapses_once_the_window_passes(self):
        """A cooldown that never expires is a delisting. Two losses last week should
        not still be blocking the name — this system discovers its universe from the
        tape, and a permanent bench quietly shrinks the tradeable world every time it
        is wrong twice."""
        assert bench([_put(hours_ago=24 * 9), _put(hours_ago=24 * 8)]) == {}

    def test_the_window_is_measured_from_the_most_recent_loss(self):
        # Old loss, today's loss: the run is intact and the clock runs from the newer.
        out = bench([_put(hours_ago=24 * 9), _put(hours_ago=2)])
        assert ("SPY", PUT_CREDIT) in out

    def test_a_zero_day_window_rests_only_the_remainder_of_the_session(self):
        """`days=0` is not "off". It benches the pair for the rest of the day it lost
        on and releases it at the next session, which is the shortest cooldown that
        still means something."""
        today = bench([_put(hours_ago=3), _put(hours_ago=2)], days=0)
        assert ("SPY", PUT_CREDIT) in today
        yesterday = bench([_put(hours_ago=30), _put(hours_ago=26)], days=0)
        assert yesterday == {}

    def test_the_rule_is_turned_off_by_the_count_not_the_window(self):
        """`after=0` is the off switch, and it is checked before anything is walked."""
        assert bench([_put(hours_ago=3), _put(hours_ago=2)], after=0) == {}


class TestWhatTheBenchCovers:
    def test_families_on_one_underlying_are_tracked_apart(self):
        """Being wrong twice about calls says nothing about puts. Benching the whole
        symbol would throw away the half of the book that was never tested."""
        out = bench([_call(hours_ago=3), _call(hours_ago=2), _put(hours_ago=1)])
        assert ("SPY", CALL_CREDIT) in out
        assert ("SPY", PUT_CREDIT) not in out

    def test_underlyings_are_tracked_apart(self):
        out = bench([_put("SPY", hours_ago=3), _put("SPY", hours_ago=2),
                     _put("QQQ", hours_ago=1)])
        assert ("SPY", PUT_CREDIT) in out
        assert ("QQQ", PUT_CREDIT) not in out

    def test_a_trade_with_no_realized_figure_is_not_counted_as_a_loss(self):
        """Unknown is not a loss. A structure the ledger could not price yet would
        otherwise bench a pair on the strength of a number nobody has."""
        unknown = _put()
        unknown._realized = None
        assert bench([unknown, _put(hours_ago=2)]) == {}

    def test_breaking_even_is_not_a_loss(self):
        assert bench([_put(realized=0, hours_ago=3), _put(realized=0, hours_ago=2)]) == {}

    def test_an_unreadable_close_time_does_not_bench_forever(self):
        """A structure with no usable timestamp cannot have its cooldown expire, so it
        is not allowed to start one."""
        broken = _put(hours_ago=1)
        broken.closed_at = "not a date"
        assert bench([broken, _put(hours_ago=2)]) == {}


class TestTheRecordExplainsItself:
    def test_the_reason_names_the_count_and_when_it_lifts(self):
        out = bench([_put(hours_ago=3), _put(hours_ago=2)])
        reason = out[("SPY", PUT_CREDIT)]
        assert "SPY" in reason and "put_credit_spread" in reason
        assert "$100.00" in reason        # the two losses, summed
        assert "Resting until" in reason
