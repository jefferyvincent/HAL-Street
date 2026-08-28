"""The cycle: scan -> propose -> gate -> execute -> record.

The shape of this file is the argument the project makes. Read top to bottom, the
model appears exactly once, in `propose`, between two deterministic stages — and
everything after it is plain Python that the model cannot reach, reorder, or skip.

Design rules, all of which exist because this runs unattended:

**One cycle never raises.** Every failure — a dead MCP call, a refused model, a
malformed proposal, a rejected order — is caught, journalled, and returns a result
object. An exception escaping here kills a scheduled process, and a trading agent that
dies silently at 10:04 is worse than one that logs a bad cycle and tries again at
10:34.

**Nothing is skipped on missing data.** If the chain will not load, the cycle ends
without a proposal. It does not proceed on a stale chain, because a proposal gated
against stale data is worse than no proposal at all.

**Dry run is a property of the cycle, not of the caller's discipline.** With
`dry_run=True` the loop does everything including gating, and stops before submission.
That path is the one used to demonstrate rejections without touching the account.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from halstreet import clock
from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.agent.cerebellum.manager import (
    Action,
    ExitDecision,
    ExitPolicy,
    closing_order,
    review,
)
from halstreet.agent.cortex.committee import Committee, Session, brief, reflection
from halstreet.agent.cortex.llm import ProposalWriter
from halstreet.agent.hippocampus.ledger import Ledger
from halstreet.execution.fills import leg_fills
from halstreet.execution.mcp_client import AlpacaMCP, MCPError
from halstreet.execution.paper_assert import LiveEnvironmentError
from halstreet.execution.structures import StructureError
from halstreet.gates import ALL_GATES, evaluate
from halstreet.gates.base import Decision, GateContext, Limits
from halstreet.gates.contract import leg_signature
from halstreet.marketdata import discovery
from halstreet.marketdata import events as events_mod
from halstreet.marketdata import patterns as patterns_mod
from halstreet.marketdata.chain import enrich
from halstreet.strategy import bias as bias_mod
from halstreet.strategy import burn, scoring
from halstreet.strategy import profiles as P
from halstreet.strategy import regime as regime_mod
from halstreet.strategy.candidates import generate
from halstreet.telemetry.journal import Journal


@dataclass
class CycleResult:
    """What one scan of one underlying did."""

    underlying: str
    candidates: int = 0
    proposal_ok: bool = False
    # The model looked at the menu and declined. Neither an approval nor an error.
    passed: bool = False
    decision: Decision | None = None
    submitted: bool = False
    order_id: str | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return self.decision is not None and self.decision.approved

    def summary(self) -> str:
        if self.error:
            return f"{self.underlying}: cycle failed — {self.error}"
        if self.passed:
            note = self.notes[-1][len("passed: "):] if self.notes else ""
            return f"{self.underlying}: passed on {self.candidates} candidates — {note}"
        if self.decision is None:
            return f"{self.underlying}: no proposal ({self.candidates} candidates)"
        verdict = self.decision.summary()
        if self.submitted:
            return f"{verdict} -> submitted {self.order_id}"
        if self.approved:
            return f"{verdict} -> not submitted (dry run)"
        return verdict


class Agent:
    """One scan loop over a universe."""

    def __init__(self, client: AlpacaMCP, writer: ProposalWriter, *, limits: Limits,
                 journal: Journal, ledger: Ledger, policy: ExitPolicy | None = None,
                 dry_run: bool = True, target_dte: int = 45,
                 profile: P.Profile | None = None,
                 breaker: CircuitState | None = None,
                 committee: Committee | None = None) -> None:
        self.client = client
        self.writer = writer
        self.limits = limits
        self.journal = journal
        self.ledger = ledger
        self.policy = policy or ExitPolicy()
        self.dry_run = dry_run
        self.target_dte = target_dte
        self.profile = profile or P.DEFAULT_PROFILE
        # In-memory when the caller supplies nothing, which keeps tests free of a
        # filesystem. The CLI always passes a persisted one — a latch that dies with
        # the process is not a latch.
        self.breaker = breaker if breaker is not None else CircuitState()
        # The floor actually applied: the stricter of profile and gate limits on
        # every dimension. Composed once, here, so a clamp is reported at startup
        # rather than discovered when a scan quietly returns nothing.
        self.floor = P.EffectiveFloor.compose(self.profile, limits)
        # None means the single-call path, which is the default. The committee is a
        # richer way to *reach* a proposal, never a different set of rules for one:
        # whichever produced it, the result meets the same sixteen gates.
        self.committee = committee

    # --- exits, which run before anything opens ----------------------------------

    async def quotes_for(self, symbols: list[str]) -> dict[str, dict]:
        """Snapshots for exactly the contracts we hold.

        Deliberately not the scan chain. Open positions sit at whatever expiry they
        were opened at, which is routinely outside the scan window — marking them
        against that window would silently fail to price the oldest positions, which
        are precisely the ones nearest expiry and most in need of managing.
        """
        if not symbols:
            return {}
        payload = await self.client.get_option_snapshot(symbols)
        return payload.get("snapshots", payload) if isinstance(payload, dict) else {}

    async def manage_exits(self, positions: list[dict] | None = None) -> list[ExitDecision]:
        """Review every open structure and close the ones that qualify.

        Runs before any entry, for two reasons: capital freed here is available to the
        entry path in the same cycle, and opening a new position while an existing one
        is past its stop is how a bad day compounds.

        Nothing in `gates/` is consulted. Exits are never gated.
        """
        open_structures = self.ledger.open_structures
        if not open_structures:
            return []

        symbols = sorted({sym for st in open_structures for sym in st.legs})
        try:
            chain = await self.quotes_for(symbols)
        except MCPError as exc:
            # Failing to price the book is not a reason to skip managing it silently.
            self.journal.error("exit_quotes", str(exc))
            chain = {}

        # Real fill prices first: the exit thresholds below are percentages of the
        # entry price, so they must be measured from what we actually paid.
        await self.refresh_fills()
        # After it, and separately: `refresh_fills` returns a count of corrected
        # prices and callers read it as one, so a backfill that changes no price must
        # not be added to it.
        await self.refresh_leg_fills()
        decisions = review(self.ledger, chain, self.policy, asof=clock.today())
        for decision in decisions:
            self.journal.write(
                "exit_decision",
                structure=decision.structure.name,
                structure_id=decision.structure.structure_id,
                action=decision.action.value,
                reason=decision.reason,
                unrealized_usd=decision.unrealized_usd,
                mark=decision.mark,
                dte=decision.structure.dte(),
            )
            if decision.should_close:
                try:
                    await self._close(decision)
                except Exception as exc:
                    # Per structure, because the alternative is what used to happen:
                    # one unexpected response aborted the sweep, so every structure
                    # after it in the book went unexamined and unclosed for the cycle
                    # — silently, since the raise was caught a frame further out.
                    # Exits are the one path that must never be blocked by another
                    # position's problem.
                    self.journal.error("close_failed",
                                       f"{decision.structure.name}: {type(exc).__name__}: {exc}")

        if any(d.should_close for d in decisions):
            self.ledger.save()
        return decisions

    async def refresh_fills(self) -> int:
        """Backfill actual fill prices onto structures still carrying their limit.

        Entry price is written at submission, when the order is `pending_new` and the
        only number in hand is the limit. Every reported figure downstream — realized
        P&L, the exit policy's percentage-of-max-gain thresholds, the write-up — is
        computed from it, so leaving the limit in place biases all of them in the same
        direction: a limit is the worst price you were willing to accept, so the
        ledger systematically understates what the book made.

        Runs at the top of each cycle, before exits are judged, because a stop set as
        a percentage of the entry price should be measured from the real one. A lookup
        that fails leaves the provisional price alone; an approximate entry price is
        worth far more than none.

        **Both sides, not just entries.** The first version of this walked
        `open_structures`, which meant a position opened and closed inside one session
        was never corrected at all, and a closing order's fill was never fetched under
        any circumstances. Realized P&L is the difference between the two prices, so a
        round trip could — and did — report a figure computed from two limits and no
        fills. Found by the soak harness, not by a unit test, because reaching it takes
        a sequence of cycles rather than a single call.
        """
        corrected = 0
        for structure in self.ledger.awaiting_fill_price():
            entry = structure.is_open
            order_id = structure.order_id if entry else structure.exit_order_id
            try:
                order = await self.client.get_order(order_id)
            except MCPError as exc:
                self.journal.error("fills", f"{order_id}: {exc}")
                continue
            filled = (order or {}).get("filled_avg_price")
            if filled in (None, ""):
                continue  # still pending; ask again next cycle
            try:
                price = Decimal(str(filled))
            except (InvalidOperation, ValueError):
                continue

            was = structure.entry_price if entry else structure.exit_price
            record = self.ledger.record_fill if entry else self.ledger.record_exit_fill
            if record(structure.structure_id, price):
                corrected += 1
                self.journal.fill_correction(
                    structure_id=structure.structure_id, name=structure.name,
                    side="entry" if entry else "exit",
                    limit_price=was, fill_price=price,
                )
            # Off the same order, at no extra cost. The net is what the policy acts
            # on; the legs are what a person reads.
            self.ledger.record_leg_fills(
                structure.structure_id, leg_fills(order), entry=entry)

        return corrected

    async def refresh_leg_fills(self) -> int:
        """Fetch per-leg fills for structures whose net was confirmed without them.

        A second pass rather than a wider first one, because the two ask different
        questions. `refresh_fills` chases a price the ledger is still guessing at;
        this chases a detail the ledger never asked for. Every position opened before
        per-leg fills were recorded is in the second state and none of them is in the
        first, so folding them together would have meant either never backfilling or
        re-confirming net prices that were already confirmed.

        Bounded by `awaiting_leg_prices`: a structure is asked once. An order with no
        usable legs records `{}` and is never asked again, so this costs nothing on a
        steady book.
        """
        learned = 0
        for structure in self.ledger.awaiting_leg_prices():
            entry = structure.is_open
            order_id = structure.order_id if entry else structure.exit_order_id
            try:
                order = await self.client.get_order(order_id)
            except MCPError:
                # No journal entry. The net price is already known, nothing downstream
                # is waiting on this, and a failure here costs a leg table its prices
                # for one cycle — not a decision.
                continue
            if (order or {}).get("status") != "filled":
                continue  # still working; `awaiting_leg_prices` will offer it again
            if self.ledger.record_leg_fills(
                    structure.structure_id, leg_fills(order), entry=entry):
                learned += 1
        return learned

    async def _close(self, decision: ExitDecision) -> None:
        """Submit the closing order for one structure and retire it in the ledger."""
        structure = decision.structure
        try:
            order = closing_order(structure)
        except StructureError as exc:
            self.journal.error("close_build", f"{structure.name}: {exc}")
            return

        if self.dry_run:
            self.journal.order(structure=order.name, submitted=False, intent="close",
                               error="dry run")
            return

        try:
            response = await self.client.place_structure(order)
        except (MCPError, LiveEnvironmentError) as exc:
            # A failed exit is the most important thing in the journal: the position is
            # still open and still needs closing on the next cycle.
            self.journal.order(structure=order.name, submitted=False, intent="close",
                               error=str(exc))
            self.journal.error("close_failed", f"{structure.name}: {exc}")
            return

        # Unparseable is the same outcome as absent: unknown, which the ledger already
        # handles and `refresh_fills` will correct on a later cycle. This parse was
        # undefended while the identical one in `refresh_fills` was guarded, and it sat
        # *between* the order being accepted and the ledger being told about it — so a
        # single malformed figure from the broker meant an order the broker had taken
        # and a ledger that still believed the structure was open, which is exactly the
        # duplicate close the comment below exists to prevent.
        fill = response.get("filled_avg_price")
        exit_price = None
        if fill not in (None, ""):
            try:
                exit_price = Decimal(str(fill))
            except (InvalidOperation, ValueError):
                self.journal.error("close_fill", f"{structure.name}: unparseable "
                                                 f"filled_avg_price {fill!r}")
        self.journal.order(
            structure=order.name, submitted=True, intent="close",
            structure_id=structure.structure_id,
            order_id=response.get("id"), status=response.get("status"),
            filled_qty=response.get("filled_qty"), filled_avg_price=fill,
        )
        # Retire it even when the fill price is unknown. A structure whose closing
        # order was accepted is no longer one we intend to hold, and leaving it open in
        # the ledger would have the next cycle try to close it again.
        self.ledger.record_close(structure.structure_id, exit_price=exit_price,
                                 exit_order_id=response.get("id"))
        # Only when the broker already answered with them. A closing order accepted
        # but not yet filled has legs with no prices, and `leg_fills` returns nothing
        # rather than a partial map — leaving this `None` so the next cycle asks.
        if legs := leg_fills(response):
            self.ledger.record_leg_fills(structure.structure_id, legs, entry=False)
        # Saved here rather than once after the sweep. The order is already with the
        # broker; between that and the write hitting disk, a crash or a kill leaves a
        # position the ledger thinks is still open and will close again on restart.
        self.ledger.save()

    # --- scan ------------------------------------------------------------------

    async def snapshot(self, underlying: str) -> dict[str, Any]:
        """Everything one cycle needs, fetched once.

        The chain window is deliberately narrow. A 40-day SPY window is over 2,000
        contracts; the gates only ever look at the legs actually proposed, and the
        model reasons better over a short menu than a long one.
        """
        asof = clock.today()
        lo = asof + timedelta(days=max(self.limits.min_dte, self.target_dte - 10))
        hi = asof + timedelta(days=self.target_dte + 10)

        account = await self.client.get_account()
        # The client unwraps the tool's envelope now; this used to be done here, and
        # doing it at one call site is how `get_orders` ended up without the same fix.
        positions = await self.client.get_positions()
        trade = await self.client.call("get_stock_latest_trade", {"symbols": underlying})
        spot = Decimal(str(trade["trades"][underlying]["p"]))

        # Trend and volatility, from daily bars on the underlying. Both feed ranking
        # only — never a gate — so a bar request that fails degrades the menu's
        # ordering rather than stopping the cycle. Neutral bias and an unknown regime
        # are the honest readings when there is no history to read.
        try:
            bars = await self.client.get_daily_bars(underlying)
        except (MCPError, KeyError, TypeError) as exc:
            self.journal.error("bars", f"{underlying}: {type(exc).__name__}: {exc}")
            bars = []
        closes = [float(b["c"]) for b in bars]
        view_bias = bias_mod.for_symbol(underlying, float(spot), closes)
        view_regime = regime_mod.build(closes)
        # Confirmed chart patterns on the same bars. Free: they were fetched for the
        # bias and the regime already, and the highs and lows were being discarded.
        #
        # Surfacing only. Nothing reads this back — not the ranking, not the gates,
        # not the exit policy — and `tests/agent/test_patterns_are_surfacing_only.py`
        # asserts as much. A chart heuristic that can size or close a position is a
        # much bigger decision than a badge, and this is a badge.
        view_patterns = patterns_mod.detect(bars)

        chain = (await self.client.get_option_chain(
            underlying, expiry_from=f"{lo}", expiry_to=f"{hi}"
        ))["snapshots"]
        # Open interest is not in the chain — it lives in the contracts endpoint. The
        # liquidity gate fails closed without it, so this merge is required, not an
        # optimisation.
        contracts = await self.client.get_option_contracts(
            underlying, expiry_from=f"{lo}", expiry_to=f"{hi}"
        )
        # Known events between now and the far edge of the scan window, resolved once
        # here and asked per-candidate about each structure's own expiry. Off the
        # broker: Alpaca has no earnings data, so this is the one lookup that does not
        # go through MCP — see marketdata/events.py for why that exception is narrow.
        window = await asyncio.to_thread(
            events_mod.events_between, underlying, asof, hi)
        return {
            "account": account,
            "positions": positions,
            "spot": spot,
            "chain": enrich(chain, contracts),
            "bias": view_bias,
            "regime": view_regime,
            "patterns": view_patterns,
            "events": scoring.EventWindow(
                known=window is not None,
                days_out=tuple((e.on - asof).days for e in (window or [])),
            ),
            "events_detail": window,
        }

    # --- one cycle ---------------------------------------------------------------

    async def run_cycle(self, underlying: str) -> CycleResult:
        result = CycleResult(underlying=underlying)
        try:
            state = await self.snapshot(underlying)
        except (MCPError, LiveEnvironmentError, KeyError, TypeError) as exc:
            result.error = f"scan failed: {type(exc).__name__}: {exc}"
            self.journal.error("scan", result.error)
            return result

        self.journal.cycle_start(
            underlying=underlying, spot=state["spot"], dry_run=self.dry_run,
            equity=state["account"].get("equity"), open_positions=len(state["positions"]),
            # Which calendar this cycle's dates came from. A run that fell back to the
            # host's says so here rather than looking identical to one that did not —
            # the whole failure mode is that the two agree most of the time.
            session_date=clock.today().isoformat(),
            date_source=clock.source(), date_fallbacks=clock.fallbacks(),
        )

        # Refresh the day's equity baseline and latch the halt if it has been
        # breached. Done here, from the snapshot already fetched, so the gate that
        # reads the latch stays a pure function of its context.
        if self.breaker.observe(state["account"], asof=clock.today(),
                                daily_loss_limit_pct=self.limits.daily_loss_limit_pct):
            self.journal.halt(reason=self.breaker.halt_reason,
                              equity=state["account"].get("equity"))
            result.notes.append(f"HALTED: {self.breaker.halt_reason}")

        # Reconcile before proposing. Trading on top of a book we cannot account for
        # is how a small divergence becomes an unexplainable P&L number.
        divergences = self.ledger.reconcile(state["positions"])
        if divergences:
            self.journal.divergence(divergences)
            result.notes.append(f"{len(divergences)} position divergence(s)")

        # What the ranking knows beyond the structures themselves. The weights come
        # from the profile; the bias and regime from this cycle's bars.
        ctx = scoring.Context(
            bias=state["bias"].direction,
            regime=state["regime"].label,
            events=state["events"],
            weights=self.profile.weights,
        )
        self.journal.market_view(
            underlying=underlying,
            bias=state["bias"].direction, bias_reasons=state["bias"].reasons,
            regime=state["regime"].label, iv_rank=state["regime"].rank,
            realized_vol=state["regime"].realized_vol,
            event_risk=events_mod.describe(state.get("events_detail")),
            events=[e.to_prompt() for e in (state.get("events_detail") or [])],
            patterns=[p.to_prompt() for p in state.get("patterns") or []],
            profile=self.profile.name,
        )

        candidates = generate(
            state["chain"], spot=state["spot"], target_dte=self.target_dte,
            # The gates' limits, applied early so the model is never shown a
            # structure that is certain to be rejected. The profile can tighten
            # these but never loosen them — see `EffectiveFloor.compose`.
            limits=self.limits, profile=self.profile, ctx=ctx,
        )
        result.candidates = len(candidates)
        self.journal.candidates(underlying, [c.to_prompt() for c in candidates])
        if not candidates:
            result.notes.append("no candidates built from the chain")
            return result

        # --- the probabilistic step ---------------------------------------------
        base_turn = self.writer.build_user_turn(
            underlying=underlying, spot=state["spot"],
            candidates=[c.to_prompt() for c in candidates],
            account=state["account"], positions=state["positions"], limits=self.limits,
        )
        if self.committee is not None:
            llm, tokens = await self._committee_proposal(
                underlying=underlying, base_turn=base_turn,
                candidates=candidates, state=state)
        else:
            llm = self.writer.propose_with_retry(base_turn)
            tokens = {"in": llm.input_tokens, "out": llm.output_tokens,
                      "cache_read": llm.cache_read_tokens}
        if llm.abstained:
            # Declining is a considered outcome, not a failure. Recorded as its own
            # event so a cycle that passed on a thin menu is distinguishable in the
            # journal from one where the model produced something unparseable.
            reason = llm.parsed.rationale
            self.journal.proposal(underlying=underlying, ok=False, passed=True,
                                  rationale=reason, tokens=tokens)
            result.notes.append(f"passed: {reason}")
            result.passed = True
            return result

        if not llm.ok:
            reason = llm.error or (llm.parsed.error if llm.parsed else "unknown")
            self.journal.proposal(underlying=underlying, ok=False, error=reason,
                                  tokens=tokens)
            result.error = f"no usable proposal: {reason}"
            return result

        proposal = llm.parsed.proposal
        result.proposal_ok = True
        self.journal.proposal(
            underlying=underlying, ok=True, structure=proposal.structure.to_wire(),
            rationale=proposal.rationale, confidence=proposal.confidence, tokens=tokens,
        )

        # --- deterministic from here ---------------------------------------------
        ctx = GateContext(
            account=state["account"], positions=state["positions"], chain=state["chain"],
            limits=self.limits, asof=clock.today(), spot=state["spot"],
            breaker=self.breaker,
            # The menu exactly as the model saw it. Built here from the candidate
            # objects rather than re-derived later, so the gate compares against what
            # was actually offered on this cycle and not a reconstruction of it.
            menu=frozenset(leg_signature(c.legs) for c in candidates),
        )
        decision = evaluate(proposal, ctx, ALL_GATES)
        result.decision = decision
        self.journal.decision(decision, dry_run=self.dry_run)

        if not decision.approved:
            return result
        if self.dry_run:
            result.notes.append("approved but not submitted (dry run)")
            self.journal.order(structure=proposal.structure.name, submitted=False,
                               error="dry run")
            return result

        await self._submit(proposal, result)
        return result

    async def _committee_proposal(self, *, underlying: str, base_turn: str,
                                  candidates: list, state: dict,
                                  ) -> tuple[Any, dict[str, int]]:
        """Catalyst, then bull and bear, then the judge.

        Every stage is allowed to fail. News is an enrichment and the debate is a
        guard; neither is load-bearing for the agent's ability to trade, so an outage
        in either degrades the decision rather than skipping the cycle. What is not
        allowed to degrade is the gate chain, and nothing here touches it.

        The whole session is journalled whether or not a trade comes out — a committee
        whose reasoning is not written down is the same opacity as one model call, at
        four times the price.
        """
        session = Session()

        headlines = await self.client.get_news(underlying)
        session.headlines = len(headlines)
        session.feed = [h.to_ticker() for h in headlines]

        evidence = {
            "bias": state["bias"].direction,
            "bias_reasons": state["bias"].reasons,
            "vol_regime": state["regime"].label,
            "hv_rank": state["regime"].rank,
            "note": "hv_rank is a realized-volatility proxy, not IV rank",
        }
        session.catalyst, counts = await asyncio.to_thread(
            self.committee.catalyst, underlying=underlying,
            headlines=headlines, evidence=evidence)
        session.spend(counts, "catalyst")
        if session.catalyst.error:
            session.errors.append(f"catalyst: {session.catalyst.error}")

        # Closed trades on this name, from the ledger. Outcomes, not recollections.
        session.reflection = reflection(self.ledger, underlying)

        # The mechanical half of the decision, done before anyone argues about it.
        # Here rather than a stage earlier because this is the first point where both
        # reads exist — the catalyst's lean and the chart's — and the one thing the
        # table says that neither says alone is when they disagree.
        session.burn = burn.to_prompt(burn.table(
            candidates,
            signal=burn.signal(
                news=None if session.catalyst.error else session.catalyst.lean,
                confidence=0.0 if session.catalyst.error else session.catalyst.confidence,
                chart=state["bias"].direction,
            ),
        ))

        # The debate sees the catalyst read; the judge sees everything.
        debate_brief = brief(base_turn=base_turn, session=session, debate=True)
        session.bull, session.bear, counts, errors = await asyncio.to_thread(
            self.committee.debate, debate_brief)
        session.spend(counts, "debate")
        session.errors.extend(errors)

        llm, counts = await asyncio.to_thread(
            self.committee.judge,
            system=self.writer.system_prompt,
            brief=brief(base_turn=base_turn, session=session),
        )
        session.spend(counts, "judge")
        # Journalled after the judge, so the record carries the whole session's cost.
        self.journal.write("committee", underlying=underlying, **session.to_journal())
        return llm, dict(session.tokens)

    async def _submit(self, proposal, result: CycleResult) -> None:
        """Submit an approved proposal and record it.

        The paper assertion runs inside `place_structure`, against the broker's own
        account snapshot, immediately before the order — not here, and not at startup.
        """
        structure_id = uuid.uuid4().hex[:12]
        try:
            response = await self.client.place_structure(proposal.structure)
        except LiveEnvironmentError as exc:
            result.error = f"BLOCKED: {exc}"
            self.journal.order(structure=proposal.structure.name, submitted=False,
                               error=str(exc))
            return
        except MCPError as exc:
            result.error = f"order rejected: {exc}"
            self.journal.order(structure=proposal.structure.name, submitted=False,
                               error=str(exc))
            return

        result.submitted = True
        result.order_id = response.get("id")
        # Stamp the throttle on acceptance, not on fill. The runaway this guards
        # against is a loop that keeps *submitting*; waiting for fills to count them
        # would let an unfilled storm through unmeasured.
        self.breaker.record_entry()
        self.journal.order(
            structure=proposal.structure.name, submitted=True,
            structure_id=structure_id, order_id=result.order_id,
            status=response.get("status"), filled_qty=response.get("filled_qty"),
            filled_avg_price=response.get("filled_avg_price"),
        )
        # Record before the fill is known. An order that was accepted is a position we
        # may hold; a ledger that only learns about filled orders cannot explain a
        # partial fill it never knew to expect.
        self.ledger.record_open(
            proposal.structure, proposal.underlying, structure_id=structure_id,
            entry_price=proposal.structure.limit_price, order_id=result.order_id,
            rationale=proposal.rationale,
        )
        # Same rule as the close: record them only if this response already carries
        # them. An order recorded at `pending_new` has none, and `refresh_leg_fills`
        # is what picks them up once it fills.
        if legs := leg_fills(response):
            self.ledger.record_leg_fills(structure_id, legs, entry=True)
        self.ledger.save()

    # --- the universe -------------------------------------------------------------

    async def discover(self, *, limit: int = discovery.DEFAULT_SHORTLIST) -> list[str]:
        """Choose what to scan, from what the tape is actually talking about.

        Census, tally, screen, shortlist — all four deterministic, and the model is
        not consulted about any of them. Which symbols an article is about is the
        publisher's structured claim, and counting claims is arithmetic; putting a
        model here would move the choice of *what to look at* onto the probabilistic
        side of the boundary, which is the one thing this design does not do.

        **It fails small, on purpose.** This runs first in a cycle, so anything it
        raises would cost the agent every name including the ones it already holds.
        A dead feed yields no new names and the caller carries on with whatever
        universe it had; one unreadable ticker costs that ticker.

        **The screen stops at the shortlist.** A census routinely names eighty-odd
        distinct symbols — measured at 86 on 2026-08-27 — and an asset lookup each is
        eighty round trips to discard seventy-four of them. Candidates are screened in
        rank order and the walk stops when the list is full.
        """
        try:
            headlines = await self.client.get_market_news()
        except Exception as exc:
            self.journal.error("discovery", f"{type(exc).__name__}: {exc}")
            return []

        ranked = discovery.tally(headlines)
        picked: list[str] = []
        tally: list[dict[str, Any]] = []
        examined = 0
        for mention in ranked:
            row: dict[str, Any] = {
                "symbol": mention.symbol, "mentions": mention.mentions,
                "headline": mention.headline[:180],
            }
            if len(picked) >= limit or examined >= discovery.MAX_EXAMINED:
                # Never screened, so the agent has no opinion about whether this name
                # is tradable. Recording it as refused would claim a judgement nobody
                # made; recording nothing would hide where the cut fell.
                row["status"] = discovery.NOT_REACHED
            else:
                examined += 1
                try:
                    asset = await self.client.get_asset(mention.symbol)
                except Exception as exc:
                    ok, why = False, f"lookup failed: {type(exc).__name__}"
                else:
                    ok, why = discovery.screen(asset)
                if ok:
                    # The chain itself, before the name is given one of the scan's
                    # slots. The asset screen only says a chain exists; this says it
                    # could carry a structure. Measured on the live tape that is the
                    # difference between a universe of six and a universe of one —
                    # SPY's median bid-ask at 45 DTE is 4% and it builds candidates,
                    # while ESTC at 13%, S at 46% and BBY at 53% cannot clear an 8%
                    # ceiling however often they are scanned.
                    #
                    # Not a second liquidity gate: it asks `candidates.leg_ok`, the
                    # same question the menu builder asks of every leg, and the
                    # sixteen gates still decide everything after. It only declines
                    # to spend a scan on a chain that has already answered.
                    ok, why = await self._chain_is_tradeable(mention.symbol)
                if ok:
                    picked.append(mention.symbol)
                    row["status"] = discovery.SCANNED
                else:
                    row |= {"status": discovery.REFUSED, "reason": why}
            tally.append(row)

        # The whole census, hottest first, not just the winners. "Why did the agent
        # trade this name" is answered by the mention count and the headline behind
        # it; "why did it stop trading that one" by the refusal; and the tail below
        # the cut is what makes the shortlist a *choice* rather than a list — six
        # names off four headlines and six off four hundred are different claims.
        self.journal.write(
            "discovery",
            headlines=len(headlines), symbols=len(ranked), tally=tally,
            # The articles themselves, not only the counts over them. The tally holds
            # a symbol, a count and one headline string — enough to draw a heat map,
            # and short of a news item by exactly the two fields that matter to one:
            # no timestamp is no ordering, and no link is nothing to click. Same shape
            # a committee read journals, so the ticker can merge the two.
            #
            # Untrusted publisher text, as everywhere it appears. It is stored as text
            # and rendered as text; `to_ticker` is where that contract is written down.
            feed=[h.to_ticker() for h in headlines[:discovery.FEED_KEPT]],
        )
        return picked

    async def _chain_is_tradeable(self, symbol: str) -> tuple[bool, str]:
        """Could this chain carry a structure at all? `(ok, why not)`.

        Asks `generate` — the menu builder itself — rather than a cheaper proxy for
        it. The first version counted strikes clearing the liquidity floor at the
        nearest expiry, and it refused every symbol on the live tape including NVDA
        and SPY: the builder tries several expiries and takes the first that yields a
        menu, and at the *nearest* one the broker returns no open interest at all, so
        a per-strike count saw nothing anywhere. A screen that disagrees with the
        thing it is screening for is worse than no screen.

        The arithmetic is free next to the two network calls above it — the chain is
        already in hand, and everything after that is pure. What it buys is a whole
        scan on a name that could never have traded.

        Never raises. A chain that will not load is a fact about this pass rather than
        about the symbol, so it costs that name its slot and nothing else.
        """
        asof = clock.today()
        lo = asof + timedelta(days=max(self.limits.min_dte, self.target_dte - 10))
        hi = asof + timedelta(days=self.target_dte + 10)
        try:
            snaps = (await self.client.get_option_chain(
                symbol, expiry_from=f"{lo}", expiry_to=f"{hi}"))["snapshots"]
            contracts = await self.client.get_option_contracts(
                symbol, expiry_from=f"{lo}", expiry_to=f"{hi}")
            built = buildable(enrich(snaps, contracts), self.limits, self.profile,
                              self.target_dte, asof)
        except Exception as exc:
            return False, f"chain unavailable: {type(exc).__name__}"

        if built:
            return True, ""
        return False, "no structure can be built from this chain inside the floors"

    async def run_once(self, universe: list[str], *,
                       on_start: Callable[[str], None] | None = None,
                       on_result: Callable[[CycleResult], None] | None = None,
                       ) -> list[CycleResult]:
        """One full pass: manage what is open, then look for what to open next.

        Cycles are independent by design — one bad symbol must not cost the others
        their scan, and a failure anywhere in the entry path must not prevent exits.
        """
        # Exits first, once for the whole book — held structures are not per-symbol
        # work and must not be repeated inside the per-underlying loop.
        try:
            exits = await self.manage_exits()
            for decision in exits:
                if decision.action is not Action.HOLD:
                    self.journal.write("exit_summary", detail=str(decision))
        except Exception as exc:
            self.journal.error("manage_exits", f"{type(exc).__name__}: {exc}")
            exits = []

        results: list[CycleResult] = []
        for underlying in universe:
            _report(on_start, underlying)
            try:
                result = await self.run_cycle(underlying)
            except Exception as exc:
                self.journal.error("cycle", f"{type(exc).__name__}: {exc}")
                result = CycleResult(underlying=underlying,
                                     error=f"unhandled {type(exc).__name__}: {exc}")
            results.append(result)
            _report(on_result, result)
        return results


def _report(hook: Callable[[Any], None] | None, value: Any) -> None:
    """Call a progress hook, and never let it cost a scan.

    These print. A closed pipe — `./start.sh | head` — or a terminal that went away
    raises here, and losing the trading because the narration failed is the wrong way
    round: the results are returned regardless and the journal has them either way.
    """
    if hook is None:
        return
    with contextlib.suppress(Exception):
        hook(value)


def buildable(chain: dict, limits, profile, target_dte: int, asof) -> int:
    """How many structures the menu builder can make from this chain. 0 means none.

    The ranking terms are neutral on purpose: bias and regime move a candidate's
    *score*, never whether it survives the floors, and inventing a market view here
    to ask a liquidity question would be inventing one for the whole scan.
    """
    ctx = scoring.Context(bias=bias_mod.NEUTRAL, regime="unknown",
                          events=scoring.EventWindow(), weights=profile.weights)
    return len(generate(chain, spot=None, target_dte=target_dte, limits=limits,
                        profile=profile, ctx=ctx, asof=asof))
