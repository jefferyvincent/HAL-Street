"""The dev/comp split, now that it is a variable prefix rather than a filename.

There used to be two files, and the safety property was "a comp run reads a
different file." Now there is one, and the property is "a comp run reads different
*names*." That is a stronger claim and a less obvious one, so it is pinned here —
these tests are the reason the collapse is safe, not a formality after it.
"""

from __future__ import annotations

import os

import pytest

from halstreet.config import KEY_PREFIX, ConfigError, load_env

DEV = "ALPACA_API_KEY=PKDEV000000\nALPACA_SECRET_KEY=devsecret\nALPACA_ENV=paper\n"
COMP = "COMP_ALPACA_API_KEY=PKCOMP11111\nCOMP_ALPACA_SECRET_KEY=compsecret\n"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """dotenv never overrides a live variable, so a leaked one would mask every test."""
    for name in (
        "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_ENV",
        "COMP_ALPACA_API_KEY", "COMP_ALPACA_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def write(root, body: str):
    (root / ".env").write_text(body)
    return root


def test_both_accounts_read_the_same_file(tmp_path):
    write(tmp_path, DEV + COMP)
    assert load_env("dev", root=tmp_path).name == ".env"
    assert load_env("comp", root=tmp_path).name == ".env"


def test_a_dev_run_never_reads_the_judged_credentials(tmp_path):
    """The whole point of the prefix. Both pairs are present; dev must ignore one."""
    write(tmp_path, DEV + COMP)
    load_env("dev", root=tmp_path)
    assert os.environ["ALPACA_API_KEY"] == "PKDEV000000"
    assert KEY_PREFIX["dev"] == "ALPACA_"
    assert KEY_PREFIX["comp"] == "COMP_ALPACA_"


def test_a_comp_run_will_not_fall_back_to_the_dev_pair(tmp_path):
    """The failure the two-file layout used to catch by the file being absent."""
    write(tmp_path, DEV)  # dev keys only — the ordinary state before the comp account exists
    with pytest.raises(ConfigError, match="COMP_ALPACA_API_KEY"):
        load_env("comp", root=tmp_path)


def test_a_blank_comp_key_is_not_a_configured_account(tmp_path):
    """.env.example ships these blank on purpose; blank must read as absent, not as set."""
    write(tmp_path, DEV + "COMP_ALPACA_API_KEY=\nCOMP_ALPACA_SECRET_KEY=\n")
    with pytest.raises(ConfigError, match="COMP_ALPACA_API_KEY"):
        load_env("comp", root=tmp_path)


def test_a_missing_secret_is_caught_alongside_a_present_key(tmp_path):
    write(tmp_path, DEV + "COMP_ALPACA_API_KEY=PKCOMP11111\n")
    with pytest.raises(ConfigError, match="COMP_ALPACA_SECRET_KEY"):
        load_env("comp", root=tmp_path)


def test_the_same_account_under_both_names_is_refused(tmp_path):
    """The mistake one file makes visible: dev keys pasted into the COMP_ slots.

    Nothing downstream would catch this — the credentials are real, the environment
    is paper, every gate passes — and the judged run would trade the development
    account, which is disqualifying.
    """
    write(tmp_path, DEV + "COMP_ALPACA_API_KEY=PKDEV000000\nCOMP_ALPACA_SECRET_KEY=devsecret\n")
    with pytest.raises(ConfigError, match="same credential"):
        load_env("comp", root=tmp_path)


def test_an_offline_run_needs_no_credentials_at_all(tmp_path):
    """`report --offline` reads the journal and never speaks to a broker."""
    write(tmp_path, "ALPACA_ENV=paper\n")
    assert load_env("dev", root=tmp_path, required=False) is not None
    assert load_env("comp", root=tmp_path, required=False) is not None


def test_a_missing_file_is_an_error_only_when_the_run_needs_one(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_env("dev", root=tmp_path)
    assert load_env("dev", root=tmp_path, required=False) is None


def test_an_unknown_account_name_is_refused(tmp_path):
    write(tmp_path, DEV)
    with pytest.raises(ConfigError, match="unknown env"):
        load_env("staging", root=tmp_path)
