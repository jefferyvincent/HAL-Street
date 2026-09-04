"""The method's own scaffolding, checked against itself.

`CLAUDE.md`, the constitution, the phase commands and the BMAD personas are
instructions that another agent reads and follows. They rot the way `docs/WRITEUP.md`
rotted: a renamed file, a command that points at a template nobody wrote, a persona
whose name no longer matches its filename. Nothing errors — the instruction is simply
followed into a dead end, or silently not followed at all.

Prose is not pinned here and should not be. What is pinned is every *pointer*: a
cross-reference, a filename, a phase that claims a command, an article that claims a
check. Those are the parts that stop being true when the repo moves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION = ROOT / ".specify" / "memory" / "constitution.md"
TEMPLATES = ROOT / ".specify" / "templates"
COMMANDS = ROOT / ".claude" / "commands"
AGENTS = ROOT / ".claude" / "agents"
SPECS = ROOT / "specs"

RULE_FILES = [
    ROOT / "CLAUDE.md",
    ROOT / "src" / "halstreet" / "CLAUDE.md",
    ROOT / "apps" / "desktop" / "CLAUDE.md",
]

#: The six phases. Each is a slash command and each has a hat that runs it.
PHASES = {
    "specify": ("analyst", "pm"),
    "plan": ("architect",),
    "tasks": ("sm",),
    "story": ("sm",),
    "implement": ("dev",),
    "qa": ("qa",),
}

_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _frontmatter(path: Path) -> dict[str, str]:
    m = _FRONTMATTER.match(path.read_text())
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


# --- the rule files exist and point at each other -----------------------------


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_rule_file_exists(path):
    assert path.is_file(), f"{path} is referenced as authoritative and is not there"


def test_the_root_file_routes_to_both_surfaces_and_the_constitution():
    """It is the only one loaded automatically, so what it fails to name is invisible."""
    text = (ROOT / "CLAUDE.md").read_text()
    assert "src/halstreet/CLAUDE.md" in text
    assert "apps/desktop/CLAUDE.md" in text
    assert ".specify/memory/constitution.md" in text


@pytest.mark.parametrize(
    "path",
    [*RULE_FILES, CONSTITUTION, *sorted(COMMANDS.glob("*.md")), *sorted(AGENTS.glob("*.md"))],
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_every_repo_link_in_the_method_resolves(path):
    """A dead pointer in an instruction is worse than a dead link in prose.

    Prose gets skimmed; an instruction gets followed. "Read the rules in X" where X
    does not exist produces work done under no rules at all, and nothing anywhere
    reports it.
    """
    broken = []
    for target in _LINK.findall(path.read_text()):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            broken.append(target)
    assert not broken, f"{path.name} links to missing files: {broken}"


# --- the constitution ---------------------------------------------------------


def test_the_constitution_numbers_its_articles_in_order():
    """Plans cite articles by number. A gap or a repeat makes a citation ambiguous."""
    found = re.findall(r"^## ([IVX]+)\. ", CONSTITUTION.read_text(), re.MULTILINE)
    expected = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    assert found == expected


def test_every_article_says_what_it_costs_or_what_enforces_it():
    """An article with no consequence attached is a slogan, and gets treated as one."""
    body = CONSTITUTION.read_text().split("## I.", 1)[1]
    sections = re.split(r"^## ", body, flags=re.MULTILINE)
    thin = [s.splitlines()[0] for s in sections if len(s.split()) < 40]
    assert not thin, f"articles with no substance behind them: {thin}"


def test_the_plan_template_checks_the_articles_a_plan_can_violate():
    """Article X is standing rather than per-plan; the other nine are checkable."""
    template = (TEMPLATES / "plan-template.md").read_text()
    for numeral in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"):
        assert re.search(rf"^\| {numeral}\. ", template, re.MULTILINE), \
            f"the Constitution Check omits article {numeral}"


# --- commands and personas ----------------------------------------------------


@pytest.mark.parametrize("phase", sorted(PHASES), ids=sorted(PHASES))
def test_every_phase_has_a_command(phase):
    path = COMMANDS / f"{phase}.md"
    assert path.is_file(), f"/{phase} is named in CLAUDE.md and has no command file"
    assert _frontmatter(path).get("description"), f"/{phase} has no description"


@pytest.mark.parametrize(
    "hat", sorted({h for hats in PHASES.values() for h in hats}))
def test_every_hat_named_by_a_phase_is_a_real_agent(hat):
    path = AGENTS / f"{hat}.md"
    assert path.is_file(), f"the method names the {hat} hat and no such agent exists"


@pytest.mark.parametrize("path", sorted(AGENTS.glob("*.md")), ids=lambda p: p.stem)
def test_an_agent_is_addressable_by_its_filename(path):
    """The name in the frontmatter is the address. A mismatch is an agent nobody calls."""
    front = _frontmatter(path)
    assert front.get("name") == path.stem, f"{path.name} declares name={front.get('name')!r}"
    assert front.get("description"), f"{path.name} has no description"
    assert front.get("tools"), f"{path.name} declares no tools"


@pytest.mark.parametrize("path", sorted(COMMANDS.glob("*.md")), ids=lambda p: p.stem)
def test_every_template_a_command_names_exists(path):
    named = re.findall(r"`?\.specify/templates/([\w-]+\.md)`?", path.read_text())
    for name in named:
        assert (TEMPLATES / name).is_file(), f"/{path.stem} names a missing template: {name}"


def test_the_root_file_names_every_command_it_ships():
    text = (ROOT / "CLAUDE.md").read_text()
    for path in sorted(COMMANDS.glob("*.md")):
        assert f"/{path.stem}" in text, f"/{path.stem} exists and the method never mentions it"


# --- specs --------------------------------------------------------------------


def _spec_dirs() -> list[Path]:
    return sorted(p for p in SPECS.iterdir() if p.is_dir()) if SPECS.exists() else []


def test_there_is_a_worked_example_to_follow():
    # A method with no example in the repo is a method nobody has run.
    assert _spec_dirs(), "specs/ holds no feature; the method has never been used here"


@pytest.mark.parametrize("spec_dir", _spec_dirs(), ids=lambda p: p.name)
def test_every_spec_directory_is_numbered_and_has_a_spec(spec_dir):
    assert re.match(r"^\d{3}-[a-z0-9-]+$", spec_dir.name), \
        f"{spec_dir.name} does not follow NNN-kebab-slug"
    assert (spec_dir / "spec.md").is_file()


@pytest.mark.parametrize("spec_dir", _spec_dirs(), ids=lambda p: p.name)
def test_a_plan_records_a_constitution_verdict(spec_dir):
    """The gate is the plan's reason to exist. Skipping it makes it a to-do list."""
    plan = spec_dir / "plan.md"
    if not plan.is_file():
        pytest.skip("not planned yet")
    text = plan.read_text()
    assert "## Constitution Check" in text
    assert re.search(r"^\*\*Verdict:\*\* (pass|pass with noted deviation|blocked)",
                     text, re.MULTILINE), "the Constitution Check records no verdict"


