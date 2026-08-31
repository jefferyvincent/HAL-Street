"""Mark the strategy engines against what the tape actually did.

    ./start.sh scorecard                     # every engine, one day ahead
    ./start.sh scorecard -- --horizon 5      # measured five days out instead

Offline by construction: both halves of the measurement — what each engine said, and
the spot beside it — are already in the journal, so this never reaches a broker.

The scoring rules are in `halstreet.telemetry.scorecard`; this file holds the parser
and the printing. See src/halstreet/CLAUDE.md, rule 1.
"""

from __future__ import annotations

import argparse
import sys

from halstreet import paths
from halstreet.config import ConfigError, load_env
from halstreet.telemetry import scorecard
from halstreet.telemetry.journal import Journal

HEAD = f"{'ENGINE':<12}{'CALLS':>7}{'SCORED':>8}{'RIGHT':>7}{'ACCURACY':>10}{'EDGE':>8}"


def _pct(value: float | None) -> str:
    """A percentage, or a dash. A dash is a real answer here — see Constitution VII."""
    return "—" if value is None else f"{value * 100:.0f}%"


def _signed(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.0f}pts"


def render(rows: list[scorecard.EngineScore], *, base: float | None,
           horizon: int, judged: int, days: list[str]) -> str:
    """The table, plus enough context that a reader knows what it is worth."""
    out = [f"ENGINE SCORECARD   {len(days)} session(s) · {judged} scored call(s) · "
           f"{horizon}d horizon", ""]
    if not rows:
        out.append("No engine has been read against a later price yet.")
        out.append("")
        out.append("Not a verdict on the engines — the journal has no pair of prices "
                   f"{horizon} day(s) apart")
        out.append("for any name they read. Run more sessions, or lower --horizon.")
        return "\n".join(out)

    out += [HEAD, "-" * len(HEAD)]
    for row in rows:
        out.append(f"{row.engine:<12}{row.calls:>7}{row.directional:>8}"
                   f"{row.correct:>7}{_pct(row.accuracy):>10}{_signed(row.edge):>8}")
    out.append("")
    out.append(f"base rate: price rose on {_pct(base)} of the scored moves")
    out.append("")
    # The single most misreadable column, said plainly rather than left to the header.
    out.append("EDGE is the column to read. Accuracy alone flatters whichever "
               "direction the tape")
    out.append("happened to take — an engine that always says up scores the base "
               "rate and knows nothing.")
    notes = [r for r in rows if r.note]
    if notes:
        out.append("")
        for row in notes:
            out.append(f"  {row.engine}: {row.note}")
    return "\n".join(out)


def main_async(args: argparse.Namespace) -> int:
    try:
        load_env(args.env, required=False)
    except ConfigError as exc:
        print(f"config: {exc}")
        return 1

    events = list(Journal.open(args.journal).read())
    if not events:
        print(f"no journal at {args.journal}")
        return 1

    calls = scorecard.calls(events)
    judged = scorecard.judge(calls, scorecard.prices(events),
                             horizon_days=args.horizon)
    base = scorecard.base_rate(judged)
    rows = scorecard.score(judged, base, min_calls=args.min_calls)
    days = sorted({str(e.get("ts"))[:10] for e in events
                   if e.get("event") == "cycle_start"})
    print(render(rows, base=base, horizon=args.horizon, judged=len(judged),
                 days=days))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mark the strategy engines against the tape.")
    p.add_argument("--env", default="dev", help="which account's journal to read")
    p.add_argument("--journal", default=None, help="override the journal path")
    p.add_argument("--horizon", type=int, default=scorecard.HORIZON_DAYS,
                   help="days ahead a call is measured (default %(default)s)")
    p.add_argument("--min-calls", type=int, default=scorecard.MIN_CALLS,
                   help="calls needed before an accuracy is printed (default %(default)s)")
    return p


def resolve(args: argparse.Namespace) -> argparse.Namespace:
    """Fill the paths that follow --env. Separated so a test can check the wiring."""
    journal, _ledger, _breaker = paths.for_env(args.env)
    if args.journal is None:
        args.journal = str(journal)
    return args


def main() -> int:
    return main_async(resolve(build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
