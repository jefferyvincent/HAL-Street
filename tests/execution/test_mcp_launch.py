"""How the broker subprocess is launched, and the version pin that keeps it alive.

`uvx alpaca-mcp-server` resolves its own dependencies at every launch, so an upstream
release can break this project without a commit landing in it. That is not
hypothetical: alpaca-mcp-server 2.3.0 declares `fastmcp>=3.1.0` with no upper bound,
fastmcp 4.0.0 moved `fastmcp.tools.tool`, and the server began dying at import —
`ModuleNotFoundError: No module named 'fastmcp.tools.tool'` — which reaches the agent
as `MCPError: Connection closed` on *every* call, including `get_clock`. The scheduler
read that as "the market's state is unknown", waited 30 minutes, and did it again.

So the pin is a rule with a test, not a note in a config file.
"""

from __future__ import annotations

from halstreet.execution import mcp_client


def test_default_args_pin_fastmcp_below_4():
    """The default launch must constrain fastmcp, because upstream does not.

    Asserted on the resolved constraint rather than on an exact string, so the pin can
    be rewritten (`<4`, `<4.0`, `>=3.1,<4`) without the test having an opinion about
    spelling — what it cares about is that a 4.x cannot be resolved.
    """
    args = mcp_client._DEFAULT_ARGS
    pins = [a for a in args if a.startswith("fastmcp")]
    assert pins, f"no fastmcp constraint in the default launch args: {args!r}"
    assert any("<4" in pin for pin in pins), f"fastmcp is not held below 4.0: {pins!r}"


def test_default_args_still_launch_the_server():
    """A pin that lost the server would be a quiet way to break everything."""
    assert "alpaca-mcp-server" in mcp_client._DEFAULT_ARGS


def test_pin_is_passed_to_uv_as_a_dependency():
    """`--with` is what makes uv resolve it; a bare constraint would be a package name."""
    args = list(mcp_client._DEFAULT_ARGS)
    pin = next(a for a in args if a.startswith("fastmcp"))
    assert args[args.index(pin) - 1] == "--with"


def test_explicit_env_args_still_win(monkeypatch):
    """The escape hatch survives the pin: a checkout or a different version can be run.

    Kept because pinning here is a defence against upstream, not a claim that this
    project knows better than whoever is debugging it at the time.
    """
    monkeypatch.setenv("ALPACA_ENV", "paper")
    monkeypatch.setenv("ALPACA_API_KEY", "PKTEST1234567890")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_MCP_ARGS", "--from ./local-checkout alpaca-mcp-server")

    client = mcp_client.AlpacaMCP.from_env()

    assert client._args == ("--from", "./local-checkout", "alpaca-mcp-server")
