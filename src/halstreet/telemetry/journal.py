"""The run journal — the evidence behind every claim this project makes.

Two audiences, one file. The write-up needs a count of proposals rejected and by which
gate; the demo needs something to show; and anyone asking "was that account clean" or
"why did it put that on" needs a record that was written at the time rather than
reconstructed afterwards.

Format is JSON Lines: one self-contained object per event, appended and flushed
immediately. Chosen over a database because a crashed run leaves a readable file, and
over a single JSON document because appending to one of those means rewriting it — and
a process killed mid-rewrite loses the whole history exactly when you most want it.

Every gate verdict is recorded, not only the failing ones. "Nine gates passed and the
tenth rejected on volume" is the interesting sentence; "rejected" alone is not.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from halstreet.gates.base import Decision


def _plain(value: Any) -> Any:
    """JSON-safe. Decimals become strings, never floats — a price that survives a
    round trip through binary floating point is not the price that was traded."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass
class Journal:
    """Append-only event log for one agent."""

    path: Path
    #: Which run wrote a record. Every event carries it.
    #:
    #: Because a file can be written by more than one agent and, until this existed,
    #: say nothing about it. Two soaks once shared a journal for an hour — one on
    #: current code and one on a version behind it — and the only evidence was that
    #: the cycle timings interleaved in a way a single 30-minute scheduler cannot
    #: produce. Everything reading the file, the coverage table and the judged
    #: Results block included, treated it as one run.
    #:
    #: It is easy to arrive at: the writer opens the path per record rather than
    #: holding a handle, which is what makes the log survive a crash — and also what
    #: lets a process that was renamed out of the way quietly recreate the file and
    #: carry on appending to it.
    run_id: str = ""

    @classmethod
    def open(cls, path: str | Path) -> Journal:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return cls(path=p, run_id=uuid.uuid4().hex[:8])

    def write(self, event: str, **fields: Any) -> dict:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run": self.run_id,
            "event": event,
            **_plain(fields),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
            fh.flush()
        return record

    # --- typed events ---------------------------------------------------------

    def cycle_start(self, *, underlying: str, spot: Any, dry_run: bool, **extra: Any) -> dict:
        return self.write("cycle_start", underlying=underlying, spot=spot,
                          dry_run=dry_run, **extra)

    def market_view(self, *, underlying: str, bias: str, bias_reasons: list[str],
                    regime: str, iv_rank: float | None, realized_vol: float | None,
                    event_risk: str, profile: str,
                    events: list[dict] | None = None,
                    patterns: list[dict] | None = None,
                    persistence: dict | None = None,
                    structure: dict | None = None) -> dict:
        """What the ranking believed about the tape before it ranked anything.

        Recorded per cycle because the menu cannot be reconstructed without it: the
        same chain ranks differently under a bullish read than a bearish one, and
        "why was this candidate on top in August?" is unanswerable six weeks later
        unless the inputs were written down beside the output.

        `regime_source` is stamped on every record. The regime is realized-vol rank,
        not IV rank (see `strategy.regime`), and a journal that said "iv_rank" without
        qualification would be quietly claiming a measurement this project does not
        take.
        """
        return self.write(
            "market_view", underlying=underlying, profile=profile,
            bias=bias, bias_reasons=bias_reasons,
            regime=regime, iv_rank=iv_rank, realized_vol=realized_vol,
            regime_source="realized_vol_proxy", event_risk=event_risk,
            # The events themselves, not just the verdict. "event_risk: present" six
            # weeks later is unfalsifiable; "AVGO earnings 2026-09-02" can be checked.
            events=events or [],
            # Confirmed chart patterns on this underlying's daily bars. Recorded for
            # the same reason as the events and read by nothing that decides: the
            # ranking, the gates and the exit policy never see them.
            patterns=patterns or [],
            # Whether direction on this name is sticky, and how far that read reaches.
            # None where the history could not carry a chain — which is not the same
            # as a chain that found nothing, and the panel says which.
            persistence=persistence,
            # Where price last broke a confirmed swing. Unlike the patterns above,
            # this one votes — see `strategy.bias` — so it is recorded as an input to
            # the decision rather than as an annotation beside it.
            structure=structure,
        )

    def candidates(self, underlying: str, candidates: list[dict]) -> dict:
        return self.write("candidates", underlying=underlying,
                          count=len(candidates), candidates=candidates)

    def proposal(self, *, underlying: str, ok: bool, error: str | None = None,
                 structure: dict | None = None, rationale: str = "",
                 confidence: float | None = None, tokens: dict | None = None,
                 passed: bool = False) -> dict:
        """One model turn. `passed` marks a considered decline, which is neither a
        proposal nor a failure and must not be counted as either."""
        return self.write("proposal", underlying=underlying, ok=ok, passed=passed,
                          error=error, structure=structure, rationale=rationale,
                          confidence=confidence, tokens=tokens or {})

    def committee_stage(self, *, underlying: str, stage: str,
                        lean: str | None = None, confidence: float | None = None,
                        error: str | None = None) -> dict:
        """One committee stage finished. A progress record, not a second archive.

        The full `committee` record is written once, after the judge, so that it
        carries the whole session's cost — which is right for the archive and useless
        for watching. Four model calls and about a minute pass with nothing on disk,
        and a panel derives what is running from the last thing written, so the
        slowest stretch of the cycle could only ever be described as "deliberating".

        Deliberately thin. It carries what a live card needs to fill in as it goes —
        which name, which stage, and the catalyst's read once there is one — and not
        the arguments themselves. Those are already going to be written in full a few
        seconds later, and a journal that says everything twice is one where a reader
        has to work out which copy to believe.
        """
        return self.write("committee_stage", underlying=underlying, stage=stage,
                          lean=lean, confidence=confidence, error=error)

    def decision(self, decision: Decision, *, dry_run: bool = False) -> dict:
        """Every gate verdict, not just the rejections.

        `dry_run` is on the record rather than left to be inferred from the
        `cycle_start` above it. An APPROVED that submitted nothing and an APPROVED
        that sent an order are the same six letters, and a reader — a person, the
        panel, or the write-up — has no business having to correlate two records to
        tell a rehearsal from a trade.

        Found the way these things are: a dry-run cycle appended a REJECTED to the
        journal the panel was watching, and it was read as the broker refusing an
        order.
        """
        return self.write(
            "gate_decision",
            structure=decision.proposal.structure.name,
            underlying=decision.proposal.underlying,
            approved=decision.approved,
            dry_run=dry_run,
            # Carried onto the decision so a single record explains itself. Confidence
            # especially: it is journalled and consulted by nothing, and a panel that
            # shows it beside the verdict is the clearest way to say so.
            rationale=decision.proposal.rationale,
            confidence=decision.proposal.confidence,
            structure_detail=decision.proposal.structure.to_wire(),
            rejected_by=[r.gate for r in decision.rejections],
            gates=[
                {"gate": r.gate, "family": r.family, "passed": r.passed,
                 "reason": r.reason}
                for r in decision.results
            ],
        )

    def order(self, *, structure: str, submitted: bool, intent: str = "open",
              structure_id: str | None = None,
              order_id: str | None = None,
              status: str | None = None, filled_qty: Any = None,
              filled_avg_price: Any = None, error: str | None = None) -> dict:
        """One order, opening or closing.

        `intent` exists because both used to be written as a bare `order` event with a
        structure name, so nothing reading the journal could tell an entry from an
        exit without joining against the ledger. Realized P&L was never wrong — it
        comes from the ledger — but a record whose meaning has to be inferred is a
        record with a gap in it, and the exits were the half nobody could see.
        """
        return self.write("order", structure=structure, submitted=submitted,
                          # Which structure this order belongs to. The order id is the
                          # broker's handle and the structure id is ours, and without
                          # both written down nothing reading the journal can get from
                          # a decision to the position it became — the names are all
                          # that connected them, and a name is not an identifier.
                          structure_id=structure_id,
                          intent=intent, order_id=order_id, status=status,
                          filled_qty=filled_qty, filled_avg_price=filled_avg_price,
                          error=error)

    def divergence(self, divergences: list[Any]) -> dict:
        return self.write("divergence", count=len(divergences),
                          detail=[str(d) for d in divergences])

    def fill_correction(self, *, structure_id: str, name: str, side: str = "entry",
                        limit_price: Any = None,
                        fill_price: Any) -> dict:
        """A provisional limit price replaced by the real fill.

        Journalled rather than done silently: it moves every P&L figure derived from
        that structure, and a number that changes without a record is a number nobody
        can reconcile later.
        """
        return self.write("fill_correction", structure_id=structure_id, name=name,
                          side=side, limit_price=limit_price,
                          fill_price=fill_price)

    def halt(self, *, reason: str, equity: Any = None) -> dict:
        """The daily-loss breaker latching. Written once, on the cycle that trips it.

        Its own event rather than an error: nothing malfunctioned. This is the agent
        working correctly on a bad day, and the write-up wants it separable from the
        cycles where something actually broke.
        """
        return self.write("halt", reason=reason, equity=equity)

    def error(self, stage: str, message: str) -> dict:
        return self.write("error", stage=stage, message=message)

    # --- reading back ----------------------------------------------------------

    def read(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # A torn final line from a killed process. Skip it rather than
                        # refusing to read the history that was written correctly.
                        continue

    def gate_rejection_counts(self) -> dict[str, int]:
        """Rejections per gate — the number the write-up asks for by name."""
        counts: dict[str, int] = {}
        for record in self.read():
            if record.get("event") != "gate_decision":
                continue
            for gate in record.get("rejected_by") or []:
                counts[gate] = counts.get(gate, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    def summary(self) -> dict[str, Any]:
        proposals = passes = approved = rejected = orders = 0
        for record in self.read():
            event = record.get("event")
            if event == "proposal" and record.get("ok"):
                proposals += 1
            elif event == "proposal" and record.get("passed"):
                # Counted separately, and never as a proposal. A cycle the model
                # declined is evidence the agent is being selective; folding it into
                # either the proposal or the failure count hides that.
                passes += 1
            elif event == "gate_decision":
                approved += bool(record.get("approved"))
                rejected += not record.get("approved")
            elif event == "order" and record.get("submitted"):
                orders += 1
        return {
            "proposals": proposals,
            "passed": passes,
            "approved": approved,
            "rejected": rejected,
            "orders_submitted": orders,
            "rejections_by_gate": self.gate_rejection_counts(),
        }
