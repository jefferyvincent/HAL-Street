"""P&L rollup and export.

`docs/WRITEUP.md` asks for realized and unrealized P&L, max drawdown, and a count of
trades against gate rejections. `BUILD-IN-PUBLIC.md` asks for the loss to be posted as
well as the win. This module produces those numbers from evidence written at the time —
the ledger for positions, the journal for decisions — rather than from a reconstruction
after the fact.

Two deliberate choices:

**Realized P&L comes from the ledger, not from the broker.** Alpaca nets legs across
structures into one position per contract, so the account cannot say what a *condor*
made — only what a contract did. Attributing P&L to a structure is something only our
own record can do.

**Drawdown is computed on the equity curve as observed, not as it might have been.**
The journal records account equity at the start of every cycle; peak-to-trough on that
series is a number that actually happened, at a resolution of one scan. It is not a
tick-level maximum drawdown and this module does not pretend otherwise — the field is
named for the sampling that produced it.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from halstreet.agent.ledger import Ledger, OpenStructure
from halstreet.telemetry.journal import Journal


def _dec(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass
class Position:
    """One structure's contribution to the result."""

    structure_id: str
    name: str
    underlying: str
    qty: int
    opened_at: str
    closed_at: str | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    realized_usd: Decimal | None
    unrealized_usd: Decimal | None
    rationale: str = ""

    @property
    def pnl(self) -> Decimal | None:
        return self.realized_usd if self.closed_at else self.unrealized_usd


@dataclass
class Report:
    """Everything the write-up asks for, in one object."""

    realized_usd: Decimal = Decimal(0)
    unrealized_usd: Decimal = Decimal(0)
    positions: list[Position] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    open_count: int = 0
    closed_count: int = 0
    proposals: int = 0
    passed: int = 0
    approved: int = 0
    rejected: int = 0
    orders_submitted: int = 0
    rejections_by_gate: dict[str, int] = field(default_factory=dict)
    equity_start: Decimal | None = None
    equity_last: Decimal | None = None
    equity_peak: Decimal | None = None
    max_drawdown_usd: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    equity_samples: int = 0
    #: Every session date the journal covers, ascending. The window is a *finding*,
    #: not something the caller asserts — see `writeup_results`.
    sessions: tuple[str, ...] = ()
    #: Every agent run behind these figures. Stated when there is more than one.
    runs: tuple[str, ...] = ()

    @property
    def window(self) -> str:
        """The dates this report actually covers, from the journal itself."""
        if not self.sessions:
            return ""
        first, last = self.sessions[0], self.sessions[-1]
        return first if first == last else f"{first} to {last}"

    @property
    def total_usd(self) -> Decimal:
        return self.realized_usd + self.unrealized_usd

    @property
    def win_rate(self) -> Decimal | None:
        decided = self.wins + self.losses
        return None if decided == 0 else (Decimal(self.wins) / decided * 100)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["positions"] = [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(p).items()}
            for p in self.positions
        ]
        for key, value in list(out.items()):
            if isinstance(value, Decimal):
                out[key] = str(value)
        out["total_usd"] = str(self.total_usd)
        out["win_rate_pct"] = None if self.win_rate is None else f"{self.win_rate:.1f}"
        return out


def equity_series(journal: Journal) -> list[tuple[str, Decimal]]:
    """Account equity at the start of each cycle, with the timestamp it was read at.

    The timestamp is what a chart needs and what a bare list of numbers cannot supply:
    scans are not evenly spaced — the scheduler only runs while the broker's clock says
    the market is open, so an overnight gap and a thirty-minute gap look identical once
    the times are thrown away. Plotting equity against sample index would draw a
    continuous session where there were three.
    """
    out: list[tuple[str, Decimal]] = []
    for record in journal.read():
        if record.get("event") != "cycle_start":
            continue
        value = _dec(record.get("equity"))
        ts = record.get("ts")
        if value is not None and value > 0 and ts:
            out.append((str(ts), value))
    return out


#: The windows a trader asks for, and where each one starts.
#:
#: Calendar boundaries, not trailing ones. "This month" means since the first, not the
#: last thirty days, and a figure labelled MTD that quietly means the latter is the
#: kind of wrong nobody catches until it matters.
PERIODS = ("day", "week", "month", "year", "all")


def period_start(period: str, today: date) -> date | None:
    """The first session a window includes. `None` for "all", which has no start."""
    if period == "day":
        return today
    if period == "week":
        return today - timedelta(days=today.weekday())   # Monday
    if period == "month":
        return today.replace(day=1)
    if period == "year":
        return today.replace(month=1, day=1)
    return None


