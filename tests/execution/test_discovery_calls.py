"""The two broker calls discovery rests on.

Both are thin, and both have one property worth pinning that a thin wrapper is
exactly the kind of code to lose in a refactor:

  * `get_market_news` must send **no** symbol filter. Passing one turns the census
    back into the per-symbol read it exists to replace, and the failure is silent —
    the call succeeds, the count comes back, and the universe is whatever was already
    in it.
  * Neither may raise. Discovery runs at the top of a cycle, before anything else
    happens; a broker hiccup there must cost the agent its *new* names, not its scan.
"""

from __future__ import annotations

import asyncio
from typing import Any

from halstreet.execution.mcp_client import AlpacaMCP, MCPError


class _Client(AlpacaMCP):
    """A real client with the transport replaced. Everything above `call` is live."""

    def __init__(self, answer: Any = None, *, raises: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._answer = answer
        self._raises = raises
        self._option_feed = "indicative"

    async def call(self, tool: str, args: dict | None = None) -> Any:
        self.calls.append((tool, dict(args or {})))
        if self._raises:
            raise MCPError("broker said no")
        return self._answer


def _news(*symbols: str) -> dict:
    return {"news": [{"created_at": "2026-08-27T12:00:00Z", "headline": "A thing",
                      "source": "benzinga", "symbols": list(symbols)}]}


def test_the_market_census_asks_for_no_symbol_at_all():
    """The whole point of the call. A `symbols` argument here is the bug."""
    c = _Client(_news("NVDA"))
    asyncio.run(c.get_market_news())
    _, args = c.calls[0]
    assert "symbols" not in args


def test_the_census_carries_a_window_a_limit_and_newest_first():
    c = _Client(_news("NVDA"))
    asyncio.run(c.get_market_news(limit=40, hours=12))
    _, args = c.calls[0]
    assert args["limit"] == 40 and args["sort"] == "desc" and args["start"]


def test_the_census_returns_parsed_headlines_with_their_publisher_tags():
    c = _Client(_news("NVDA", "AMD"))
    got = asyncio.run(c.get_market_news())
    assert [h.symbols for h in got] == [("NVDA", "AMD")]


def test_a_broker_failure_costs_the_new_names_and_nothing_else():
    c = _Client(raises=True)
    assert asyncio.run(c.get_market_news()) == []


def test_an_asset_lookup_returns_the_record():
    c = _Client({"symbol": "NVDA", "class": "us_equity"})
    assert asyncio.run(c.get_asset("NVDA"))["symbol"] == "NVDA"


def test_an_asset_lookup_is_asked_for_in_upper_case():
    c = _Client({})
    asyncio.run(c.get_asset("nvda"))
    assert c.calls[0][1]["symbol_or_asset_id"] == "NVDA"


def test_an_unknown_symbol_screens_out_rather_than_raising():
    """Alpaca 404s a symbol it does not carry, and the feed tags plenty of those.

    Returning `{}` rather than raising lets `discovery.screen` refuse it as the
    unreadable record it is, which is the same answer by a calmer route.
    """
    c = _Client(raises=True)
    assert asyncio.run(c.get_asset("NOPE")) == {}


# --- the page cap -------------------------------------------------------------------
#
# Found by running it. `DEFAULT_SCAN` was 100, and Alpaca answers a `limit` over 50
# with a 400: "invalid limit: larger than the allowed maximum of 50". The census
# therefore failed on every pass, discovery returned nothing every pass, and the agent
# scanned an empty universe — silently, because discovery is written to degrade rather
# than raise. A quiet zero is exactly what a degrading path looks like when it is
# actually broken, which is why this is pinned rather than left to the constant.

class _Pages(_Client):
    """A feed that answers in pages, as the real one does."""

    def __init__(self, pages: list[dict]) -> None:
        super().__init__()
        self._pages = pages

    async def call(self, tool: str, args: dict | None = None):
        self.calls.append((tool, dict(args or {})))
        return self._pages[len(self.calls) - 1]


def _page(*symbols: str, token: str | None = None) -> dict:
    out: dict = {"news": [{"created_at": "2026-08-27T12:00:00Z", "headline": f"About {s}",
                           "source": "benzinga", "symbols": [s]} for s in symbols]}
    if token:
        out["next_page_token"] = token
    return out


def test_no_single_request_asks_for_more_than_the_api_allows():
    c = _Pages([_page("A")])
    asyncio.run(c.get_market_news(limit=500))
    assert all(args["limit"] <= 50 for _, args in c.calls)


def test_a_census_larger_than_one_page_is_paged_rather_than_truncated():
    c = _Pages([_page("A", token="p2"), _page("B")])
    got = asyncio.run(c.get_market_news(limit=100))
    assert [h.symbols for h in got] == [("A",), ("B",)]


def test_the_page_token_is_sent_back_on_the_next_request():
    c = _Pages([_page("A", token="p2"), _page("B")])
    asyncio.run(c.get_market_news(limit=100))
    assert c.calls[1][1]["page_token"] == "p2"


def test_the_first_request_carries_no_page_token():
    c = _Pages([_page("A")])
    asyncio.run(c.get_market_news(limit=10))
    assert "page_token" not in c.calls[0][1]


def test_paging_stops_when_the_feed_runs_out_even_below_the_limit():
    """No token means no more news. Asking again is a round trip for a repeat page."""
    c = _Pages([_page("A")])
    assert len(asyncio.run(c.get_market_news(limit=100))) == 1
    assert len(c.calls) == 1


def test_paging_stops_at_the_limit_even_when_more_pages_exist():
    c = _Pages([_page("A", "B", token="p2"), _page("C", token="p3")])
    got = asyncio.run(c.get_market_news(limit=2))
    assert len(got) == 2 and len(c.calls) == 1


def test_a_failure_partway_through_keeps_the_pages_that_did_arrive():
    """Half a census beats none. The count is a ranking input, not a total."""
    class _Flaky(_Pages):
        async def call(self, tool, args=None):
            self.calls.append((tool, dict(args or {})))
            if len(self.calls) > 1:
                raise MCPError("feed gave up")
            return _page("A", "B", token="p2")

    c = _Flaky([])
    assert len(asyncio.run(c.get_market_news(limit=100))) == 2
