"""Known events inside a holding period — the input the scoring term never had.

`scoring.event_risk_for` used to take a symbol and nothing else, and answered from a
frozen set of tickers that do not report earnings. For the universe this agent
actually trades — SPY, QQQ, IWM — that returned `none` every time, so one of the six
weighted terms was a constant on every candidate the ranking has ever produced.

The reasoning behind that set was not wrong, it was answering a narrower question than
the term's name. An index does not report earnings, and a diversified one spreads its
constituents' reports across a quarter rather than concentrating them on one afternoon.
Both true. Neither says anything about the two risks that actually price index
options: a macro print, and a single holding large enough to move the whole index on
its own. QQQ is roughly a tenth NVDA; that is concentration wearing a diversified name.

So this module answers the real question — *is there a known event between now and this
expiry* — and it answers it per expiry, which is the part that makes the term
discriminate at all. Two candidates on the same underlying, one expiring before an
event and one spanning it, are not the same trade, and until now they scored as if they
were.

**Source.** Nasdaq's keyless earnings calendar, which is what HAL uses for the same job.
Alpaca has no earnings data — `get_corporate_action_announcements` covers dividends,
splits, mergers and spinoffs, and returns nothing at all on this account's entitlement.
Yahoo now rate-limits unauthenticated clients to 429 on the first request. That makes
this the one thing in the agent that does not come through the MCP server, which is a
deliberate exception and a narrow one: it is a public calendar, not broker interaction,
and no order, position or account figure is ever read from it.

**It fails to `unknown`, never to `none`.** A network error, a shape change, a rate
limit — all of them mean "I could not check", and `unknown` is penalised exactly as
`present` is. An agent that reads a failed lookup as a clear calendar is confidently
wrong precisely on the days it matters most.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from halstreet import paths

NASDAQ_EARNINGS = "https://api.nasdaq.com/api/calendar/earnings"

#: Nasdaq blocks the default client string outright.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json",
}

TIMEOUT = 12.0

#: How far ahead to look at most. Beyond this the calendar is speculative anyway, and
#: a scan window that walks a hundred days is a hundred requests.
MAX_HORIZON_DAYS = 75

#: Holdings large enough that their report moves the index itself.
#:
#: A short, auditable list rather than a live holdings feed, for the same reason
#: `NO_EARNINGS` is one: it changes slowly, it is reviewable in a diff, and a wrong
#: entry is visible rather than buried in a vendor response. It is deliberately not a
#: full holdings table — the question is not "what is in the index" but "what single
#: name can move it on its own afternoon", and that is a much shorter list.
DOMINANT_HOLDINGS: dict[str, frozenset[str]] = {
    "QQQ": frozenset({"NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "META", "GOOGL", "GOOG", "TSLA"}),
    "QQQM": frozenset({"NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "META", "GOOGL", "GOOG", "TSLA"}),
    "SPY": frozenset({"NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "META", "GOOGL", "GOOG"}),
    "VOO": frozenset({"NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "META", "GOOGL", "GOOG"}),
    "IVV": frozenset({"NVDA", "AAPL", "MSFT", "AMZN", "AVGO", "META", "GOOGL", "GOOG"}),
    "SMH": frozenset({"NVDA", "TSM", "AVGO", "AMD", "ASML", "MU", "QCOM", "TXN"}),
    "SOXX": frozenset({"NVDA", "AVGO", "AMD", "TXN", "QCOM", "MU", "ADI"}),
    "XLK": frozenset({"NVDA", "AAPL", "MSFT", "AVGO", "ORCL", "CRM", "AMD"}),
}

#: Below this, a constituent's report is not an index event. Roughly "mega-cap".
MIN_MARKET_CAP_USD = 200_000_000_000

_MONEY = re.compile(r"[^\d.]")


@dataclass(frozen=True)
class Event:
    """One known event inside a window."""

    on: date
    symbol: str
    kind: str          # "earnings"
    #: Why this matters to the underlying being traded — itself, or via an index.
    via: str
    note: str = ""

    def to_prompt(self) -> dict:
        return {"date": self.on.isoformat(), "symbol": self.symbol,
                "kind": self.kind, "via": self.via, "note": self.note}


def _cap(value: object) -> float:
    try:
        return float(_MONEY.sub("", str(value or "")) or 0)
    except ValueError:
        return 0.0


def _cache_path(day: date) -> paths.Path:
    return paths.CACHE_DIR / f"earnings-{day.isoformat()}.json"


def _cached(day: date) -> list[dict] | None:
    try:
        return json.loads(_cache_path(day).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _store(day: date, rows: list[dict]) -> None:
    try:
        paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(day).write_text(json.dumps(rows))
    except OSError:
        pass  # a cache that cannot be written is a slow lookup, not a failure


def fetch_day(day: date, *, client: httpx.Client | None = None) -> list[dict] | None:
    """Reporters for one date. None means the lookup failed — not that it was empty.

    Cached on disk by date because a calendar for a past or present day does not
    change, and a 45-day scan window would otherwise re-fetch the same six weeks on
    every cycle.
    """
    hit = _cached(day)
    if hit is not None:
        return hit

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
    try:
        response = client.get(NASDAQ_EARNINGS, params={"date": day.isoformat()})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None
    finally:
        if owned:
            client.close()

    data = payload.get("data") or {}
    rows = data.get("rows")
    if rows is None:
        # A day with no reporters returns rows: null rather than []. That is a real
        # answer and worth caching; only a transport failure is None to the caller.
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    _store(day, rows)
    return rows


def watch_list(underlying: str) -> frozenset[str]:
    """Symbols whose earnings count as an event for this underlying.

    Itself, plus any holding large enough to move it. A single name watches only
    itself; an index watches the handful of names that can move it alone.
    """
    root = underlying.upper()
    return frozenset({root}) | DOMINANT_HOLDINGS.get(root, frozenset())


def events_between(underlying: str, start: date, end: date, *,
                   client: httpx.Client | None = None) -> list[Event] | None:
    """Known events in `[start, end]`, or None if the calendar could not be read.

    None and `[]` are different answers and the caller must keep them different: one
    is "the window is clear", the other is "I do not know", and only the first is
    grounds for removing a penalty.
    """
    if end < start:
        return []
    end = min(end, start + timedelta(days=MAX_HORIZON_DAYS))
    watching = watch_list(underlying)

    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
    try:
        out: list[Event] = []
        day = start
        while day <= end:
            rows = fetch_day(day, client=client)
            if rows is None:
                return None  # a hole in the window is not a clear window
            for row in rows:
                symbol = str(row.get("symbol") or "").upper().strip()
                if symbol not in watching:
                    continue
                # A constituent only counts if it is big enough to move the index.
                if symbol != underlying.upper() and _cap(row.get("marketCap")) < MIN_MARKET_CAP_USD:
                    continue
                out.append(Event(
                    on=day, symbol=symbol, kind="earnings",
                    via="itself" if symbol == underlying.upper() else underlying.upper(),
                    note=str(row.get("time") or "").replace("time-", "").replace("-", " "),
                ))
            day += timedelta(days=1)
        return out
    finally:
        if owned:
            client.close()


def describe(events: list[Event] | None) -> str:
    """One line for the journal and the startup log."""
    if events is None:
        return "calendar unavailable — event risk unknown"
    if not events:
        return "no known events in window"
    first = min(events, key=lambda e: e.on)
    where = "" if first.via == "itself" else f" (via {first.via})"
    return (f"{len(events)} event(s), next {first.symbol} {first.kind} "
            f"{first.on.isoformat()}{where}")


def today() -> date:
    return datetime.now(UTC).date()