@pytest.mark.parametrize("spec_dir", _spec_dirs(), ids=lambda p: p.name)
def test_a_deviation_is_explained_rather_than_asserted(spec_dir):
    """`pass with noted deviation` is only meaningful if the note is there."""
    plan = spec_dir / "plan.md"
    if not plan.is_file() or "noted deviation" not in plan.read_text():
        pytest.skip("no deviation claimed")
    after = plan.read_text().split("**Verdict:**", 1)[1]
    assert len(after.split()) > 60, "a deviation is claimed and never explained"


def _stories() -> list[Path]:
    return sorted(SPECS.glob("*/stories/*.md"))


@pytest.mark.parametrize("story", _stories(), ids=lambda p: p.stem)
def test_a_story_carries_its_own_context(story):
    """BMAD's one rule, and the only part of it a test can hold.

    A story that says "see the plan" works exactly as long as the conversation that
    produced it is still on screen.
    """
    text = story.read_text().lower()
    for phrase in ("see the plan above", "as discussed above", "see above", "as mentioned"):
        assert phrase not in text, f"{story.name} refers outward: {phrase!r}"
    for heading in ("## context", "## acceptance criteria", "## files", "## test first"):
        assert heading in text, f"{story.name} is missing {heading}"


@pytest.mark.parametrize("story", _stories(), ids=lambda p: p.stem)
def test_a_story_names_files_that_exist(story):
    """A story pointing at a path nobody wrote sends the next reader looking for it."""
    missing = []
    for path in re.findall(r"^\| `([^`]+)` \|", story.read_text(), re.MULTILINE):
        if not (ROOT / path).exists():
            missing.append(path)
    assert not missing, f"{story.name} names files that are not there: {missing}"
