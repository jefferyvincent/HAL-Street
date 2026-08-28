"""The boundary between a command and the code it runs.

`src/halstreet/CLAUDE.md`, rule 1: `scripts/` parses arguments, `halstreet/cli/`
holds the parser and the printing, and the decision lives in a domain package. This
file is what makes that a rule rather than a preference.

It is worth a test because the drift is invisible and one-way. A helper added to a
script is easier than a module in the moment, and nothing complains — until the test
that needs it has to load the file through `importlib.util.spec_from_file_location`,
which is exactly how `scripts/soak.py` came to hold the coverage logic with no test on
the table it printed, and how `scripts/verify_multileg.py` came to carry a second OCC
parser for months after the real one landed.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = ROOT / "src" / "halstreet" / "cli"
PACKAGE = ROOT / "src" / "halstreet"

SHIMS = sorted(p for p in SCRIPTS.glob("*.py"))
CLI_MODULES = sorted(p for p in CLI.glob("*.py") if p.name != "__init__.py")

#: The two files in the package allowed to print. Neither is a domain module:
#: `agent/run.py` is the loop's own entrypoint, and `telemetry/server.py` says once,
#: at startup, that `dist/` is unbuilt — a fact the browser could only report as a 503.
MAY_PRINT = {"agent/run.py", "telemetry/server.py"}
#: The only entrypoint outside `cli/`. `./start.sh` dispatches to it directly.
MAY_PARSE_ARGS = {"agent/run.py"}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _imported_modules(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


# --- scripts/ is a shim and nothing else --------------------------------------


def test_there_is_at_least_one_script_to_check():
    # A glob that matches nothing passes every parametrized test below silently.
    assert SHIMS


@pytest.mark.parametrize("path", SHIMS, ids=lambda p: p.name)
def test_a_script_defines_no_functions_or_classes(path):
    """The rule, stated where it can fail.

    Anything worth defining is worth importing, and a definition here is unreachable
    from the suite without import machinery.
    """
    defined = [n.name for n in _tree(path).body
               if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)]
    assert not defined, f"{path.name} defines {defined}; move them into halstreet/"


@pytest.mark.parametrize("path", SHIMS, ids=lambda p: p.name)
def test_a_script_imports_only_its_cli_module(path):
    imported = _imported_modules(_tree(path))
    assert imported, f"{path.name} imports nothing — it cannot be delegating"
    assert all(m.startswith("halstreet.cli.") for m in imported), \
        f"{path.name} imports {imported}; a shim delegates and does not assemble"


@pytest.mark.parametrize("path", SHIMS, ids=lambda p: p.name)
def test_a_script_delegates_to_a_main_that_exists(path):
    """Named, imported and called — the whole file, checked end to end."""
    (module,) = _imported_modules(_tree(path))
    assert hasattr(importlib.import_module(module), "main")
    assert "main()" in path.read_text()


@pytest.mark.parametrize("path", SHIMS, ids=lambda p: p.name)
def test_a_script_stays_short_enough_to_read_at_a_glance(path):
    # Not a style rule. A shim long enough to skim is long enough to hide a decision.
    assert len(path.read_text().splitlines()) <= 15


# --- cli/ modules are entrypoints ---------------------------------------------


@pytest.mark.parametrize("path", CLI_MODULES, ids=lambda p: p.stem)
def test_every_cli_module_exposes_main(path):
    module = importlib.import_module(f"halstreet.cli.{path.stem}")
    assert callable(module.main)


@pytest.mark.parametrize("path", CLI_MODULES, ids=lambda p: p.stem)
def test_every_cli_module_builds_its_parser_separately_from_running(path):
    """`build_parser()` is what lets a test read the flags without executing anything.

    `--help` and the defaults are part of the contract — `--journal` defaulting to the
    wrong account's file is the bug the soak harness exists for — and a parser
    assembled inside `main()` can only be checked by running the command.
    """
    module = importlib.import_module(f"halstreet.cli.{path.stem}")
    assert callable(module.build_parser)
    assert module.build_parser().parse_known_args([])


# --- the dependency runs one way ----------------------------------------------


def test_no_domain_module_imports_the_cli_package():
    """The layering, in the direction that actually breaks.

    A domain module reaching into `cli/` for a helper drags argparse and stdout into
    the gates' import graph, and makes the thing it wanted impossible to test without
    a parser.
    """
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.is_relative_to(CLI):
            continue
        if any(m.startswith("halstreet.cli") for m in _imported_modules(_tree(path))):
            offenders.append(_rel(path))
    assert not offenders, f"these import halstreet.cli: {offenders}"


def test_only_entrypoints_parse_arguments():
    offenders = [
        _rel(p) for p in PACKAGE.rglob("*.py")
        if not p.is_relative_to(CLI)
        and _rel(p) not in MAY_PARSE_ARGS
        and "argparse" in _imported_modules(_tree(p))
    ]
    assert not offenders, f"argparse outside an entrypoint: {offenders}"


def test_a_domain_module_returns_its_text_rather_than_printing_it():
    """Why `soak.render()` returns a string and `cli/soak.py` prints it.

    A function that prints can only be asserted on through captured stdout, which is
    how the coverage table went untested while being the soak's entire output.
    """
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.is_relative_to(CLI) or _rel(path) in MAY_PRINT:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, f"print() outside cli/: {offenders}"


# --- start.sh agrees with the package -----------------------------------------


def _dispatched_modules() -> set[str]:
    return set(re.findall(r"-m (halstreet[\w.]+)", (ROOT / "start.sh").read_text()))


def test_every_module_start_dispatches_to_is_importable_and_runnable():
    """The launcher's half of Article VII: a mode that cannot run must not be offered.

    `python -m halstreet.cli.typo` fails with a bare "No module named", after the
    environment check has already told the user everything is fine.
    """
    dispatched = _dispatched_modules()
    assert dispatched, "start.sh dispatches to no python modules"
    for name in sorted(dispatched):
        module = importlib.import_module(name)
        assert hasattr(module, "main"), f"{name} has no main()"


def test_start_no_longer_runs_scripts_by_path_or_as_a_namespace_package():
    """`python -m scripts.report` only ever worked by implicit namespace package.

    `scripts/` has no `__init__.py`, so that dispatch depended on the working
    directory being the repo root and on nothing else on the path being called
    `scripts`. Every mode now names a real installed module.
    """
    text = (ROOT / "start.sh").read_text()
    body = text[text.index('case "$MODE" in'):]
    assert "-m scripts." not in body
    assert "scripts/" not in body


def test_every_cli_module_is_reachable_from_start_or_a_script():
    """A command nobody can type is a command nobody maintains."""
    dispatched = _dispatched_modules()
    shimmed = {m for p in SHIMS for m in _imported_modules(_tree(p))}
    for path in CLI_MODULES:
        name = f"halstreet.cli.{path.stem}"
        assert name in dispatched or name in shimmed, f"{name} has no entrypoint"
