"""Verify that multi-leg option orders work end to end through Alpaca's MCP server.

This is step 1 of the migration order, ahead of everything else, because the whole
project rests on the assumption it tests. Desk research already confirmed the shape:
`place_option_order` accepts a `legs` list, sets `order_class="mleg"` itself, and caps
out at four legs. What research cannot settle needs live paper keys:

  * the actual response shape of OptionChain vs. what strike selection will expect
  * whether this paper account's options level permits every target structure
  * fill behaviour and slippage on a real 4-leg condor

Dry run by default: it fetches a chain, selects strikes, builds a vertical and an iron
condor, and prints the exact payloads without submitting anything. Pass --submit to
actually place them, which is opt-in for the obvious reason.

    python -m halstreet.cli.verify                 # inspect payloads only
    python -m halstreet.cli.verify --submit        # place, then report fills
    python -m halstreet.cli.verify --underlying QQQ --dte 30

The chain-shape reading and strike selection are in `execution/chain_pick.py`, tested
offline against every payload shape this has met. What is left here is what genuinely
needs a broker: the calls, and the printing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from decimal import Decimal

from halstreet import clock
from halstreet.config import ConfigError, load_env
from halstreet.execution.chain_pick import (
    contracts_from_chain,
    expiries_after,
    nearest,
    pick_expiry,
    strikes_for,
)
from halstreet.execution.mcp_client import AlpacaMCP, MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError
from halstreet.execution.structures import (
    Structure,
    StructureError,
    iron_condor,
    roll,
    vertical,
)
from halstreet.marketdata.occ import occ


def log(msg: str = "") -> None:
    print(msg, flush=True)


def head(title: str) -> None:
    log(f"\n{'-' * 72}\n{title}\n{'-' * 72}")


async def run(args: argparse.Namespace) -> int:
    head("1. Paper environment assertion (our side of the MCP boundary)")
    try:
        loaded = load_env(args.env)
        log(f"  loaded   {loaded}")
        client = AlpacaMCP.from_env(args.env)
    except ConfigError as exc:
        log(f"  FAIL     {exc}")
        return 1
    except LiveEnvironmentError as exc:
        log(f"  BLOCKED  {exc}")
        return 1
    log(f"  PASS     config proves paper; key {client.redacted_key}")
    log(f"           endpoint {client.endpoint}")

    head("2. Connect and read the account through MCP")
    try:
        acct = await client.get_account()
    except MCPError as exc:
        log(f"  FAIL     {exc}")
        log("           Is the server installed?  uvx alpaca-mcp-server --help")
        return 1
    log(f"  PASS     account {acct.get('id', '?')}")
    log(f"           equity          {acct.get('equity')}")
    log(f"           options level   {acct.get('options_trading_level')}  <- 3 needed for condors")
    log(f"           options bp      {acct.get('options_buying_power')}")

    head(f"3. Fetch the {args.underlying} option chain")
    # Filter server-side. SPY lists past 2,000 contracts across all expiries, which is
    # twenty-plus round trips for data the engine does not want — it works one expiry
    # window at a time, so ask for one.
    lo = clock.today() + timedelta(days=max(7, args.dte - 10))
    hi = clock.today() + timedelta(days=args.dte + 10)
    log(f"  window   {lo} .. {hi}")
    try:
        chain = await client.get_option_chain(
            args.underlying, expiry_from=f"{lo}", expiry_to=f"{hi}"
        )
    except MCPError as exc:
        log(f"  FAIL     {exc}")
        return 1

    chain_snaps = chain.get("snapshots") if isinstance(chain, dict) else {}
    symbols = contracts_from_chain(chain)
    if not symbols:
        log("  FAIL     could not find option symbols in the response.")
        log(f"           top-level shape: {type(chain).__name__}")
        if isinstance(chain, dict):
            log(f"           keys: {sorted(chain)[:15]}")
        log("           Update contracts_from_chain() in execution/chain_pick.py --")
        log("           this is exactly the unknown this script exists to surface.")
        return 1
    log(f"  PASS     {len(symbols)} contracts; shape handled")
    log(f"           sample: {symbols[0]}")

    expiry = pick_expiry(symbols, args.dte)
    if expiry is None:
        log(f"  FAIL     no expiry at least 7 days out in {len(symbols)} contracts")
        return 1
    dte = (expiry - clock.today()).days
    calls = strikes_for(symbols, expiry, "C")
    puts = strikes_for(symbols, expiry, "P")
    log(f"           expiry {expiry} ({dte} DTE), {len(calls)} calls / {len(puts)} puts")

    if not calls or not puts:
        log("  FAIL     need both calls and puts at the chosen expiry")
        return 1

    head("4. Build structures from real strikes")
    root = args.underlying.upper()

    # Centre on spot, not on the middle of the strike ladder. SPY lists strikes from
    # roughly half spot to well above it, so the ladder's midpoint sits ~50 points
    # below the money — structures built around it would be deep ITM on one side and
    # worthless on the other, and would tell us nothing about real fills.
    try:
        trade = await client.call("get_stock_latest_trade", {"symbols": root})
        spot = Decimal(str(trade["trades"][root]["p"]))
    except (MCPError, KeyError, TypeError) as exc:
        log(f"  FAIL     could not read spot for {root}: {exc}")
        return 1
    mid = nearest(calls, spot)
    log(f"  spot     {spot}  -> centre strike {mid}")
    width = Decimal(args.width)

    try:
        spread = vertical(
            "test vertical call spread",
            occ(root, expiry, "C", mid),
            occ(root, expiry, "C", nearest(calls, mid + width)),
            qty=1,
        )
        condor = iron_condor(
            "test iron condor",
            occ(root, expiry, "P", nearest(puts, mid - width * 2)),
            occ(root, expiry, "P", nearest(puts, mid - width)),
            occ(root, expiry, "C", nearest(calls, mid + width)),
            occ(root, expiry, "C", nearest(calls, mid + width * 2)),
            qty=1,
        )
    except StructureError as exc:
        log(f"  FAIL     {exc}")
        return 1

    # Delta/vega gates read these. Alpaca omits greeks where the IV inversion is
    # ill-conditioned (deep ITM/OTM) and for 0DTE entirely, so a gate that reads them
    # must fail closed on a missing value rather than skip the check.
    legs_used = {leg.symbol for leg in spread.legs} | {leg.symbol for leg in condor.legs}
    no_greeks = sorted(sym for sym in legs_used if "greeks" not in (chain_snaps.get(sym) or {}))
    if no_greeks:
        log(f"  WARN     {len(no_greeks)}/{len(legs_used)} chosen legs have no greeks: {no_greeks}")
    else:
        log(f"  greeks   present on all {len(legs_used)} chosen legs")

    structures = [spread, condor]
    for s in structures:
        log(f"\n  {s.name} -- {len(s.legs)} legs")
        log("  " + json.dumps(s.to_wire(), indent=2).replace("\n", "\n  "))

    head("5. Leg ceiling and the roll rule")
    try:
        Structure(name="five-leg", legs=(*condor.legs, spread.legs[0]))
    except StructureError as exc:
        log(f"  PASS     5-leg structure rejected before submission:\n           {exc}")
    else:
        log("  FAIL     a 5-leg structure was accepted; the ceiling is not enforced")
        return 1

    # A roll is one order or it is not a roll: closing legs + opening legs <= 4.
    # 2-leg structures qualify, 4-leg structures do not.
    later = pick_expiry(expiries_after(symbols, expiry), args.dte + 30)
    if later is None:
        log("  SKIP     no later expiry listed; cannot demonstrate a roll")
    else:
        later_calls = strikes_for(symbols, later, "C")
        replacement = vertical(
            f"{later} vertical",
            occ(root, later, "C", nearest(later_calls, mid)),
            occ(root, later, "C", nearest(later_calls, mid + width)),
            qty=1,
        )
        rolled = roll(spread, replacement)
        log(f"  PASS     2-leg roll fits one order: {len(rolled.legs)} legs "
            f"({expiry} -> {later})")
        log("  " + json.dumps(rolled.to_wire(), indent=2).replace("\n", "\n  "))

        try:
            roll(condor, condor)
        except StructureError as exc:
            log(f"  PASS     condor roll refused at construction:\n           {exc}")
        else:
            log("  FAIL     a condor roll was accepted; the rule is not enforced")
            return 1

        log("\n  NOTE     Alpaca accepts an MLeg order only if all legs are covered within")
        log("           that same order. Whether a 4-leg roll satisfies coverage is the one")
        log("           thing here that research could not settle.")
        log("           The roll is not submitted by this script: its closing legs reference")
        log("           contracts we would have to be holding, so it needs a run against an")
        log("           already-open vertical rather than one placed seconds earlier.")

    if not args.submit:
        head("Dry run complete -- nothing submitted")
        log("  Payload shape confirmed against a real chain. Re-run with --submit to")
        log("  place these and measure fills, which is the part research cannot answer.")
        return 0

    head("6. Submit (PAPER)")
    for s in structures:
        log(f"\n  submitting {s.name} ({len(s.legs)} legs)...")
        try:
            resp = await client.place_structure(s)
        except LiveEnvironmentError as exc:
            log(f"  BLOCKED  {exc}")
            return 1
        except MCPError as exc:
            log(f"  FAIL     {exc}")
            log("           If this is a permissions error, check the options level above.")
            continue
        log(f"  PASS     order {resp.get('id', '?')}  class={resp.get('order_class')}  "
            f"status={resp.get('status')}")
        log(f"           filled {resp.get('filled_qty')} @ {resp.get('filled_avg_price')}")
        log(f"           legs returned: {len(resp.get('legs') or [])}")

    head("Done -- check fills above for slippage on the 4-leg condor")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", default="dev", choices=["dev", "comp"])
    p.add_argument("--underlying", default="SPY")
    p.add_argument("--dte", type=int, default=45, help="target days to expiry")
    p.add_argument("--width", default="5", help="strike width between legs")
    p.add_argument("--submit", action="store_true", help="actually place the orders")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.submit and args.env == "comp":
        log("Refusing to submit test orders to the competition account -- it must stay clean.")
        return 1
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