def _on(ts: Any) -> date | None:
    """The session date a timestamp belongs to.

    The UTC date, and that is exact rather than approximate here: the exchange opens
    at 09:30 and closes at 16:00 local, which is 13:30-20:00 UTC in summer and
    14:30-21:00 in winter. Every fill this agent can produce lands inside one UTC day,
    so the two dates agree. It would stop being true for a venue trading through
    midnight UTC, which is why it is written down rather than assumed.
    """
    try:
        return datetime.fromisoformat(str(ts)).date()
    except (TypeError, ValueError):
        return None


def by_period(ledger: Ledger, equity: list[tuple[str, Decimal]], *,
              today: date) -> list[dict]:
    """Realized P&L and equity change over each window a trader asks for.

    **Two numbers, and they are not the same number.** Realized is what closed trades
    actually made — exact, straight off the ledger, and it is zero on a day the desk
    held rather than a day it lost. Equity change is mark-to-market: it moves with open
    positions, which is what most people mean by "today's P&L", and it is the one that
    can be quietly wrong.

    So the equity figure is reported only when the samples actually reach back to the
    start of the window. A journal that begins on the 27th cannot say what the month
    did, and computing it anyway would produce a number labelled MTD that means "since
    this file was created" — plausible, precise, and false. `covered` is how the panel
    knows which it has.

    Realized needs no such guard: a closed structure carries its own date, and a window
    with none in it made nothing, which is a fact rather than a gap.
    """
    first = _on(equity[0][0]) if equity else None
    last_value = equity[-1][1] if equity else None

    out: list[dict] = []
    for period in PERIODS:
        start = period_start(period, today)

        realized = Decimal(0)
        closed = 0
        for structure in ledger.structures:
            if structure.is_open:
                continue
            when = _on(structure.closed_at)
            if when is None or (start is not None and when < start):
                continue
            value = structure.realized()
            if value is not None:
                realized += value
            closed += 1

        # The last sample at or before the window opened is where it started from.
        # Not the first sample *inside* it: on a day with one scan, the open and the
        # close would be the same reading and the day would always show zero.
        opening = None
        if equity and start is None:
            # "All" opens at the first sample there is. It has no start to sit before,
            # and the `start is None` short-circuit below would otherwise put every
            # sample in *both* lists — making the opening the closing and reporting a
            # flat zero over the whole journal, which is what it did.
            opening = equity[0][1]
        elif equity:
            before = [v for ts, v in equity
                      if (d := _on(ts)) is not None and d < start]
            inside = [v for ts, v in equity
                      if (d := _on(ts)) is not None and d >= start]
            opening = before[-1] if before else (inside[0] if inside else None)

        covered = bool(equity) and (
            start is None or (first is not None and first <= start)
        )
        change = (last_value - opening
                  if covered and opening is not None and last_value is not None
                  else None)

        out.append({
            "period": period,
            "start": start.isoformat() if start else None,
            "realized_usd": realized,
            "closed": closed,
            # None when the samples do not reach the start of the window. The panel
            # says so rather than printing a number that means something else.
            "equity_change_usd": change,
            "covered": covered,
            "since": first.isoformat() if first else None,
        })
    return out


def runs_covered(journal: Journal) -> tuple[str, ...]:
    """Distinct agent runs behind these figures.

    More than one is not an error — a restart mid-window is ordinary and its records
    belong in the same report. It is worth *stating*, because the alternative is a
    reader assuming one continuous run, which is how a stray agent's cycles get
    counted as the judged session's.
    """
    seen: list[str] = []
    for event in journal.read():
        run = str(event.get("run") or "")
        if run and run not in seen:
            seen.append(run)
    return tuple(seen)


def sessions_covered(journal: Journal) -> tuple[str, ...]:
    """The distinct session dates in a journal, ascending.

    `session_date` is the exchange's own date and is what a cycle records now; the
    timestamp's date is the fallback for records written before that existed. Both
    are dates the run happened on, which is all this claim needs.
    """
    seen = {
        str(record.get("session_date") or str(record.get("ts") or "")[:10])
        for record in journal.read()
        if record.get("event") == "cycle_start"
    }
    return tuple(sorted(d for d in seen if len(d) == 10))


def equity_curve(journal: Journal) -> list[Decimal]:
    """Just the values, for drawdown — which only cares about order, not spacing."""
    return [value for _, value in equity_series(journal)]


def drawdown(curve: Iterable[Decimal]) -> tuple[Decimal, Decimal, Decimal] | None:
    """Peak, worst peak-to-trough fall in dollars, and the same as a percentage."""
    peak: Decimal | None = None
    worst = Decimal(0)
    worst_pct = Decimal(0)
    for value in curve:
        if peak is None or value > peak:
            peak = value
        fall = peak - value
        if fall > worst:
            worst = fall
            worst_pct = (fall / peak * 100) if peak else Decimal(0)
    return None if peak is None else (peak, worst, worst_pct)


