"""Typed client for Alpaca's official MCP server.

The rules require broker interaction to go through MCP or a CLI rather than the REST
API, and this is the only module in the project that talks to the broker at all.

HAL's `peripheral/mcp_client.py` already solved the generic problem — transports,
OAuth, discovery, caching — for arbitrary user-configured servers. This is narrower
on purpose: one known server, launched as a subprocess we control, exposing the
handful of tools this agent actually calls, with types on both ends. The generic
client stays in HAL for the conversational surface.

Connection model follows HAL's: connect-per-call. Each call opens a short-lived
stdio session and closes it, which avoids juggling long-lived async MCP sessions
across asyncio tasks (anyio cancel-scope affinity bugs) at the cost of subprocess
startup per call. The scan loop runs on a 30-minute cadence, so that cost is noise.

Every order path passes through `place_structure`, which asserts the paper
environment immediately before submission — not at startup, where a later config
reload could invalidate it.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from halstreet import clock as session_clock
from halstreet.execution.paper_assert import (
    PaperConfig,
    assert_paper_account,
    assert_paper_config,
    mcp_env,
)
from halstreet.execution.structures import Structure
from halstreet.marketdata import news


def _describe(exc: BaseException, depth: int = 0) -> str:
    """A cause worth reading, dug out of anyio's nested task groups.

    `stdio_client` and `ClientSession` each open a task group, so a plain socket error
    surfaces as `ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)` —
    wrapped twice, with the actual cause several layers down. Three of those reached
    the journal during development and said nothing at all about what went wrong;
    during a judged window that is the difference between a two-minute fix and an
    unexplained gap in the run.

    Recurses into `ExceptionGroup.exceptions`, reporting every distinct leaf rather
    than only the first — a task group can fail for more than one reason at once, and
    the first is not reliably the interesting one.
    """
    inner = getattr(exc, "exceptions", None)
    if inner and depth < 5:
        seen: list[str] = []
        for sub in inner:
            text = _describe(sub, depth + 1)
            if text not in seen:
                seen.append(text)
        if seen:
            return " | ".join(seen)
    detail = str(exc).strip()
    if isinstance(exc, FileNotFoundError):
        # The single most common first-run failure, and the least self-explanatory:
        # the MCP server is launched as a subprocess, so a missing `uvx` surfaces as a
        # bare "No such file or directory" naming nothing. start.sh puts .venv/bin on
        # PATH for exactly this reason; anything invoking the client directly has to
        # do the same, and should be told so rather than left to guess.
        return (f"{type(exc).__name__}: cannot launch the MCP server: {detail}. "
                "Is `uvx` on PATH? start.sh exports .venv/bin for exactly this; "
                "invoking a script directly does not.")
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


_CALL_TIMEOUT = 60.0
_DEFAULT_COMMAND = "uvx"
_DEFAULT_ARGS = ("alpaca-mcp-server",)

# Tool names read off a live server via list_tools, not from the repo's toolsets.py.
# That file lists OpenAPI operationIds (getAccount, OptionChain, get-options-contracts)
# which are an internal detail — every registered MCP tool is snake_case, and calling
# an operationId gets "Unknown tool". 72 tools are exposed; these are the ones used.
TOOL_ACCOUNT = "get_account_info"
TOOL_OPTION_CHAIN = "get_option_chain"
TOOL_OPTION_SNAPSHOT = "get_option_snapshot"
TOOL_OPTION_CONTRACTS = "get_option_contracts"
TOOL_PLACE_OPTION_ORDER = "place_option_order"
TOOL_POSITIONS = "get_all_positions"
TOOL_ORDERS = "get_orders"
TOOL_ORDER_BY_ID = "get_order_by_id"
TOOL_ACTIVITIES = "get_account_activities"
# Daily bars on the underlying, for the strategy layer's trend and volatility read.
TOOL_STOCK_BARS = "get_stock_bars"
TOOL_NEWS = "get_news"
TOOL_OPTION_BARS = "get_option_bars"
# Exits, for the position manager. close_position takes a held symbol directly, which
# is the non-mleg path out of a leg; close_all_positions is the panic button.
TOOL_CLOSE_POSITION = "close_position"
TOOL_CLOSE_ALL_POSITIONS = "close_all_positions"
TOOL_CANCEL_ALL_ORDERS = "cancel_all_orders"

# `indicative` is Alpaca's free options feed and the default. `opra` is the official
# consolidated feed and needs a paid market-data agreement on the account — without
# one it returns HTTP 403, not an empty result. Indicative quotes are not the NBBO, so
# whichever feed is in use belongs in the run journal next to any P&L claim.
DEFAULT_OPTION_FEED = "indicative"

# Snapshots/contracts requested per page. Alpaca defaults to 100.
PAGE_LIMIT = 1000


class MCPError(RuntimeError):
    """A tool call that did not come back usable."""


class AlpacaMCP:
    """Client for one Alpaca MCP server subprocess.

    Construct via `from_env` so the paper assertion runs before any credential is
    handed to a subprocess.
    """

    def __init__(self, cfg: PaperConfig, command: str, args: tuple[str, ...],
                 option_feed: str = DEFAULT_OPTION_FEED) -> None:
        self._cfg = cfg
        self._command = command
        self._args = args
        self._option_feed = option_feed

    @classmethod
    def from_env(cls, env: str = "dev") -> AlpacaMCP:
        cfg = assert_paper_config(env)
        command = os.environ.get("ALPACA_MCP_COMMAND", _DEFAULT_COMMAND)
        raw_args = os.environ.get("ALPACA_MCP_ARGS")
        args = tuple(raw_args.split()) if raw_args else _DEFAULT_ARGS
        feed = os.environ.get("ALPACA_OPTION_FEED", DEFAULT_OPTION_FEED).strip()
        return cls(cfg, command, args, option_feed=feed or DEFAULT_OPTION_FEED)

    @property
    def option_feed(self) -> str:
        """Which options feed this client reads. Log it beside any published P&L."""
        return self._option_feed

    @property
    def endpoint(self) -> str:
        return self._cfg.endpoint

    @property
    def redacted_key(self) -> str:
        """Key prefix only — safe for logs, screenshots and build-in-public posts."""
        return self._cfg.redacted_key

    # --- transport ---------------------------------------------------------

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        """Call one tool and return its parsed payload.

        The server returns content blocks; Alpaca's are JSON text. Anything that does
        not parse is raised rather than passed on as a string, because a caller that
        receives an error message shaped like data will act on it.
        """
        params = StdioServerParameters(
            command=self._command,
            args=list(self._args),
            env={**os.environ, **mcp_env(self._cfg)},
        )
        try:
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool, args or {}), timeout=_CALL_TIMEOUT
                )
        except TimeoutError as exc:
            raise MCPError(f"{tool} timed out after {_CALL_TIMEOUT:g}s") from exc
        except Exception as exc:
            raise MCPError(f"{tool} failed: {_describe(exc)}") from exc

        if getattr(result, "isError", False):
            raise MCPError(f"{tool} returned an error: {_text(result)}")
        return _parse(tool, result)

    # --- reads -------------------------------------------------------------

    async def get_account(self) -> dict:
        return await self.call(TOOL_ACCOUNT)

    async def get_option_chain(self, underlying: str, *, expiry_from: str | None = None,
                               expiry_to: str | None = None, strike_gte: float | None = None,
                               strike_lte: float | None = None, max_pages: int = 20,
                               **kwargs: Any) -> dict:
        """The chain for one underlying, paginated to completion.

        Filter server-side. SPY's full chain runs past 2,000 contracts across every
        listed expiry, which is twenty-plus round trips to fetch and nothing the
        strategy engine wants — it works one expiry window at a time. `expiry_from`
        and `expiry_to` are YYYY-MM-DD and map to expiration_date_gte/lte.

        One page is not a chain, so pagination is handled here rather than left to
        every caller to remember. `max_pages` is a runaway guard, and exhausting it
        raises rather than returning a partial chain that looks complete — a
        truncated strike ladder selects a wrong strike silently.
        """
        for key, value in (
            ("expiration_date_gte", expiry_from),
            ("expiration_date_lte", expiry_to),
            ("strike_price_gte", strike_gte),
            ("strike_price_lte", strike_lte),
        ):
            if value is not None:
                kwargs.setdefault(key, value)
        snapshots: dict[str, Any] = {}
        token: str | None = None
        for _ in range(max_pages):
            # Ask for a large page. The server defaults to 100 snapshots, which turns a
            # two-expiry SPY window into twenty-plus round trips against a 30-minute
            # scan budget; the cap below then exists to catch a genuinely unbounded
            # request rather than ordinary width.
            args = {"underlying_symbol": underlying, "feed": self._option_feed,
                    "limit": PAGE_LIMIT, **kwargs}
            if token:
                args["page_token"] = token
            page = await self.call(TOOL_OPTION_CHAIN, args)
            snapshots.update(page.get("snapshots") or {})
            token = page.get("next_page_token")
            if not token:
                return {"snapshots": snapshots}
        raise MCPError(
            f"{TOOL_OPTION_CHAIN} for {underlying} still had pages after {max_pages}; "
            f"refusing to return a partial chain ({len(snapshots)} contracts so far)"
        )

    async def get_option_contracts(self, underlying: str, *, expiry_from: str | None = None,
                                   expiry_to: str | None = None, max_pages: int = 20,
                                   **kwargs: Any) -> list[dict]:
        """Contract metadata for an underlying — crucially, open interest.

        Open interest is **not** in the chain snapshot. `get_option_chain` returns
        quotes, bars, greeks and IV; open interest lives only here, as a string, with
        its own `open_interest_date`. It is published daily, so it is always a day or
        two stale — fine for a liquidity floor, wrong for anything claiming to be live.
        """
        rows: list[dict] = []
        token: str | None = None
        for _ in range(max_pages):
            args: dict[str, Any] = {"underlying_symbols": underlying,
                                    "limit": PAGE_LIMIT, **kwargs}
            if expiry_from:
                args.setdefault("expiration_date_gte", expiry_from)
            if expiry_to:
                args.setdefault("expiration_date_lte", expiry_to)
            if token:
                args["page_token"] = token
            page = await self.call(TOOL_OPTION_CONTRACTS, args)
            rows.extend(page.get("option_contracts") or [])
            token = page.get("next_page_token")
            if not token:
                return rows
        raise MCPError(
            f"{TOOL_OPTION_CONTRACTS} for {underlying} still had pages after {max_pages}; "
            f"refusing to return a partial contract list ({len(rows)} so far)"
        )

    async def get_option_snapshot(self, symbols: list[str], **kwargs: Any) -> dict:
        return await self.call(
            TOOL_OPTION_SNAPSHOT,
            {"symbols": ",".join(symbols), "feed": self._option_feed, **kwargs},
        )

    async def get_news(self, underlying: str, *, limit: int = 12,
                       hours: int = 48) -> list[news.Headline]:
        """Recent headlines for one underlying.

        Returns an empty list rather than raising. News is an enrichment and not a
        dependency — a scan cycle with no headlines must propose exactly as it would
        have without them, so a news outage cannot become a trading outage. The
        failure is still recorded by the caller; it just is not fatal.
        """
        try:
            payload = await self.call(TOOL_NEWS, {
                "symbols": underlying.upper(),
                "limit": limit,
                "start": news.window(hours),
                "sort": "desc",
            })
        except MCPError:
            return []
        return news.parse(payload, limit=limit)

    async def get_option_bars(self, symbols: list[str], *, timeframe: str = "1Day",
                              start: str | None = None, limit: int = 500) -> dict[str, list[dict]]:
        """OHLCV per contract, keyed by OCC symbol.

        Used only by the panel, to draw a structure's price history against the levels
        its exit policy acts on. Nothing in the trading path reads it: a decision is
        made from the live chain and the deterministic ranking, never from a picture.
        """
        args: dict[str, Any] = {"symbols": ",".join(symbols), "timeframe": timeframe,
                                "limit": limit}
        if start:
            args["start"] = start
        payload = await self.call(TOOL_OPTION_BARS, args)
        bars = (payload or {}).get("bars") if isinstance(payload, dict) else None
        return bars if isinstance(bars, dict) else {}

    async def get_positions(self) -> list[dict]:
        return _rows(await self.call(TOOL_POSITIONS))

    async def get_orders(self, **kwargs: Any) -> list[dict]:
        return _rows(await self.call(TOOL_ORDERS, kwargs))

    async def get_order(self, order_id: str) -> dict:
        """One order by id — the only unambiguous source for what a structure filled at.

        Position `avg_entry_price` cannot answer this: the broker nets legs across
        structures, so a contract held by two structures reports one blended average
        belonging to neither. An order id maps to exactly one structure.
        """
        return await self.call(TOOL_ORDER_BY_ID, {"order_id": order_id})

    async def get_daily_closes(self, underlying: str, *, days: int = 500) -> list[float]:
        """Adjusted daily closes for one underlying, oldest first.

        Two corrections the raw endpoint does not make for you, both of which would
        silently corrupt a volatility or trend read:

        **Today's bar is dropped while it is still forming.** A partial session is
        not a day: its close is whatever the last print happened to be, and feeding it
        into a 30-day realized-vol window makes the most recent — and most heavily
        weighted — observation an artefact of what time the scan ran. The scan loop
        runs every 30 minutes, so without this the volatility regime would drift
        through the session on nothing but the clock.

        **Prices are split- and dividend-adjusted.** An unadjusted series turns a
        2-for-1 split into a -50% return, which reads as a volatility explosion that
        never happened. Alpaca defaults to `raw`; this asks for `all`.
        """
        payload = await self.call(TOOL_STOCK_BARS, {
            "symbols": underlying,
            "timeframe": "1Day",
            "days": days,
            "limit": PAGE_LIMIT,
            "adjustment": "all",
        })
        bars = ((payload or {}).get("bars") or {}).get(underlying.upper()) or []
        # The exchange's date, not the host's. These agree during a session — the
        # NYSE day sits inside one UTC day at either offset — so this was right by
        # arithmetic rather than by construction, and only while the agent ran during
        # market hours. `clock.today()` is the one place that answers this question.
        today = session_clock.today().isoformat()
        closes: list[float] = []
        for bar in bars:
            if str(bar.get("t") or "")[:10] >= today:
                continue
            close = bar.get("c")
            if isinstance(close, (int, float)) and close > 0:
                closes.append(float(close))
        return closes

    async def get_activities(self, activity_types: str | None = None, **kwargs: Any) -> Any:
        """Account activity. `activity_types="FILL"` is how you ask whether an account
        has ever traded — the account snapshot carries no fill count."""
        args = dict(kwargs)
        if activity_types:
            args["activity_types"] = activity_types
        return await self.call(TOOL_ACTIVITIES, args)

    # --- the one write -----------------------------------------------------

    async def place_structure(self, structure: Structure) -> dict:
        """Submit a structure as a single order.

        The paper assertion runs here, against the broker's own account snapshot,
        immediately before submission. Alpaca's MCP server performs no such check —
        `place_option_order` is annotated destructive and will place whatever it is
        given against whatever credentials it holds — so this is the last and only
        thing standing between a bug and a real trade. Do not move it to startup and
        do not cache its result.
        """
        assert_paper_account(await self.get_account())
        return await self.call(TOOL_PLACE_OPTION_ORDER, structure.to_wire())


def _text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


# Every tool response is wrapped:
#   {"_alpaca_mcp_security": {"trust": "untrusted_tool_output", ...}, "data": {...}}
#
# The envelope is the server telling us its own output is untrusted — market data and
# account fields are attacker-influenceable in principle and must never be read back
# as instructions. That matters more here than in most MCP clients, because this
# output feeds an LLM that writes trade proposals. Unwrapping happens here so callers
# get plain data, and `TRUSTED_ENVELOPE` records what the server claimed so the agent
# loop can label the content before it ever reaches a prompt.
_SECURITY_KEY = "_alpaca_mcp_security"
_DATA_KEY = "data"


def _rows(payload: Any) -> list[dict]:
    """The list inside a list-returning tool's response.

    Two envelopes, not one. `_parse` strips Alpaca's security wrapper and returns its
    `data`; several tools then put their actual payload under a second key — `result`
    for positions and orders, `news` for news. A caller that reached for the list
    directly got a dict, and iterating a dict yields its *keys*, so the failure is an
    `AttributeError` several frames away from the cause rather than an empty result.

    The loop was already unwrapping positions by hand at the call site, which meant
    the same fix had to be remembered separately everywhere — and had not been, for
    orders. Doing it once here is the point.
    """
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("result", "positions", "orders", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _parse(tool: str, result: Any) -> Any:
    raw = _text(result)
    if not raw.strip():
        raise MCPError(f"{tool} returned no content")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPError(f"{tool} returned unparseable content: {raw[:300]}") from exc

    if isinstance(payload, dict) and _SECURITY_KEY in payload:
        if _DATA_KEY not in payload:
            raise MCPError(f"{tool} returned a security envelope with no {_DATA_KEY!r} field")
        return payload[_DATA_KEY]
    return payload
