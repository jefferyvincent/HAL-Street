"""Reading an option chain, and picking strikes out of it.

These functions decide which contracts a verification run builds its structures from,
and they lived in `scripts/verify_multileg.py` where nothing could reach them. The
script's whole reason for existing is that nobody knew what shape Alpaca's OptionChain
would come back in — so the one part of it that handles that uncertainty was the last
part that should have been untestable.

`contracts_from_chain` is checked against every shape it claims to handle, because a
shape it silently returns [] for is reported to the operator as "no contracts listed"
rather than "I did not recognise this response".
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from halstreet import clock
from halstreet.execution import chain_pick

TODAY = date(2026, 8, 28)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    # Expiry selection is relative to today, so the answers move unless the day does
    # not. Article III: ask the clock, and in a test pin the clock.
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def sym(expiry: date, right: str, strike: str, root: str = "SPY") -> str:
    return f"{root}{expiry:%y%m%d}{right}{int(Decimal(strike) * 1000):08d}"


NEAR = TODAY + timedelta(days=3)     # inside the one-week floor
MID = TODAY + timedelta(days=45)
FAR = TODAY + timedelta(days=75)

CHAIN = [
    sym(NEAR, "C", "760"),
    sym(MID, "C", "755"), sym(MID, "C", "760"), sym(MID, "C", "765"),
    sym(MID, "P", "745"), sym(MID, "P", "750"),
    sym(FAR, "C", "760"), sym(FAR, "C", "770"),
]


# --- contracts_from_chain: the shapes -----------------------------------------


def test_a_snapshots_map_is_read_by_key():
    payload = {"snapshots": {CHAIN[1]: {"latestQuote": {}}, CHAIN[2]: {}}}
    assert chain_pick.contracts_from_chain(payload) == sorted([CHAIN[1], CHAIN[2]])


@pytest.mark.parametrize("key", ["option_chain", "chain", "data", "results"])
def test_a_wrapped_list_of_objects_is_read_by_symbol(key):
    payload = {key: [{"symbol": CHAIN[2]}, {"symbol": CHAIN[1]}]}
    assert chain_pick.contracts_from_chain(payload) == sorted([CHAIN[1], CHAIN[2]])


def test_a_bare_list_of_objects_is_read_by_symbol():
    assert chain_pick.contracts_from_chain([{"symbol": CHAIN[1]}]) == [CHAIN[1]]


def test_a_bare_map_of_symbols_is_accepted_only_if_the_keys_parse():
    """Confirmed by parsing, not by assuming.

    A five-key dict whose keys are not OCC symbols is some other response entirely,
    and returning its keys as "contracts" would send strike selection looking for
    strikes in the word "status".
    """
    assert chain_pick.contracts_from_chain({CHAIN[1]: {}, CHAIN[2]: {}}) == sorted(CHAIN[1:3])
    assert chain_pick.contracts_from_chain({"status": "ok", "count": 2}) == []


@pytest.mark.parametrize("payload", [None, "text", 3, {}, [], [{"no_symbol": 1}]])
def test_an_unrecognised_shape_yields_no_contracts(payload):
    # The caller prints the payload's type and keys and stops. That branch is the one
    # the verification script exists to surface, so it must be reachable.
    assert chain_pick.contracts_from_chain(payload) == []


# --- pick_expiry --------------------------------------------------------------


def test_the_expiry_closest_to_the_target_wins():
    assert chain_pick.pick_expiry(CHAIN, 45) == MID
    assert chain_pick.pick_expiry(CHAIN, 75) == FAR


def test_an_expiry_inside_a_week_is_never_chosen():
    """Even when it is by far the closest to the target.

    A contract expiring in three days has a fill profile that says nothing about the
    structures the agent actually opens, and asking for --dte 3 should not quietly
    get you one.
    """
    assert chain_pick.pick_expiry(CHAIN, 1) == MID


def test_the_floor_is_inclusive_at_exactly_seven_days():
    on_the_floor = TODAY + timedelta(days=chain_pick.EXPIRY_FLOOR_DAYS)
    assert chain_pick.pick_expiry([sym(on_the_floor, "C", "760")], 7) == on_the_floor


def test_no_listed_expiry_far_enough_out_returns_none():
    # None, not "the nearest one anyway" — the caller reports it and stops.
    assert chain_pick.pick_expiry([sym(NEAR, "C", "760")], 45) is None
    assert chain_pick.pick_expiry([], 45) is None


def test_symbols_that_are_not_options_are_ignored_rather_than_raising():
    assert chain_pick.pick_expiry(["SPY", "", "GARBAGE", *CHAIN], 45) == MID


# --- strikes_for / expiries_after / nearest -----------------------------------


def test_strikes_are_filtered_by_expiry_and_right_and_sorted():
    assert chain_pick.strikes_for(CHAIN, MID, "C") == [Decimal(755), Decimal(760),
                                                       Decimal(765)]
    assert chain_pick.strikes_for(CHAIN, MID, "P") == [Decimal(745), Decimal(750)]
    assert chain_pick.strikes_for(CHAIN, FAR, "P") == []


def test_expiries_after_returns_only_later_contracts():
    later = chain_pick.expiries_after(CHAIN, MID)
    assert set(later) == {CHAIN[6], CHAIN[7]}
    assert chain_pick.expiries_after(CHAIN, FAR) == []


def test_nearest_picks_the_closest_listed_strike():
    strikes = [Decimal(745), Decimal(750), Decimal(760)]
    assert chain_pick.nearest(strikes, Decimal(758)) == Decimal(760)
    assert chain_pick.nearest(strikes, Decimal(744)) == Decimal(745)
    assert chain_pick.nearest(strikes, Decimal(750)) == Decimal(750)


def test_a_tie_goes_to_the_lower_strike_rather_than_to_list_order():
    """An exact midpoint has two right answers and needs one of them, every time.

    Without the tie-break the winner is whichever came first out of a set, and the
    structure a verification run builds changes between runs on the same chain.
    """
    strikes = [Decimal(760), Decimal(750)]
    assert chain_pick.nearest(strikes, Decimal(755)) == Decimal(750)
    assert chain_pick.nearest(sorted(strikes), Decimal(755)) == Decimal(750)


def test_the_module_uses_the_one_occ_parser():
    """The duplicate this file exists to have deleted.

    `verify_multileg.py` carried its own parse_occ under a comment saying the real one
    should be ported into marketdata/. The port landed; the copy stayed. A second
    parser is a second answer to "is this an option", and they drift.
    """
    import inspect

    source = inspect.getsource(chain_pick)
    assert "def parse_occ" not in source
    assert "occ_mod.parse" in source
