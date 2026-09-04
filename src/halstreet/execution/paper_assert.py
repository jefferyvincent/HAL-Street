"""Paper-environment assertion — the gate that cannot be delegated.

Alpaca's MCP server does not check this for us. `place_option_order` is annotated
`destructiveHint: True` and performs no paper/live validation of its own;
`ALPACA_PAPER_TRADE` defaults to true but is an ordinary environment variable with
nothing guarding it. If it is wrong, or unset in a context we did not configure, the
server will place a real order with real money and report success.

So the assertion lives here, on our side of the MCP boundary, and every order path
calls it before constructing anything. It is deliberately paranoid and fails closed:
three independent signals must all agree that this is paper, and any one of them
being unavailable is itself a failure. A check that silently passes when it cannot
read its input is not a check.

Nothing in this module performs I/O. `assert_paper_config` reads process
configuration; `assert_paper_account` judges an account snapshot the caller already
fetched. Both raise LiveEnvironmentError rather than returning a bool, because the
only correct response to "this might be live" is to stop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Alpaca key-ID prefixes. Paper credentials are issued as PK…, live as AK….
# This is a strong signal precisely because it travels with the credential itself
# rather than with a flag someone can flip.
_PAPER_KEY_PREFIX = "PK"
_LIVE_KEY_PREFIX = "AK"

# Alpaca paper account numbers begin PA, live ones do not.
_PAPER_ACCOUNT_PREFIX = "PA"

_PAPER_HOST = "paper-api.alpaca.markets"
_LIVE_HOST = "api.alpaca.markets"


class LiveEnvironmentError(RuntimeError):
    """Raised when anything about the environment fails to prove it is paper.

    Never catch this to continue. It means the process was one step away from
    trading real money.
    """


@dataclass(frozen=True)
class PaperConfig:
    """A configuration that has been proven to be paper-only."""

    api_key: str
    secret_key: str
    endpoint: str

    @property
    def redacted_key(self) -> str:
        return f"{self.api_key[:6]}…" if len(self.api_key) > 6 else "…"


def assert_paper_config(env: str = "dev", *, source: dict[str, str] | None = None) -> PaperConfig:
    """Prove from process configuration alone that this run cannot reach live trading.

    `env` selects the credential set: "dev" reads ALPACA_*, "comp" reads COMP_ALPACA_*
    so the judged account's keys can never be picked up by a development run that
    forgot to switch. `source` overrides os.environ for testing.

    Raises LiveEnvironmentError unless all of the following hold:
      1. ALPACA_ENV is exactly "paper"
      2. the API key ID carries the paper prefix and not the live one
      3. the resolved endpoint, if one is configured, is the paper host
    """
    src = os.environ if source is None else source
    prefix = "COMP_ALPACA_" if env == "comp" else "ALPACA_"

    declared = (src.get("ALPACA_ENV") or "").strip().lower()
    if declared != "paper":
        raise LiveEnvironmentError(
            f"ALPACA_ENV must be exactly 'paper', got {declared!r}. "
            "Refusing to start: this project trades only in the paper environment."
        )

    api_key = (src.get(f"{prefix}API_KEY") or "").strip()
    secret_key = (src.get(f"{prefix}SECRET_KEY") or "").strip()
    if not api_key or not secret_key:
        raise LiveEnvironmentError(
            f"{prefix}API_KEY and {prefix}SECRET_KEY must both be set for env={env!r}. "
            "Missing credentials fail closed — an unreadable check is not a passed check."
        )

    if api_key.startswith(_LIVE_KEY_PREFIX):
        raise LiveEnvironmentError(
            f"{prefix}API_KEY looks like a LIVE credential ({_LIVE_KEY_PREFIX}… prefix). "
            "Refusing to continue."
        )
    if not api_key.startswith(_PAPER_KEY_PREFIX):
        raise LiveEnvironmentError(
            f"{prefix}API_KEY does not carry the paper {_PAPER_KEY_PREFIX}… prefix. "
            "Refusing to guess — supply a paper credential."
        )

    endpoint = (src.get(f"{prefix}BASE_URL") or "").strip() or f"https://{_PAPER_HOST}"
    if _LIVE_HOST in endpoint and _PAPER_HOST not in endpoint:
        raise LiveEnvironmentError(
            f"{prefix}BASE_URL points at the live host ({endpoint}). Refusing to continue."
        )

    return PaperConfig(api_key=api_key, secret_key=secret_key, endpoint=endpoint)


def mcp_env(cfg: PaperConfig) -> dict[str, str]:
    """The environment handed to the Alpaca MCP server subprocess.

    ALPACA_PAPER_TRADE is set explicitly rather than relying on its default, so the
    server's behaviour does not depend on a default we do not control.
    """
    return {
        "ALPACA_API_KEY": cfg.api_key,
        "ALPACA_SECRET_KEY": cfg.secret_key,
        "ALPACA_PAPER_TRADE": "true",
    }


def assert_paper_account(acct: dict) -> None:
    """Second gate: the broker's own account snapshot must agree it is paper.

    Config can lie — a paper-prefixed key could in principle be pointed somewhere
    unexpected, and an env var proves only what someone typed. This checks what the
    broker actually said about the account we are connected to, and so runs after the
    first successful call and immediately before every order.

    Alpaca's `get_account_info` does **not** return an `is_paper` flag; an earlier
    version of this function looked for one and consequently refused every real
    response. What it does return is `account_number`, and paper accounts carry a PA
    prefix the way paper API keys carry PK. That prefix is the signal, with an
    explicit `is_paper` honoured first in case a future response or a different
    transport supplies one.
    """
    if "is_paper" in acct:
        if not acct["is_paper"]:
            raise LiveEnvironmentError(
                f"Broker reports a LIVE account (id={acct.get('id', 'unknown')}). "
                "Refusing to construct an order."
            )
        return

    number = str(acct.get("account_number") or "").strip().upper()
    if not number:
        raise LiveEnvironmentError(
            "Account snapshot carries neither is_paper nor account_number — cannot "
            "prove this is paper. Failing closed."
        )
    if not number.startswith(_PAPER_ACCOUNT_PREFIX):
        raise LiveEnvironmentError(
            f"Account {number} does not carry the paper {_PAPER_ACCOUNT_PREFIX} prefix "
            f"(id={acct.get('id', 'unknown')}). Refusing to construct an order."
        )
