"""The agent's brain regions, held to what they claim.

`agent/` was eleven flat modules doing four unrelated jobs, and the layout said none
of it: a survival reflex, a reasoning stage, a memory and a body clock sat as
siblings. The regions are the fix, and they are worth exactly as much as their
membership is accurate — a `ledger.py` that drifts into `cortex/` leaves four
directories that look like an architecture and describe nothing.

The naming follows HAL, which solved this in the same problem domain. That lineage is
already in the code: `cortex/committee.py` opens by saying it was adapted from HAL's
`cortex.committee`, a fact the flat directory could not carry.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parents[2] / "src" / "halstreet" / "agent"

#: What each region is for, and the modules that answer that question. The mapping is
#: written out rather than derived from the tree: a test that reads the directory to
#: learn what is in it agrees with any arrangement, including a wrong one.
REGIONS = {
    "cortex": {"llm", "committee", "proposal"},
    "cerebellum": {"loop", "manager"},
    "brainstem": {"schedule", "lock", "breaker"},
    "hippocampus": {"ledger", "soak"},
}

#: The entrypoint. Outside every region, as HAL keeps `server.py` outside its own.
FLAT = {"run"}

#: A reflex may not wait for deliberation. `brainstem/` is the three modules that stop
#: the organism — a drawdown halt, a second process, the closing bell — and none of
#: them consults anything: a daily-loss breaker that imported the committee would be a
#: kill switch with an opinion, and it would be slower than the thing it exists to stop.
FORBIDDEN_EDGES = {("brainstem", "cortex"), ("brainstem", "cerebellum")}


def _modules(region: str) -> set[str]:
    return {p.stem for p in (AGENT / region).glob("*.py") if p.stem != "__init__"}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


# --- membership ---------------------------------------------------------------


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_every_region_holds_exactly_what_it_claims(region):
    assert _modules(region) == REGIONS[region]


def test_no_module_is_left_outside_a_region():
    """The failure this file exists for, and it arrives one file at a time.

    A module dropped at the top of `agent/` is not a small untidiness — it is the
    next reader learning that the regions are optional, which is how four
    directories become decoration.
    """
    loose = {p.stem for p in AGENT.glob("*.py") if p.stem != "__init__"}
    assert loose == FLAT, f"modules outside a region: {sorted(loose - FLAT)}"


def test_the_entrypoint_did_not_move():
    """`python -m halstreet.agent.run` is in start.sh, the README and the docs.

    Renaming it costs every one of those and buys nothing: it is the one module in
    here that is not a region's work, it is the process itself.
    """
    assert (AGENT / "run.py").is_file()


def test_no_module_appears_in_two_regions():
    seen: dict[str, str] = {}
    for region, modules in REGIONS.items():
        for module in modules:
            assert module not in seen, f"{module} is claimed by {seen[module]} and {region}"
            seen[module] = region


# --- the regions say what they are for ----------------------------------------


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_a_region_declares_what_it_is_for(region):
    """An undocumented region is a folder with a biology word on it.

    The metaphor only pays if a reader can answer "does this belong here" without
    opening the modules — which means each `__init__.py` states the question the
    region answers and what it refuses.
    """
    doc = ast.get_docstring(ast.parse((AGENT / region / "__init__.py").read_text()))
    assert doc, f"{region}/__init__.py has no docstring"
    assert len(doc.split()) >= 40, f"{region} is named and not explained"


@pytest.mark.parametrize("region", sorted(REGIONS))
def test_a_region_names_what_does_not_belong_in_it(region):
    """The half that stops the metaphor stretching.

    Every module fits *somewhere* if the only guidance is what a region holds. What
    settles an argument is the sentence saying what it does not.
    """
    doc = ast.get_docstring(ast.parse((AGENT / region / "__init__.py").read_text())) or ""
    assert "Not here" in doc, f"{region} does not say what it excludes"


# --- the traffic between them -------------------------------------------------


@pytest.mark.parametrize(("frm", "to"), sorted(FORBIDDEN_EDGES))
def test_a_reflex_does_not_wait_for_deliberation(frm, to):
    offenders = []
    for path in (AGENT / frm).glob("*.py"):
        if any(m.startswith(f"halstreet.agent.{to}") for m in _imports(path)):
            offenders.append(path.name)
    assert not offenders, f"{frm}/ imports {to}/: {offenders}"


def test_no_region_imports_the_old_flat_paths():
    """A missed rewrite that a stale `__pycache__` would happily satisfy."""
    stale = []
    for path in AGENT.rglob("*.py"):
        for module in _imports(path):
            tail = module.removeprefix("halstreet.agent.")
            if module.startswith("halstreet.agent.") and tail.split(".")[0] in (
                    *REGIONS, *FLAT):
                continue
            if module.startswith("halstreet.agent.") :
                stale.append(f"{path.name} -> {module}")
    assert not stale, f"imports that no longer exist: {stale}"


def test_the_target_dte_comes_from_the_config_when_no_flag_says_otherwise():
    """`--dte` follows $TARGET_DTE, the way --universe follows $UNIVERSE.

    Without this the window was the one operational setting that could only be changed
    by editing a launcher, and `start.sh` does not pass it. A profile with a short band
    would then be driven by the 45 baked into the parser and silently clamped to its
    ceiling — the right answer by accident, and only ever the ceiling.
    """
    from halstreet.agent.run import target_dte_from

    assert target_dte_from(0, {"TARGET_DTE": "14"}) == 14
    # The flag still wins, because a flag is somebody typing it just now.
    assert target_dte_from(30, {"TARGET_DTE": "14"}) == 30
    # And with neither, the long-standing default.
    assert target_dte_from(0, {}) == 45
