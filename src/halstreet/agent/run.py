"""Entry point: `python -m halstreet.agent.run` (or `./start.sh`).

Defaults to a dry run. Submitting has to be asked for — an agent that trades because
someone forgot a flag is a bug with a P&L attached.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from datetime import datetime

from halstreet import clock as session_clock
from halstreet import paths
from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.brainstem.lock import AlreadyRunning, JournalLock
from halstreet.agent.brainstem.schedule import Scheduler, market_clock
from halstreet.agent.cerebellum.loop import Agent
from halstreet.agent.cerebellum.manager import ExitPolicy
from halstreet.agent.cortex import committee as committee_mod
from halstreet.agent.cortex.llm import ProposalWriter
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.config import ConfigError, load_env
from halstreet.execution.mcp_client import AlpacaMCP
from halstreet.execution.paper_assert import LiveEnvironmentError
from halstreet.gates.base import ConfigurationError, Limits
from halstreet.marketdata import discovery
from halstreet.strategy import profiles as P
from halstreet.telemetry.journal import Journal


def log(message: str = "") -> None:
    print(message, flush=True)


#: What an operator types to hand the choice of names to the agent.
AUTO = "auto"


def universe_from_env(source: dict[str, str] | None = None) -> list[str]:
    """The names to scan, or `[]` meaning "discover them".

    `UNIVERSE=SPY,QQQ,IWM` still pins exactly those three, and that matters more now
    than it did — a judged run, a reproduction, or a bug in one name all need the
    universe nailed down, and a discovery mode that could not be switched off would
    make every run unrepeatable.

    Unset or `auto` means discovery. Empty deliberately does *not* fall back to a
    built-in list: a shipped default is how three tickers nobody remembers choosing
    became the universe in the first place.
    """
    src = os.environ if source is None else source
    raw = (src.get("UNIVERSE") or AUTO).strip()
    names = [s.strip().upper() for s in raw.split(",") if s.strip()]
    if not names or names == [AUTO.upper()]:
        return []
    if AUTO.upper() in names:
        raise ValueError(
            f"UNIVERSE={raw!r} mixes {AUTO!r} with explicit symbols. It is one or the "
            "other — either name the symbols, or say auto and let the agent choose."
        )
    return names


def resolve_paths(args: argparse.Namespace) -> argparse.Namespace:
    """Point the unset path arguments at the files for this account.

    The record follows the account for the same reason the credentials do. A judged
    run that appended to the dev journal would have every reported figure computed
    over both — and `Equity: X -> Y` would take X from one account and Y from another.
    """
    journal, ledger, breaker = paths.for_env(args.env)
    if args.journal is None:
        args.journal = str(journal)
    if args.ledger is None:
        args.ledger = str(ledger)
    if args.breaker is None:
        args.breaker = str(breaker)
    return args


async def main_async(args: argparse.Namespace) -> int:
    resolve_paths(args)
    try:
        load_env(args.env)
        limits = Limits.from_env()
        policy = ExitPolicy.from_env()
        profile = P.get(args.profile) if args.profile else P.from_env()
    except (ConfigError, ConfigurationError, P.UnknownProfile) as exc:
        log(f"config: {exc}")
        return 1

    # DRY_RUN in the environment is a floor, not a default: it can force a dry run,
    # but --submit is the only thing that ever turns submission on.
    env_dry = (os.environ.get("DRY_RUN") or "true").strip().lower() != "false"
    dry_run = True if env_dry else not args.submit
    if args.submit and env_dry:
        log("DRY_RUN=true in the environment overrides --submit. Nothing will be sent.")

    try:
        client = AlpacaMCP.from_env(args.env)
    except LiveEnvironmentError as exc:
        log(f"BLOCKED: {exc}")
        return 1

    # One agent per journal, before anything else opens the broker. Two agents on
    # one account interleave their scans and write a single file that reads as one
    # run — and the stale one is usually the dangerous half, because it is running
    # whatever the code was when it started.
    lock = JournalLock(args.journal)
    try:
        lock.acquire()
    except AlreadyRunning as exc:
        log(f"BLOCKED: {exc}")
        return 1

    journal = Journal.open(args.journal)
    ledger = Ledger.load(args.ledger)
    breaker = CircuitState.load(args.breaker)
    if args.clear_halt and breaker.halted:
        log(f"clearing halt: {breaker.halt_reason}")
        breaker.clear()
    writer = ProposalWriter.from_env()
    # `[]` means auto: the universe is discovered at the top of every pass rather
    # than fixed here. Fixed here it would be the overnight tape's answer to a
    # question the afternoon has moved on from.
    universe = (universe_from_env({"UNIVERSE": args.universe}) if args.universe
                else universe_from_env())
    discovery_limit = args.discovery_limit or int(
        os.environ.get("DISCOVERY_LIMIT") or discovery.DEFAULT_SHORTLIST)

    # Tri-state on purpose: the flag is None unless the caller said something, so an
    # explicit --committee/--no-committee beats $COMMITTEE and silence defers to it.
    # `args.committee or enabled()` would have made --no-committee unable to turn off
    # what the environment turned on, which is the one thing the flag is now for.
    use_committee = committee_mod.resolve(args.committee)
    agent = Agent(client, writer, limits=limits, journal=journal, ledger=ledger,
                  policy=policy, dry_run=dry_run, target_dte=args.dte,
                  profile=profile, breaker=breaker,
                  committee=committee_mod.Committee.from_env() if use_committee else None)

    log(f"env={args.env}  mode={'DRY RUN' if dry_run else 'LIVE (paper)'}  "
        f"model={writer.model}  "
        f"universe={','.join(universe) if universe else 'auto (discovered from the news)'}")
    log("proposal path: " + ("committee (catalyst -> bull/bear -> judge)"
                             if use_committee else "single call"))
    log(f"feed={client.option_feed}  journal={args.journal}  ledger={args.ledger}")
    log(f"exits: take {policy.take_profit_pct:g}% / stop {policy.stop_loss_pct:g}% / "
        f"force close at {policy.force_close_dte} DTE")
    log(f"profile={profile.name}  deltas={'/'.join(f'{d:g}' for d in profile.short_deltas)}  "
        f"dte band {profile.min_dte}-{profile.max_dte}  "
        f"builds {', '.join(profile.structures)}")
    # Every dimension where the profile and .env disagreed, in both directions —
    # said out loud at startup rather than left to be inferred from an empty menu.
    for note in agent.floor.notes:
        log(f"  {note}")
    log(f"circuit: {breaker.describe()}")
    log(f"  correlated cap {limits.max_correlated_positions} position(s) per group / "
        f"daily loss {limits.daily_loss_limit_pct:g}% / "
        f"{limits.max_entries_per_hour} entries per hour / "
        f"{limits.max_open_positions} open positions")
    if breaker.halted:
        log("  NOTE: entries are blocked until this clears. Exits are not — they never are.")
    open_now = ledger.open_structures
    log(f"open structures: {len(open_now)}\n")

    totals = {"cycles": 0, "approved": 0, "submitted": 0}

    async def one_pass() -> None:
        # Re-resolved per pass when auto. A universe decided once at startup is a
        # hardcoded list with extra steps by the afternoon.
        names = universe or await agent.discover(limit=discovery_limit)
        if not universe:
            log(f"\n  discovered: {', '.join(names) if names else 'nothing'}")
        if not names:
            # Never a fallback to something else. Substituting a default here would
            # trade a universe nobody chose on exactly the cycles where the evidence
            # for choosing it is missing.
            log("\n  no symbols to scan "
                + ("(discovery found none this pass)" if not universe else ""))
            return
        results = await agent.run_once(names)
        # Wall-clock, for a human watching a terminal — not a market fact, so the
        # host's zone is the right one and DTZ's warning does not apply.
        stamp = datetime.now().astimezone().strftime("%H:%M:%S")
        log(f"\n[{stamp}] scan")
        for result in results:
            log(f"  {result.summary()}")
            for note in result.notes:
                log(f"      note: {note}")
        totals["cycles"] += len(results)
        totals["approved"] += sum(r.approved for r in results)
        totals["submitted"] += sum(r.submitted for r in results)

    if args.once:
        market = None
        # A single pass runs whether or not the clock could be read — but if it can,
        # the exchange's own date is adopted first, so a one-off run measures DTE the
        # same way a scheduled one does.
        with contextlib.suppress(Exception):
            market = await market_clock(client)
        if market is not None:
            session_clock.adopt(market)
        clock = market
        if clock is not None and not clock.is_open:
            log(f"note: market is closed (next open {clock.next_open}) — "
                "quotes will be stale.")
        await one_pass()
    else:
        interval = int(os.environ.get("SCAN_INTERVAL_MINUTES") or 30)
        scheduler = Scheduler(client, interval, log=log, journal=journal)
        scheduler.install_signal_handlers()
        log(f"scheduled: every {interval}m while the market is open"
            f"{', until the close' if args.until_close else ''}. Ctrl-C to stop.")
        try:
            await scheduler.run(one_pass, max_cycles=args.max_cycles,
                                until_close=args.until_close)
        except KeyboardInterrupt:
            log("interrupted")

    lock.release()

    log(f"\n{totals['cycles']} cycle(s): {totals['approved']} approved, "
        f"{totals['submitted']} submitted")

    counts = journal.gate_rejection_counts()
    if counts:
        log("\nrejections by gate (whole journal):")
        for gate, n in counts.items():
            log(f"  {n:>4}  {gate}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The agent's flags, so callers can reuse them instead of copying them."""
    p = argparse.ArgumentParser(
        description=__doc__,
        # Defaults resolve through paths.py rather than being literals here, so
        # --help has to show them or nobody can tell where a run will write.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--env", default="dev", choices=["dev", "comp"])
    p.add_argument("--committee", action=argparse.BooleanOptionalAction, default=None,
                   help="catalyst read, bull/bear debate, then a judge — four model "
                        "calls per underlying instead of one, and the only path that "
                        "reads the news. On unless COMMITTEE=false; --no-committee "
                        "forces the single call for one run")
    p.add_argument("--universe", default="",
                   help=f"comma-separated, or {AUTO!r} to discover from the news; "
                        "defaults to $UNIVERSE")
    p.add_argument("--discovery-limit", type=int, default=0,
                   help="names to scan per pass when the universe is auto; "
                        "defaults to $DISCOVERY_LIMIT")
    p.add_argument("--dte", type=int, default=45, help="target days to expiry")
    p.add_argument("--profile", default="", choices=["", *sorted(P.PROFILES)],
                   help="risk profile; defaults to $RISK_PROFILE, then moderate")
    # default=None so `resolve_paths` below can tell "unset" from "set to the dev
    # path": unset follows the account, and an explicit path always wins. With a
    # literal default the two are indistinguishable and a comp run could not be given
    # its own files without the caller naming all three every time.
    p.add_argument("--journal", default=None,
                   help=f"append-only run journal (default: {paths.RUN_JOURNAL}, "
                        f"or {paths.for_env('comp')[0]} for --env comp)")
    p.add_argument("--ledger", default=None,
                   help="structure ledger — what the broker cannot tell us "
                        "(default: follows --env)")
    p.add_argument("--breaker", default=None,
                   help="circuit-breaker state (equity baseline, halt latch) "
                        "(default: follows --env)")
    p.add_argument("--clear-halt", action="store_true",
                   help="clear a latched daily-loss halt; a human act, never automatic")
    p.add_argument("--submit", action="store_true",
                   help="actually place approved orders (paper). Off by default.")
    p.add_argument("--dry-run", action="store_true", help="explicit no-op; this is the default")
    p.add_argument("--once", action="store_true",
                   help="one pass and exit, ignoring the schedule and market hours")
    p.add_argument("--until-close", action="store_true",
                   help="keep scanning until the market closes, then stop")
    p.add_argument("--max-cycles", type=int, default=None,
                   help="stop after this many scans")
    return p


def main() -> int:
    return asyncio.run(main_async(build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