def _unrealized(structure: OpenStructure, marks: dict[str, Decimal]) -> Decimal | None:
    """Mark-to-market for an open structure, if a mark was supplied for it."""
    mark = marks.get(structure.structure_id)
    if mark is None or structure.entry_price is None:
        return None
    return (mark - structure.entry_price) * 100 * structure.qty


def build(ledger: Ledger, journal: Journal, *,
          marks: dict[str, Decimal] | None = None) -> Report:
    """Assemble the report. `marks` maps structure_id to a current net mark."""
    marks = marks or {}
    report = Report()

    for structure in ledger.structures:
        realized = structure.realized() if not structure.is_open else None
        unrealized = _unrealized(structure, marks) if structure.is_open else None
        report.positions.append(
            Position(
                structure_id=structure.structure_id,
                name=structure.name,
                underlying=structure.underlying,
                qty=structure.qty,
                opened_at=structure.opened_at,
                closed_at=structure.closed_at,
                entry_price=structure.entry_price,
                exit_price=structure.exit_price,
                realized_usd=realized,
                unrealized_usd=unrealized,
                rationale=structure.rationale,
            )
        )
        if structure.is_open:
            report.open_count += 1
            if unrealized is not None:
                report.unrealized_usd += unrealized
        else:
            report.closed_count += 1
            if realized is not None:
                report.realized_usd += realized
                # A scratch is neither. Counting it as a win flatters the record.
                if realized > 0:
                    report.wins += 1
                elif realized < 0:
                    report.losses += 1

    summary = journal.summary()
    report.proposals = summary["proposals"]
    report.passed = summary.get("passed", 0)
    report.approved = summary["approved"]
    report.rejected = summary["rejected"]
    report.orders_submitted = summary["orders_submitted"]
    report.rejections_by_gate = summary["rejections_by_gate"]

    curve = equity_curve(journal)
    report.sessions = sessions_covered(journal)
    report.runs = runs_covered(journal)
    report.equity_samples = len(curve)
    if curve:
        report.equity_start = curve[0]
        report.equity_last = curve[-1]
        result = drawdown(curve)
        if result is not None:
            report.equity_peak, report.max_drawdown_usd, report.max_drawdown_pct = result
    return report


def to_csv(report: Report) -> str:
    """One row per structure. For a spreadsheet, or for the demo video."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "structure_id", "name", "underlying", "qty", "opened_at", "closed_at",
        "entry_price", "exit_price", "realized_usd", "unrealized_usd", "rationale",
    ])
    for p in report.positions:
        writer.writerow([
            p.structure_id, p.name, p.underlying, p.qty, p.opened_at, p.closed_at or "",
            p.entry_price if p.entry_price is not None else "",
            p.exit_price if p.exit_price is not None else "",
            p.realized_usd if p.realized_usd is not None else "",
            p.unrealized_usd if p.unrealized_usd is not None else "",
            p.rationale.replace("\n", " "),
        ])
    return buffer.getvalue()


def render(report: Report) -> str:
    """The human-readable summary, shaped like the write-up's Results section."""
    lines = ["Results", "=" * 60]
    lines.append(f"  realized            ${report.realized_usd:+,.2f}")
    lines.append(f"  unrealized          ${report.unrealized_usd:+,.2f}")
    lines.append(f"  total               ${report.total_usd:+,.2f}")
    lines.append("")
    lines.append(f"  positions           {report.closed_count} closed, "
                 f"{report.open_count} open")
    if report.win_rate is not None:
        lines.append(f"  win rate            {report.win_rate:.0f}% "
                     f"({report.wins}W / {report.losses}L)")
    lines.append("")
    lines.append(f"  proposals           {report.proposals}"
                 + (f"  ({report.passed} cycle(s) passed)" if report.passed else ""))
    lines.append(f"  gate outcomes       {report.approved} approved, "
                 f"{report.rejected} rejected")
    lines.append(f"  orders submitted    {report.orders_submitted}")
    if report.rejections_by_gate:
        lines.append("")
        lines.append("  rejections by gate")
        for gate, n in report.rejections_by_gate.items():
            lines.append(f"    {n:>4}  {gate}")
    if report.equity_start is not None:
        lines.append("")
        lines.append(f"  equity              ${report.equity_start:,.2f} -> "
                     f"${report.equity_last:,.2f}")
        if report.max_drawdown_usd is not None:
            lines.append(f"  max drawdown        ${report.max_drawdown_usd:,.2f} "
                         f"({report.max_drawdown_pct:.2f}%) "
                         f"over {report.equity_samples} scan samples")
    return "\n".join(lines)


