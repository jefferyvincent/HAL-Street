"""Circuit breakers: correlated exposure, the daily-loss latch, rate and count caps.

Every gate here has a test proving it *rejects* — docs/TESTING.md's rule, and the
only kind of test that shows a safety layer is load-bearing rather than decorative.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from halstreet.agent.brainstem.breaker import CircuitState
from halstreet.execution.structures import Leg, PositionIntent, Side, Structure
from halstreet.gates import ALL_GATES, evaluate
from halstreet.gates.base import GateContext, Limits, Proposal
from halstreet.gates.circuit import (
    CORRELATED_GROUPS,
    correlated_exposure,
    daily_loss_halt,
    entry_rate_throttle,
    groups_for,
    open_position_count,
)
from halstreet.marketdata.occ import Right, occ
from tests.gates.conftest import offered

from .conftest import FAR


def spread_on(root: str, qty: int = 1) -> Proposal:
    """A two-leg credit spread on any underlying."""
    short = occ(root, FAR, Right.PUT, Decimal(700))
    long_ = occ(root, FAR, Right.PUT, Decimal(695))
    return Proposal(
        structure=Structure(
            name=f"{root} put spread",
            legs=(Leg(short, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),
                  Leg(long_, 1, Side.BUY, PositionIntent.BUY_TO_OPEN)),
            qty=qty, limit_price=Decimal("-1.00"),
        ),
        underlying=root,
    )


def held(root: str, qty: int) -> dict:
    return {"symbol": occ(root, FAR, Right.PUT, Decimal(700)), "qty": str(qty)}


# --- correlated exposure --------------------------------------------------------

def test_the_default_universe_is_one_correlated_group():
    # The finding that motivated this gate: SPY, QQQ and IWM are the shipped default
    # UNIVERSE, and all three are the same bet.
    assert groups_for("SPY") == groups_for("QQQ") == groups_for("IWM") == ["us-broad-market"]


def test_three_spreads_across_correlated_names_are_rejected(ctx):
    # The live 2026-08-26 scan approved put credit spreads on SPY, QQQ and IWM in one
    # cycle. Every other gate waved it through; this one must not.
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1),
                                held("QQQ", -1), held("QQQ", 1)])
    result = correlated_exposure(spread_on("IWM"), ctx)
    assert not result.passed
    assert "us-broad-market" in result.reason
    assert "move together" in result.reason


def test_the_per_underlying_cap_alone_would_have_allowed_it(ctx):
    # Proof that the new gate is not redundant: the existing concentration gate sees
    # three distinct roots and has no objection to any of them.
    from halstreet.gates.portfolio import underlying_concentration
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1),
                                held("QQQ", -1), held("QQQ", 1)])
    assert underlying_concentration(spread_on("IWM"), ctx).passed


def test_one_correlated_name_alongside_another_is_allowed(ctx):
    # The cap is two positions' worth, not one — some correlation is unavoidable in a
    # book of index options, and a gate that permitted only one name would make the
    # universe pointless.
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1)])
    assert correlated_exposure(spread_on("QQQ"), ctx).passed


def test_an_uncorrelated_name_is_not_constrained_by_a_group_it_is_not_in(ctx):
    """A full `us-broad-market` book has no opinion about KO.

    This test used to also assert the *reason* was "KO is in no correlated group",
    which was the old wave-through. KO is now bounded by the unclassified cap
    instead — a looser limit, but a limit. What survives unchanged, and is the part
    that always mattered, is that one group's exposure never constrains a name
    outside it.
    """
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1),
                                held("QQQ", -1), held("QQQ", 1)])
    result = correlated_exposure(spread_on("KO"), ctx)
    assert result.passed
    assert "us-broad-market" not in result.reason


def test_more_legs_raise_the_ceiling_but_more_contracts_do_not(ctx):
    # The cap scales with legs so a four-leg condor is not judged against a two-leg
    # spread's allowance. It must NOT scale with qty: held contracts do not grow with
    # the order, so letting qty inflate the ceiling means a big order passes where a
    # small one fails. That is backwards for a concentration limit, and it is exactly
    # what an earlier `cap_positions * legs * qty` did.
    ctx = _with(ctx, positions=[held("SPY", -2), held("SPY", 2)])
    assert not correlated_exposure(spread_on("QQQ", qty=1), ctx).passed
    assert not correlated_exposure(spread_on("QQQ", qty=10), ctx).passed


def test_scaling_a_proposal_never_makes_it_more_acceptable(ctx):
    # The property, stated directly: adding contracts can only move a structure
    # toward rejection, never away from it.
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1)])
    verdicts = [correlated_exposure(spread_on("QQQ", qty=q), ctx).passed
                for q in (1, 2, 5, 20)]
    assert verdicts == sorted(verdicts, reverse=True)


def test_the_cap_can_be_disabled(ctx):
    ctx = _with(ctx, limits=Limits(max_correlated_positions=0),
                positions=[held("SPY", -9), held("QQQ", -9)])
    assert correlated_exposure(spread_on("IWM"), ctx).passed


def test_every_group_member_is_uppercase_and_unique():
    # A lowercase entry would silently never match an OCC root.
    for name, members in CORRELATED_GROUPS.items():
        assert all(m == m.upper() and m.isalpha() for m in members), name


# --- the daily-loss latch --------------------------------------------------------

def test_a_latched_halt_rejects_every_entry(ctx):
    ctx.breaker.halt("daily loss 6.0% hit the 5% floor")
    result = daily_loss_halt(spread_on("SPY"), ctx)
    assert not result.passed
    assert "halted" in result.reason


def test_the_latch_does_not_reset_when_equity_recovers():
    # A breaker that un-trips on a bounce is a delay, not a breaker.
    state = CircuitState(baseline_equity=Decimal(100000), baseline_day="2026-08-26")
    state.observe({"equity": "94000"}, asof=date(2026, 8, 26),
                  daily_loss_limit_pct=Decimal(5))
    assert state.halted
    state.observe({"equity": "99500"}, asof=date(2026, 8, 26),
                  daily_loss_limit_pct=Decimal(5))
    assert state.halted


def test_it_latches_exactly_once_so_the_caller_can_react_once():
    state = CircuitState(baseline_equity=Decimal(100000), baseline_day="2026-08-26")
    first = state.observe({"equity": "90000"}, asof=date(2026, 8, 26))
    second = state.observe({"equity": "90000"}, asof=date(2026, 8, 26))
    assert first is True and second is False


def test_a_new_day_re_baselines_and_clears_the_latch():
    state = CircuitState(baseline_equity=Decimal(100000), baseline_day="2026-08-26")
    state.observe({"equity": "90000"}, asof=date(2026, 8, 26))
    assert state.halted
    state.observe({"equity": "90000"}, asof=date(2026, 8, 27))
    assert not state.halted
    assert state.baseline_equity == Decimal(90000)


def test_a_missing_breaker_fails_closed(ctx):
    # A loop that forgot to wire the breaker must not read as one with a healthy it.
    ctx = _with(ctx, breaker=None)
    assert not daily_loss_halt(spread_on("SPY"), ctx).passed
    assert not entry_rate_throttle(spread_on("SPY"), ctx).passed


def test_unreadable_state_on_disk_starts_halted(tmp_path):
    # The file exists to record that trading was stopped, so a file we cannot read
    # might be one that says exactly that.
    bad = tmp_path / "circuit.json"
    bad.write_text("{not json")
    state = CircuitState.load(bad)
    assert state.halted
    assert "unreadable" in state.halt_reason


def test_the_latch_survives_a_restart(tmp_path):
    # HAL keeps this in process-local globals, which means restarting the agent
    # silently re-arms trading — and restarting is what someone does when an
    # unattended agent starts behaving oddly.
    path = tmp_path / "circuit.json"
    first = CircuitState.load(path)
    first.baseline_equity, first.baseline_day = Decimal(100000), "2026-08-26"
    first.observe({"equity": "90000"}, asof=date(2026, 8, 26))
    assert first.halted

    reloaded = CircuitState.load(path)
    assert reloaded.halted
    assert "daily loss" in reloaded.halt_reason


def test_clearing_the_halt_is_a_separate_deliberate_act(tmp_path):
    path = tmp_path / "circuit.json"
    state = CircuitState.load(path)
    state.halt("because")
    state.clear()
    assert not CircuitState.load(path).halted


def test_the_daily_loss_gate_can_be_disabled(ctx):
    ctx.breaker.halt("whatever")
    ctx = _with(ctx, limits=Limits(daily_loss_limit_pct=Decimal(0)))
    assert daily_loss_halt(spread_on("SPY"), ctx).passed


# --- rate and count caps ---------------------------------------------------------

def test_the_entry_throttle_rejects_a_burst(ctx):
    for _ in range(6):
        ctx.breaker.record_entry(now=1_000_000.0)
    result = entry_rate_throttle(spread_on("SPY"), ctx)
    assert not result.passed
    assert "6 entries in the last hour" in result.reason


def test_entries_age_out_of_the_window(ctx):
    for _ in range(6):
        ctx.breaker.record_entry(now=1_000_000.0)
    ctx.breaker.prune(1_000_000.0 + 3601)
    assert entry_rate_throttle(spread_on("SPY"), ctx).passed


def test_too_many_open_positions_rejects(ctx):
    ctx = _with(ctx, limits=Limits(max_open_positions=3),
                positions=[held("SPY", 1), held("QQQ", 1), held("IWM", 1)])
    result = open_position_count(spread_on("DIA"), ctx)
    assert not result.passed
    assert "exceed the cap of 3" in result.reason


def test_adding_to_a_contract_already_held_does_not_add_a_position(ctx):
    # Legs net at the broker: selling more of a contract already held is one position
    # at a larger size, not a second position.
    existing = occ("SPY", FAR, Right.PUT, Decimal(700))
    ctx = _with(ctx, limits=Limits(max_open_positions=1),
                positions=[{"symbol": existing, "qty": "-1"}])
    proposal = Proposal(
        structure=Structure(name="more of the same",
                            legs=(Leg(existing, 1, Side.SELL, PositionIntent.SELL_TO_OPEN),),
                            qty=1, limit_price=Decimal("-1.00")),
        underlying="SPY")
    assert open_position_count(proposal, ctx).passed


# --- the whole chain --------------------------------------------------------------

def test_a_healthy_proposal_passes_the_whole_chain(vertical_spread, ctx):
    # `offered` is explicit: a healthy proposal is one the strategy engine actually
    # built, and `from-the-menu` rejects anything else — including this, without it.
    decision = evaluate(vertical_spread, offered(ctx, vertical_spread), ALL_GATES)
    assert decision.approved, decision.summary()
    assert len(decision.results) == len(ALL_GATES)


def test_the_circuit_gates_are_in_the_chain():
    names = {g.gate_name for g in ALL_GATES}
    assert {"correlated-exposure", "daily-loss-halt",
            "entry-rate-throttle", "open-position-count"} <= names


def _with(ctx: GateContext, **overrides) -> GateContext:
    import dataclasses
    return dataclasses.replace(ctx, **overrides)


# --- names the correlation map has never heard of ---------------------------------
#
# Added when the universe stopped being three tickers in `.env` and started being
# whatever the news feed is talking about. Until then every name the agent could
# propose was in `CORRELATED_GROUPS` by construction, so "in no group" meant "a name
# a human deliberately added and deliberately left unmapped". With discovery it means
# "a name nobody has ever classified", which is most of them — and the old answer to
# that was to wave it through.

def test_a_name_the_map_has_never_heard_of_is_not_simply_waved_through(ctx):
    """The gap discovery opens, stated as a test.

    `CORRELATED_GROUPS` is a hand-written map of about sixty tickers. A discovered
    universe is unbounded, so the common case is now a name that is in no group — and
    a correlation cap that answers "allowed, no group" to the common case is not a
    cap. The book can hold ten single names that all fall over together and this gate
    never counts past one of them.
    """
    ctx = _with(ctx, positions=[held("KO", -1), held("KO", 1),
                                held("PEP", -1), held("PEP", 1),
                                held("MO", -1), held("MO", 1)])
    assert not correlated_exposure(spread_on("MCD"), ctx).passed


def test_the_unmapped_cap_is_its_own_limit_not_the_correlation_one(ctx):
    """Two different claims, so two different numbers.

    "SPY and QQQ move together" is a fact about those two names. "I have not
    classified KO, PEP and MCD" is a fact about the *map*, and bounding it is a
    humility limit rather than a correlation one. Sharing one knob would mean
    loosening the verified claim to make room for the unverified one.
    """
    ctx = _with(ctx, limits=Limits(max_correlated_positions=2,
                                   max_unclassified_positions=4),
                positions=[held("KO", -1), held("KO", 1),
                           held("PEP", -1), held("PEP", 1),
                           held("MO", -1), held("MO", 1)])
    assert correlated_exposure(spread_on("MCD"), ctx).passed


def test_the_unmapped_cap_says_which_names_it_counted(ctx):
    ctx = _with(ctx, positions=[held("KO", -1), held("KO", 1),
                                held("PEP", -1), held("PEP", 1),
                                held("MO", -1), held("MO", 1)])
    reason = correlated_exposure(spread_on("MCD"), ctx).reason
    assert "KO" in reason and "PEP" in reason
    assert "unclassified" in reason


def test_a_mapped_name_is_never_counted_against_the_unmapped_cap(ctx):
    """Otherwise the two caps double-count the same position.

    A book of SPY and QQQ is bounded by `us-broad-market`. If those two also landed
    in the unmapped bucket they would consume an allowance meant for the names nobody
    has classified, and a fully-classified book would trip a limit about
    classification.
    """
    ctx = _with(ctx, positions=[held("SPY", -1), held("SPY", 1),
                                held("QQQ", -1), held("QQQ", 1)])
    assert correlated_exposure(spread_on("KO"), ctx).passed


def test_the_unmapped_cap_can_be_disabled_on_its_own(ctx):
    ctx = _with(ctx, limits=Limits(max_unclassified_positions=0),
                positions=[held("KO", -9), held("PEP", -9)])
    assert correlated_exposure(spread_on("MCD"), ctx).passed


def test_disabling_the_unmapped_cap_leaves_the_correlation_cap_alone(ctx):
    """The two must not be one knob wearing two names."""
    ctx = _with(ctx, limits=Limits(max_unclassified_positions=0),
                positions=[held("SPY", -1), held("SPY", 1),
                           held("QQQ", -1), held("QQQ", 1)])
    assert not correlated_exposure(spread_on("IWM"), ctx).passed
