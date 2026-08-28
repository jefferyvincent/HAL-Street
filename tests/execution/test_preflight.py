"""The eligibility checks for the judged account.

These had no test at all while they lived in `scripts/preflight.py`, because a file
that is not importable is a file that cannot be asserted on — which is the point of
the move. What they decide is not a small thing: a pass here is the sentence "this
account is eligible", and the competition disqualifies a project run on a reused one.

The case each of these exists for is the fourth one down. Every list-ish endpoint here
can come back in a shape nobody has seen, and the difference between "no positions"
and "I could not read the positions" is the difference between a clean account and a
disqualification nobody noticed.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from halstreet.execution import preflight


def _account(**over):
    """A judged account that passes everything, so each test can break one thing."""
    acct = {
        "id": "acct-fresh-1",
        "account_number": "PA3XYZ",
        "equity": "100000.00",
        "created_at": "2026-08-20T14:03:00Z",
    }
    acct.update(over)
    return acct


def _snap(**over):
    snap = {"account": _account(), "positions": [], "orders": [], "fills": []}
    snap.update(over)
    return snap


def _by_name(checks):
    return {c.name: c for c in checks}


@pytest.fixture(autouse=True)
def _isolated_record(tmp_path, monkeypatch):
    """Never touch the real used-accounts file. It is a claim about a real account."""
    monkeypatch.setattr(preflight, "USED_ACCOUNTS", tmp_path / "accounts_used.json")


def test_a_fresh_paper_account_passes_every_check():
    assert preflight.failures(preflight.run_checks(_snap())) == []


# --- rows(): the shape we did not expect --------------------------------------


@pytest.mark.parametrize("payload,expected", [
    ([], []),
    ([{"symbol": "SPY"}], [{"symbol": "SPY"}]),
    ({"result": [1, 2]}, [1, 2]),
    ({"positions": [1]}, [1]),
    ({"activities": []}, []),
    ({}, []),
])
def test_rows_reads_the_shapes_these_endpoints_actually_return(payload, expected):
    assert preflight.rows(payload) == expected


@pytest.mark.parametrize("payload", ["a string", 7, None, {"unexpected": {"a": 1}}])
def test_an_unrecognised_shape_is_none_and_not_empty(payload):
    """The whole reason this returns None rather than [].

    An empty list here reads as "the account holds nothing", which is precisely the
    conclusion preflight exists to be certain about. None forces the check above to
    fail instead, and a failed check is recoverable — a false pass is not.
    """
    assert preflight.rows(payload) is None


def test_unreadable_positions_fail_the_check_rather_than_certifying_it_clean():
    checks = _by_name(preflight.run_checks(_snap(positions=None)))
    open_check = checks["no open positions or orders"]
    assert not open_check.passed
    assert "unreadable" in open_check.detail


def test_unreadable_fill_history_fails_the_check():
    checks = _by_name(preflight.run_checks(_snap(fills=None)))
    assert not checks["no trade history"].passed
    assert "unreadable" in checks["no trade history"].detail


# --- the individual checks ----------------------------------------------------


def test_a_live_account_number_fails_the_paper_check():
    checks = _by_name(preflight.run_checks(_snap(account=_account(account_number="9ABCD"))))
    assert not checks["paper environment"].passed


@pytest.mark.parametrize("equity", ["99999.99", "100000.01", "0", "", "unknown", None])
def test_equity_must_be_exactly_one_hundred_thousand(equity):
    # To the cent, and a value that will not parse fails rather than raising: the
    # report must still print the other five checks.
    checks = _by_name(preflight.run_checks(_snap(account=_account(equity=equity))))
    assert not checks["starting equity is $100,000"].passed


def test_an_account_with_one_fill_is_not_fresh():
    checks = _by_name(preflight.run_checks(_snap(fills=[{"id": "f1"}])))
    assert not checks["no trade history"].passed
    assert "1 fill(s)" in checks["no trade history"].detail


def test_an_open_order_fails_even_with_no_positions():
    checks = _by_name(preflight.run_checks(_snap(orders=[{"id": "o1"}])))
    assert not checks["no open positions or orders"].passed


def test_an_account_created_before_the_window_is_rejected():
    old = _account(created_at="2026-07-31T23:59:00Z")
    checks = _by_name(preflight.run_checks(_snap(account=old)))
    assert not checks["account created for this competition"].passed


def test_the_window_boundary_is_inclusive():
    on_the_day = _account(created_at=f"{preflight.COMPETITION_OPENED}T00:00:00Z")
    checks = _by_name(preflight.run_checks(_snap(account=on_the_day)))
    assert checks["account created for this competition"].passed


@pytest.mark.parametrize("created", ["not a date", "", None])
def test_an_unparseable_creation_date_fails_rather_than_raising(created):
    checks = _by_name(preflight.run_checks(_snap(account=_account(created_at=created))))
    assert not checks["account created for this competition"].passed


def test_an_account_with_no_id_cannot_be_certified_unused():
    """No id means nothing to record afterwards, so "not previously used" is unprovable."""
    checks = _by_name(preflight.run_checks(_snap(account=_account(id=""))))
    assert not checks["account not previously used"].passed


# --- the record of claimed accounts -------------------------------------------


def test_a_recorded_account_fails_the_next_run():
    preflight.record("acct-fresh-1")
    checks = _by_name(preflight.run_checks(_snap()))
    assert not checks["account not previously used"].passed


def test_recording_is_idempotent_and_keeps_earlier_ids():
    preflight.record("acct-a")
    preflight.record("acct-b")
    preflight.record("acct-a")
    assert preflight.used_ids() == ["acct-a", "acct-b"]
    assert json.loads(preflight.USED_ACCOUNTS.read_text())["ids"] == ["acct-a", "acct-b"]


def test_an_unparseable_record_does_not_crash_preflight():
    """Deliberately the one place that reads unreadable as empty — see used_ids().

    A corrupt record blocks nothing it should not: the ids it might have contained
    cannot be matched against either way, and failing closed here would refuse a fresh
    account for a file's sake.
    """
    preflight.USED_ACCOUNTS.write_text("{ not json")
    assert preflight.used_ids() == []
    assert preflight.failures(preflight.run_checks(_snap())) == []


# --- rendering ----------------------------------------------------------------


def test_the_rendered_table_marks_pass_and_fail_and_names_every_check():
    checks = preflight.run_checks(_snap(positions=None))
    text = preflight.render(checks)
    assert "[FAIL] no open positions or orders" in text
    assert "[PASS] paper environment" in text
    for check in checks:
        assert check.name in text


def test_render_survives_an_empty_check_list():
    # It is reached through a failure path that returns before the checks run; a
    # ValueError from max() there would replace a diagnosis with a traceback.
    assert preflight.render([]) == ""


def test_the_competition_window_is_a_real_date():
    assert isinstance(preflight.COMPETITION_OPENED, date)
