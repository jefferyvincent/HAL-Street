"""The structure chart: the panel's one route that reaches the broker.

Two properties matter here and both are easy to lose later. The chart's three lines
must come from the same rule the exit policy applies — a picture that disagrees with
the behaviour is worse than no picture, because it is believed. And the route must
only be able to ask about structures this agent actually traded, or a read-only
dashboard has quietly become a general market-data proxy.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from halstreet.agent.cerebellum.manager import ExitPolicy, exit_levels
from halstreet.agent.hippocampus.ledger import Ledger, OpenStructure
from halstreet.telemetry import server, structure_chart

SHORT, LONG = "QQQ261016C00755000", "QQQ261016C00765000"


def structure(entry: Decimal | None = Decimal("-1.60")) -> OpenStructure:
    return OpenStructure(
        structure_id="s1", name="755/765 call credit spread", underlying="QQQ", qty=1,
        legs={SHORT: -1, LONG: 1}, opened_at="2026-08-26T16:42:38+00:00",
        entry_price=entry, order_id="o1",
    )


def bars(**series: list[tuple[str, str]]) -> dict[str, list[dict]]:
    return {sym: [{"t": t, "c": c} for t, c in rows] for sym, rows in series.items()}


# --- the net, not a leg ------------------------------------------------------------

def test_the_series_is_the_structures_own_price():
    """A spread's price is the signed sum of its legs, on the same convention the exit
    uses: negative means it is held for a credit."""
    got = structure_chart.net_series(structure(), bars(
        **{SHORT: [("2026-08-26T13:00:00Z", "4.96")], LONG: [("2026-08-26T13:00:00Z", "3.36")]}
    ))
    assert [(p.t, p.value) for p in got] == [("2026-08-26T13:00:00Z", Decimal("-1.60"))]


def test_a_timestamp_missing_from_one_leg_is_dropped():
    """`mark_structure` refuses to act on a partial mark; the chart holds the same line.

    Drawing the bars that did arrive would put dips in the line that are an absent
    quote rather than a price, and nothing on the chart would say which.
    """
    got = structure_chart.net_series(structure(), bars(**{
        SHORT: [("13:00", "4.96"), ("14:00", "5.10")],
        LONG: [("13:00", "3.36")],
    }))
    assert [p.t for p in got] == ["13:00"]


def test_no_bars_at_all_is_an_empty_series_not_a_crash():
    assert structure_chart.net_series(structure(), {}) == []


# --- the lines are the policy ------------------------------------------------------

def test_the_levels_come_from_the_exit_policy_itself():
    policy = ExitPolicy()
    built = structure_chart.build(structure(), {}, policy)
    expected = exit_levels(Decimal("-1.60"), policy)
    assert built["levels"] == expected.to_prompt()
    assert built["levels"]["target"] == str(Decimal("-1.60") * Decimal("0.5"))


def test_an_unknown_entry_price_draws_no_levels_rather_than_guessing():
    built = structure_chart.build(structure(entry=None), {}, ExitPolicy())
    assert built["levels"] is None


def test_the_policy_travels_with_the_chart():
    """So the panel can say what the target *means*, not just where it is."""
    built = structure_chart.build(structure(), {}, ExitPolicy())
    assert built["policy"]["take_profit_pct"] == "50"
    assert built["policy"]["force_close_dte"] == 5


def test_a_provisional_price_is_flagged_as_one():
    """The panel must be able to distinguish a fill from the limit standing in for it."""
    built = structure_chart.build(structure(), {}, ExitPolicy())
    assert built["entry_filled"] is False


# --- the route can only ask about our own book -------------------------------------

def test_only_structures_in_the_ledger_can_be_charted(tmp_path):
    """The symbols come from the ledger, never from the caller.

    That is what keeps this from being a general market-data proxy behind a read-only
    dashboard: the panel cannot name a contract, only a structure the agent opened.
    """
    ledger = Ledger(path=tmp_path / "ledger.json", structures=[structure()])
    assert structure_chart.find(ledger, "s1") is not None
    assert structure_chart.find(ledger, "QQQ261016C00755000") is None
    assert structure_chart.find(ledger, "../../etc/passwd") is None


def test_the_chart_route_is_a_get_like_every_other():
    from fastapi.routing import APIRoute

    route = next(r for r in server.app.routes
                 if isinstance(r, APIRoute) and "chart" in r.path)
    assert route.methods <= {"GET", "HEAD"}


@pytest.mark.parametrize("field", ["series", "levels", "policy", "legs"])
def test_the_payload_carries_what_the_panel_draws(field):
    assert field in structure_chart.build(structure(), {}, ExitPolicy())


# --- candles ----------------------------------------------------------------------

def test_a_candle_is_built_from_the_observed_net_not_from_the_legs():
    """The trap this exists to avoid.

    A spread's high is not the sum of its legs' highs. The legs move together, so
    when the short leg prints its high the long one usually has too, and the net
    range is a fraction of the summed one. Adding signed highs would draw a body
    and wicks spanning prices the structure was never at — a chart that looks more
    informative and is less true.

    Every value in a candle here is one of the net points it was given.
    """
    from halstreet.telemetry.structure_chart import Point, net_candles

    points = [Point(t=f"2026-08-27T{h:02d}:00:00Z", value=v)
              for h, v in [(13, Decimal("-1.36")), (14, Decimal("-1.20")),
                           (15, Decimal("-1.64")), (16, Decimal("-1.59"))]]
    candle = net_candles(points)[0]
    seen = {p.value for p in points}
    assert {candle["o"], candle["h"], candle["l"], candle["c"]} <= seen
    assert candle["o"] == Decimal("-1.36"), "the session's first observation"
    assert candle["c"] == Decimal("-1.59"), "and its last"
    assert candle["h"] == Decimal("-1.20") and candle["l"] == Decimal("-1.64")


def test_one_candle_per_session():
    from halstreet.telemetry.structure_chart import Point, net_candles

    points = [Point(t="2026-08-26T14:00:00Z", value=Decimal("-1.0")),
              Point(t="2026-08-26T18:00:00Z", value=Decimal("-1.2")),
              Point(t="2026-08-27T14:00:00Z", value=Decimal("-1.3"))]
    candles = net_candles(points)
    assert [c["t"][:10] for c in candles] == ["2026-08-26", "2026-08-27"]


def test_a_gap_produces_no_candle_rather_than_a_wide_one():
    # A weekend is an absence of trading, not a long session. Bucketing by date
    # keeps the axis honest across it.
    from halstreet.telemetry.structure_chart import Point, net_candles

    points = [Point(t="2026-08-28T14:00:00Z", value=Decimal("-1.0")),
              Point(t="2026-08-31T14:00:00Z", value=Decimal("-1.4"))]
    assert len(net_candles(points)) == 2


def test_a_single_observation_is_a_flat_candle():
    from halstreet.telemetry.structure_chart import Point, net_candles

    candle = net_candles([Point(t="2026-08-27T14:00:00Z", value=Decimal("-1.5"))])[0]
    assert candle["o"] == candle["h"] == candle["l"] == candle["c"] == Decimal("-1.5")


def test_no_points_means_no_candles():
    from halstreet.telemetry.structure_chart import net_candles
    assert net_candles([]) == []


def test_the_bar_size_follows_the_window():
    """A fixed hourly bar is wrong at both ends.

    Over a two-day window it yields a dozen points, and a candle needs several
    observations to have a body at all — an hour-old position drew three flat ones.
    Over two months it yields hundreds, which is a smudge.
    """
    from halstreet.telemetry.structure_chart import resolution

    assert resolution(1)[0] == "15Min"
    assert resolution(12)[0] == "1Hour"
    assert resolution(60)[0] == "1Day"
    # And the bucket moves with it, so the candle count stays in a readable band.
    assert resolution(1)[1] == 13, "grouped by hour"
    assert resolution(12)[1] == 10, "grouped by session"


def test_candles_group_by_hour_at_the_finest_resolution():
    from halstreet.telemetry.structure_chart import Point, net_candles

    points = [Point(t=f"2026-08-27T14:{m:02d}:00Z", value=Decimal(f"-1.{m}"))
              for m in (15, 30, 45)]
    points.append(Point(t="2026-08-27T15:00:00Z", value=Decimal("-1.9")))
    assert len(net_candles(points, bucket=13)) == 2
    assert len(net_candles(points, bucket=10)) == 1, "same points, grouped by date"


def test_the_lead_in_scales_with_how_long_the_position_has_been_held():
    """A flat month before the open buried a fresh position in prehistory.

    Measured on a live QQQ spread opened that morning: the candles spanned -3.84 to
    -0.50 while the position had traded between -1.0 and -1.7. Four fifths of the
    chart was what those two contracts cost as a pair before anyone held them.
    """
    from datetime import UTC, datetime, timedelta

    from halstreet.telemetry.structure_chart import MIN_LEAD_IN_DAYS, start_of_window

    def opened(days_ago: float) -> OpenStructure:
        when = datetime.now(UTC) - timedelta(days=days_ago)
        return OpenStructure(structure_id="s", name="n", underlying="QQQ", qty=1,
                             legs={}, opened_at=when.isoformat())

    fresh = datetime.strptime(start_of_window(opened(0)), "%Y-%m-%d").replace(tzinfo=UTC)
    lead = (datetime.now(UTC) - fresh).total_seconds() / 86400
    assert MIN_LEAD_IN_DAYS <= lead < MIN_LEAD_IN_DAYS + 1.5, lead

    # A month-old position gets about a week, not another month.
    old = datetime.strptime(start_of_window(opened(30)), "%Y-%m-%d").replace(tzinfo=UTC)
    before_open = 30 - (datetime.now(UTC) - old).total_seconds() / 86400
    assert 5 <= -before_open <= 10, -before_open


def test_the_lead_in_is_never_unbounded():
    from datetime import UTC, datetime, timedelta

    from halstreet.telemetry.structure_chart import LOOKBACK_DAYS, start_of_window

    ancient = OpenStructure(structure_id="s", name="n", underlying="QQQ", qty=1, legs={},
                            opened_at=(datetime.now(UTC) - timedelta(days=900)).isoformat())
    start = datetime.strptime(start_of_window(ancient), "%Y-%m-%d").replace(tzinfo=UTC)
    before_open = 900 - (datetime.now(UTC) - start).total_seconds() / 86400
    assert -before_open <= LOOKBACK_DAYS + 1


def test_the_newest_candle_is_marked_while_its_bucket_is_open():
    """Otherwise the newest candle is indistinguishable from a closed one.

    A reader has no way to tell a finished hour from four minutes of it — which is
    the difference between a shape that means something and one that is about to
    change. The panel draws this one hollow and moves it with the live mark.
    """
    from datetime import UTC, datetime, timedelta

    from halstreet.telemetry.structure_chart import Point, net_candles

    now = datetime.now(UTC)
    points = [
        Point(t=(now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
              value=Decimal("-1.2")),
        Point(t=now.strftime("%Y-%m-%dT%H:%M:%SZ"), value=Decimal("-1.5")),
    ]
    candles = net_candles(points, bucket=13)
    assert [c["forming"] for c in candles] == [False, True]


def test_history_alone_has_no_forming_candle():
    from halstreet.telemetry.structure_chart import Point, net_candles

    points = [Point(t="2020-01-02T14:00:00Z", value=Decimal("-1.0")),
              Point(t="2020-01-03T14:00:00Z", value=Decimal("-1.1"))]
    assert not any(c["forming"] for c in net_candles(points, bucket=13))


def test_forming_is_decided_at_the_bucket_the_candle_is_grouped_by(monkeypatch):
    """Grouped by date, today's candle is forming all day; grouped by hour, only this
    hour's is. The flag has to follow whatever the bucket actually is.

    The clock is pinned rather than read. This test used to take `now() - 4h` and
    assert that stamp was still "today", which is true for twenty hours out of every
    twenty-four and false for the four after UTC midnight — a test that passed all
    afternoon and failed at 00:01Z. A test of "the bucket the clock is in" has to own
    the clock, or the only thing it measures is what time the suite happened to run.
    """
    from datetime import UTC, datetime

    from halstreet.telemetry import structure_chart
    from halstreet.telemetry.structure_chart import Point, net_candles

    pinned = datetime(2026, 3, 5, 18, 30, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return pinned

    monkeypatch.setattr(structure_chart, "datetime", Clock)

    # Four hours earlier: a different hour, the same session.
    points = [Point(t="2026-03-05T14:30:00Z", value=Decimal("-1.0"))]
    assert net_candles(points, bucket=13)[0]["forming"] is False, "a closed hour"
    assert net_candles(points, bucket=10)[0]["forming"] is True, "but today's session"

    # And the hour the clock is actually in is forming under either bucket.
    current = [Point(t="2026-03-05T18:00:00Z", value=Decimal("-1.0"))]
    assert net_candles(current, bucket=13)[0]["forming"] is True
    assert net_candles(current, bucket=10)[0]["forming"] is True


def test_the_forming_flag_survives_serialisation_as_a_boolean():
    """`str(False)` is "False", which is truthy in Python and in JavaScript.

    The payload stringified every field but the timestamp, so the flag arrived as a
    non-empty string and every candle read as still forming — the panel would have
    drawn the entire chart hollow. Prices are strings because they are Decimals and
    a float would be a different number; a boolean is neither.
    """
    from datetime import UTC, datetime, timedelta

    from halstreet.telemetry.structure_chart import build

    now = datetime.now(UTC)
    structure = OpenStructure(
        structure_id="s", name="n", underlying="QQQ", qty=1,
        legs={SHORT: -1}, opened_at=(now - timedelta(days=1)).isoformat(),
        entry_price=Decimal("-1.50"))
    bars = {SHORT: [
        {"t": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"), "c": 1.2},
        {"t": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "c": 1.5},
    ]}
    payload = build(structure, bars, ExitPolicy(), bucket=13)
    flags = [c["forming"] for c in payload["candles"]]
    assert all(isinstance(f, bool) for f in flags), flags
    assert flags.count(True) == 1, "exactly one bucket is open"
    # And the prices stay strings, because a Decimal through a float is a different
    # number and this payload is what the chart is drawn from.
    assert all(isinstance(c["o"], str) for c in payload["candles"])


# --- choosing the bar size --------------------------------------------------------

def test_a_requested_bar_size_is_honoured():
    from halstreet.telemetry.structure_chart import chosen

    assert chosen("5Min", days=30) == ("5Min", 13)
    assert chosen("1Day", days=1) == ("1Day", 10)


def test_no_request_falls_back_to_the_window():
    from halstreet.telemetry.structure_chart import chosen, resolution

    assert chosen(None, days=2) == resolution(2)
    assert chosen("", days=40) == resolution(40)


def test_an_unknown_bar_size_gives_the_right_chart_rather_than_an_error():
    """This is a query string on a read-only route.

    A typo should draw the chart the window suggests, not return a 400 to someone
    who only wanted to look at a position.
    """
    from halstreet.telemetry.structure_chart import chosen, resolution

    assert chosen("5Sec", days=3) == resolution(3)
    assert chosen("../etc/passwd", days=3) == resolution(3)


def test_nothing_sub_minute_is_offered():
    """Alpaca does not serve it, and an option would not fill it.

    A five-second series on a 45-DTE index spread is mostly gaps, and a chart of
    gaps is worse than a coarser one that is continuous.
    """
    from halstreet.telemetry.structure_chart import OFFERED

    assert not any(unit in tf for tf in OFFERED for unit in ("Sec", "sec"))
    assert set(OFFERED) == {"1Min", "5Min", "15Min", "1Hour", "1Day"}


def test_every_offered_bar_size_carries_a_bucket_that_matches_it():
    # A minute bar grouped by date would be one candle from four hundred points.
    from halstreet.telemetry.structure_chart import OFFERED

    for name, (bar, bucket) in OFFERED.items():
        assert bar == name
        assert bucket == (10 if name in ("1Hour", "1Day") else 13), name
