"""The paper assertion must reject. Per docs/TESTING.md, the rejection is the test.

Alpaca's MCP server performs no environment check of its own, so every one of these
cases is a path by which a bug reaches a real brokerage account. Each gets a test
proving it stops here.
"""

from __future__ import annotations

import pytest

from halstreet.execution.paper_assert import (
    LiveEnvironmentError,
    assert_paper_account,
    assert_paper_config,
    mcp_env,
)

PAPER = {
    "ALPACA_ENV": "paper",
    "ALPACA_API_KEY": "PKTEST1234567890",
    "ALPACA_SECRET_KEY": "secret",
}


def test_accepts_a_clean_paper_config():
    cfg = assert_paper_config(source=PAPER)
    assert cfg.api_key == "PKTEST1234567890"
    assert "paper-api.alpaca.markets" in cfg.endpoint


def test_rejects_live_key_prefix():
    src = {**PAPER, "ALPACA_API_KEY": "AKLIVE1234567890"}
    with pytest.raises(LiveEnvironmentError, match="LIVE credential"):
        assert_paper_config(source=src)


def test_rejects_unrecognised_key_prefix():
    """Fail closed on an unknown prefix rather than assuming it is fine."""
    src = {**PAPER, "ALPACA_API_KEY": "XX1234567890"}
    with pytest.raises(LiveEnvironmentError, match="paper PK"):
        assert_paper_config(source=src)


@pytest.mark.parametrize("declared", ["live", "", "PAPER_TRADING", "prod", "papers"])
def test_rejects_any_env_that_is_not_exactly_paper(declared):
    with pytest.raises(LiveEnvironmentError, match="must be exactly 'paper'"):
        assert_paper_config(source={**PAPER, "ALPACA_ENV": declared})


def test_rejects_missing_credentials():
    """An unreadable check is not a passed check."""
    with pytest.raises(LiveEnvironmentError, match="must both be set"):
        assert_paper_config(source={**PAPER, "ALPACA_SECRET_KEY": ""})


def test_rejects_live_base_url():
    src = {**PAPER, "ALPACA_BASE_URL": "https://api.alpaca.markets"}
    with pytest.raises(LiveEnvironmentError, match="live host"):
        assert_paper_config(source=src)


def test_comp_env_reads_its_own_keys_and_ignores_dev_ones():
    """A dev run that forgot to switch must not pick up the judged account's keys,
    and a comp run must not silently fall back to the dev credentials."""
    src = {**PAPER, "COMP_ALPACA_API_KEY": "PKCOMP123456", "COMP_ALPACA_SECRET_KEY": "s"}
    assert assert_paper_config("comp", source=src).api_key == "PKCOMP123456"
    with pytest.raises(LiveEnvironmentError, match="COMP_ALPACA_API_KEY"):
        assert_paper_config("comp", source=PAPER)


def test_mcp_env_pins_paper_trade_rather_than_trusting_the_default():
    cfg = assert_paper_config(source=PAPER)
    assert mcp_env(cfg)["ALPACA_PAPER_TRADE"] == "true"


def test_account_snapshot_rejects_live():
    with pytest.raises(LiveEnvironmentError, match="LIVE account"):
        assert_paper_account({"is_paper": False, "id": "abc"})


def test_account_snapshot_rejects_a_snapshot_with_no_usable_signal():
    """A snapshot that cannot prove it is paper is not evidence that it is."""
    with pytest.raises(LiveEnvironmentError, match="neither is_paper nor account_number"):
        assert_paper_account({"id": "abc", "equity": "100000"})


def test_account_snapshot_accepts_paper():
    assert_paper_account({"is_paper": True, "id": "abc"})


def test_account_snapshot_accepts_a_real_alpaca_response():
    """Alpaca returns no is_paper flag — the paper signal is the PA account number.

    Regression: an earlier version looked only for is_paper and so refused every
    genuine response, which would have blocked every order.
    """
    assert_paper_account({"id": "abc", "account_number": "PA37FXUPCB7L", "status": "ACTIVE"})


def test_account_snapshot_rejects_a_live_account_number():
    with pytest.raises(LiveEnvironmentError, match="does not carry the paper PA prefix"):
        assert_paper_account({"id": "abc", "account_number": "928374651"})


def test_explicit_is_paper_false_beats_a_paper_looking_number():
    with pytest.raises(LiveEnvironmentError, match="LIVE account"):
        assert_paper_account({"id": "abc", "is_paper": False, "account_number": "PA123"})


# --- diagnosable transport errors ------------------------------------------------

def test_a_nested_task_group_error_reports_its_actual_cause():
    # stdio_client and ClientSession each open a task group, so a plain socket error
    # surfaces as "ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)"
    # — wrapped twice, saying nothing. Three of those reached the journal during
    # development, and during a judged window that is an unexplained gap in the run.
    from halstreet.execution.mcp_client import _describe
    wrapped = ExceptionGroup("unhandled errors in a TaskGroup",
                             [ExceptionGroup("inner", [FileNotFoundError(2, "missing uvx")])])
    described = _describe(wrapped)
    assert "FileNotFoundError" in described
    assert "missing uvx" in described
    assert "TaskGroup" not in described
    # And it names the actual cause. A bare "No such file or directory" is technically
    # the truth and practically useless: the missing file is the MCP server binary,
    # which is a PATH problem, and saying so turns a puzzling failure into a one-liner.
    assert "uvx" in described and "PATH" in described


def test_every_distinct_cause_is_reported_not_just_the_first():
    # A task group can fail for more than one reason at once, and the first is not
    # reliably the interesting one.
    from halstreet.execution.mcp_client import _describe
    described = _describe(ExceptionGroup("g", [ValueError("a"), OSError("b")]))
    assert "ValueError: a" in described and "OSError: b" in described


def test_duplicate_causes_are_collapsed():
    from halstreet.execution.mcp_client import _describe
    described = _describe(ExceptionGroup("g", [OSError("same"), OSError("same")]))
    assert described == "OSError: same"


def test_an_exception_with_no_message_still_names_its_type():
    from halstreet.execution.mcp_client import _describe
    assert _describe(KeyboardInterrupt()) == "KeyboardInterrupt"


def test_recursion_is_bounded():
    # Malformed nesting must not hang the error path — the one place that would turn
    # a recoverable transport blip into a dead loop.
    from halstreet.execution.mcp_client import _describe
    deep = ValueError("floor")
    for _ in range(30):
        deep = ExceptionGroup("g", [deep])
    assert _describe(deep)