def write_exports(report: Report, directory: str | Path) -> dict[str, Path]:
    """Write summary.json, positions.csv and results.txt."""
    import json

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out / "summary.json",
        "csv": out / "positions.csv",
        "txt": out / "results.txt",
    }
    paths["json"].write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    paths["csv"].write_text(to_csv(report))
    paths["txt"].write_text(render(report) + "\n")
    return paths


def _describes(label: str, sessions: tuple[str, ...]) -> bool:
    """Whether a human's window label is consistent with the dates in the journal.

    Deliberately lenient: the label is prose ("2026-09-01 to 2026-09-30", "week one"),
    and the point is to catch a label naming dates the data does not contain, not to
    parse English. A label with no dates in it makes no checkable claim and passes.
    """
    import re
    claimed = set(re.findall(r"\d{4}-\d{2}-\d{2}", label))
    if not claimed or not sessions:
        return True
    return min(claimed) <= sessions[-1] and max(claimed) >= sessions[0]


def writeup_results(report: Report, *, window: str = "") -> str:
    """The write-up's Results section, rendered from the run rather than typed.

    `docs/WRITEUP.md` ends with the numbers a judge reads first, and they are the
    numbers most likely to be wrong if a human retypes them at 2am from a terminal
    that has scrolled. This emits the section as markdown so filling it in is one
    command and cannot disagree with the journal.

    Every figure carries its own caveat inline. Drawdown is scan-resolution and says
    so; a `passed` count is reported beside proposals rather than folded into them,
    because an agent that declined 12 cycles is being selective and a total that hides
    that reads as an agent that found nothing.
    """
    # Derived from the journal, never from the caller. `--window` was a label
    # interpolated straight into this line and used to filter nothing, so a judged
    # window's dates could sit above numbers computed over every session in the file
    # — in a section whose own heading promises the figures are generated, not typed.
    # The caller may still describe the window; a description that contradicts the
    # data is reported rather than printed as fact.
    measured = report.window
    if measured and window and not _describes(window, report.sessions):
        lines = [f"- **Window traded:** {measured} — measured from the journal. "
                 f"(The run was labelled {window!r}, which does not match; the "
                 f"figures below cover {measured}.)"]
    else:
        # Only when the label says something the dates do not already say.
        stated = f" ({window})" if window and window.strip() != measured else ""
        lines = ["- **Window traded:** " + ((measured + stated) if measured
                                            else (window or "_not stated_"))]

    total_cycles = report.proposals + report.passed
    lines.append(
        f"- **Proposals / passes:** {report.proposals} proposed, {report.passed} passed "
        f"({total_cycles} model turns). A pass is a considered decline, not a failure — "
        "it is counted separately for that reason."
    )
    lines.append(
        f"- **Gate outcomes:** {report.approved} approved, {report.rejected} rejected"
    )
    if report.rejections_by_gate:
        detail = ", ".join(f"`{g}` {n}" for g, n in report.rejections_by_gate.items())
        lines.append(f"- **Rejections by gate:** {detail}")
    else:
        lines.append(
            "- **Rejections by gate:** none. Not evidence the gates are inert — "
            "candidates are pre-filtered against the same limits before the model "
            "sees them, so the strategy layer absorbs most of what would be rejected."
        )
    if len(report.runs) > 1:
        lines.append(
            f"- **Agent runs in this window:** {len(report.runs)}. The figures cover "
            "all of them. A restart mid-window is ordinary; two agents running at "
            "once is not, and this is where that would show."
        )
    lines.append(f"- **Orders submitted:** {report.orders_submitted}")
    lines.append(
        f"- **Positions:** {report.closed_count} closed, {report.open_count} open"
        + (f" — {report.wins}W / {report.losses}L" if report.closed_count else "")
    )
    lines.append(
        f"- **Realized P&L:** ${report.realized_usd:,.2f}  ·  "
        f"**Unrealized:** ${report.unrealized_usd:,.2f}  ·  "
        f"**Total:** ${report.total_usd:,.2f}"
    )
    if report.equity_start is not None and report.equity_last is not None:
        lines.append(
            f"- **Equity:** ${report.equity_start:,.2f} → ${report.equity_last:,.2f}"
        )
    if report.max_drawdown_usd is not None:
        lines.append(
            f"- **Max drawdown:** ${report.max_drawdown_usd:,.2f} "
            f"({report.max_drawdown_pct:.2f}%) over {report.equity_samples} scan "
            "samples — scan resolution, not tick resolution"
        )
    lines.append(
        "- **What went wrong and what I'd change:** _written by hand; the numbers "
        "above are generated, this one should not be._"
    )
    return "\n".join(lines)
