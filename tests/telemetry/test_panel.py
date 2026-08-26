"""The panel app: it can only read, and it cannot advertise what it lacks.

`test_server.py` proves the *server* has no write route and that the socket never
reads. This file covers the other three surfaces — the React sources, the Tauri shell,
and the shape the project asked the frontend to keep. All of it matters for the same
reason: a dashboard that can trade is a second path to the broker that does not go
through `gates/`, and the whole argument of this project is that there is exactly one
such path.

The navigation tests exist because of a real defect. The chrome bar once shipped
JOURNAL and GATES drawn as tabs, styled clickable, wired to nothing. They came from
the design mockup, where those screens existed; the implementation had only the
console. A control that looks live and is not is the same class of lie as a button
claiming to place an order, and it is the kind that survives review because it looks
finished.

These read the sources rather than running them. That is a real limit — they cannot
catch a logic error — and a deliberate trade: the invariants here are structural
("this call does not appear", "this view is reachable"), they hold for the whole tree
rather than one code path, and they run in the Python suite with no browser, so they
cannot be the thing that gets skipped on competition day.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "apps" / "desktop"
SRC = APP / "src"
TAURI = APP / "src-tauri"


def sources(*globs: str) -> dict[Path, str]:
    out: dict[Path, str] = {}
    for g in globs:
        for f in sorted(SRC.glob(g)):
            out[f] = f.read_text()
    return out


@pytest.fixture(scope="module")
def ts() -> dict[Path, str]:
    """Every TypeScript source in the app."""
    return sources("**/*.ts", "**/*.tsx")


def rel(p: Path) -> str:
    return str(p.relative_to(APP))


# --- the client can only read -------------------------------------------------

@pytest.mark.parametrize("write", [
    "XMLHttpRequest",   # the older way to send one
    "sendBeacon",       # fire-and-forget, easy to miss in review
    "<form",            # submits with no JavaScript at all
    "method:",          # fetch(url, {method: "POST"})
    '"POST"',
])
def test_the_client_has_no_way_to_send_a_request(ts: dict[Path, str], write: str):
    hits = [rel(f) for f, body in ts.items() if write in body]
    assert not hits, f"{write} would give the panel a write path: {hits}"


def test_the_socket_is_never_written_to(ts: dict[Path, str]):
    """The mirror of the server's guarantee, on this side.

    The server never reads the socket, so a frame sent from here would land nowhere —
    but a `send` in the client is still the first half of a write path, and the second
    half is one line of Python away. Neither end has the code, and that is the point.
    """
    for f, body in ts.items():
        assert not re.search(r"\bsocket\.send\b|\bws\.send\b", body), \
            f"{rel(f)} writes to the socket"


def test_every_fetch_is_a_plain_get(ts: dict[Path, str]):
    calls = [(f, m.group(1)) for f, body in ts.items()
             for m in re.finditer(r"fetch\(([^)]*)\)", body)]
    assert calls, "the panel must still fetch, or this test proves nothing"
    for f, call in calls:
        assert "method" not in call, f"{rel(f)}: fetch with an explicit method — {call}"


# --- it cannot advertise what it lacks ----------------------------------------

def views() -> set[str]:
    return {f.stem for f in (SRC / "views").glob("*View.tsx")}


def tabs() -> set[str]:
    block = re.search(r"const VIEW_KEYS[^;]+;", (SRC / "hooks" / "useShortcuts.ts").read_text())
    assert block, "useShortcuts no longer declares VIEW_KEYS — this test has drifted"
    return set(re.findall(r'"(\w+)"(?=\s*[,}])', block.group(0)))


def test_every_view_is_reachable_and_every_route_has_a_view():
    """Both directions. An unreachable view is as dead as a tab that goes nowhere."""
    routed = set(re.findall(r"^\s*(\w+): (\w+View),", (SRC / "App.tsx").read_text(), re.MULTILINE))
    names = {view for _, view in routed}
    keys = {key for key, _ in routed}

    assert names == views(), f"views/ and App's route table disagree: {names ^ views()}"
    assert keys == tabs(), f"routes and keyboard shortcuts disagree: {keys ^ tabs()}"

    listed = set(re.findall(r'export \{ (\w+) \}', (SRC / "views" / "index.ts").read_text()))
    assert listed == views(), f"views/index.ts is out of date: {listed ^ views()}"


def test_the_tab_ids_are_the_view_ids():
    """The chrome bar builds its tabs from the same names App routes on."""
    source = (SRC / "hooks" / "useTabs.ts").read_text()
    ids = set(re.findall(r'\["(\w+)", "[A-Z]+", ICON\.\w+\]', source))
    assert ids == tabs(), f"chrome bar tabs and routes disagree: {ids ^ tabs()}"


def test_the_footer_advertises_only_shortcuts_that_are_bound():
    """The same rule as the tabs, for the keyboard: no key drawn that does nothing."""
    footer = (SRC / "components" / "StatusBar.tsx").read_text()
    advertised = set(re.findall(r'text-amber">([A-Z0-9])</b>', footer))
    handler = (SRC / "hooks" / "useShortcuts.ts").read_text()
    bound = {k.upper() for k in re.findall(r'e\.key === "(\w)"', handler)}
    bound |= set(re.findall(r'"(\d)":', handler))
    assert advertised <= bound, f"footer advertises unbound key(s): {advertised - bound}"


# --- the shape the project asked for ------------------------------------------

def test_views_live_in_views(ts: dict[Path, str]):
    misplaced = [rel(f) for f in ts if f.name.endswith("View.tsx") and f.parent != SRC / "views"]
    assert not misplaced, f"views belong in src/views/: {misplaced}"


def test_business_logic_stays_out_of_the_markup():
    """JSX renders; hooks and lib decide.

    The check is narrow on purpose — it looks for the two things that actually crept
    in before: array reordering and reduction done inline in a component, which is
    where a render-order bug hides, and derived state computed per render instead of
    memoised in a hook.
    """
    for f in sorted((SRC / "views").glob("*.tsx")) + sorted((SRC / "components").glob("*.tsx")):
        body = f.read_text()
        for smell in (".reverse()", ".reduce(", ".sort("):
            assert smell not in body, f"{rel(f)}: {smell} belongs in a hook or lib/, not in JSX"


def test_hooks_are_hooks_and_stores_are_stores():
    for f in (SRC / "hooks").glob("*.ts"):
        assert f.name.startswith("use"), f"{rel(f)} is in hooks/ but is not one"
        assert "export function use" in f.read_text() or "export const use" in f.read_text()
    # lib/ is the pure layer: no React at all, so it stays testable and reusable.
    for f in (SRC / "lib").glob("*.ts"):
        assert "from \"react\"" not in f.read_text(), f"{rel(f)} imports React; lib/ must stay pure"


def test_user_facing_copy_lives_in_the_strings_file():
    """No sentence hardcoded in a component.

    Beyond translation, this keeps the panel's claims reviewable in one file — the
    lines that say there is no override, that limits are not editable here, that exits
    are never blocked. Those are promises about behaviour, and they should be read
    together rather than found nine components apart.
    """
    strings = (SRC / "constants" / "strings.ts").read_text()
    for f in sorted((SRC / "views").glob("*.tsx")) + sorted((SRC / "components").glob("*.tsx")):
        body = f.read_text()
        # A run of words between JSX tags is prose; short tokens and punctuation are not.
        prose = [m.group(1).strip() for m in re.finditer(r">([A-Za-z][A-Za-z ,.'\-]{14,})<", body)]
        assert not prose, f"{rel(f)} hardcodes copy: {prose} — put it in constants/strings.ts"
    assert "noOverride" in strings and "limitsNote" in strings


def test_the_palette_is_declared_once():
    """Colours come from the theme tokens or the constants that mirror them.

    Tailwind arbitrary values (`shadow-[inset_2px_0_0_#21d07a]`) are exempt: they are
    compiled utilities, not JavaScript, and Tailwind cannot read a CSS variable there.
    """
    for f in sorted((SRC / "views").glob("*.tsx")) + sorted((SRC / "components").glob("*.tsx")):
        body = re.sub(r"\[[^\]\s]*\]", "", f.read_text())  # drop Tailwind arbitrary values
        loose = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
        assert not loose, f"{rel(f)} has a loose colour {loose} — use constants/theme.ts"


# --- the desktop shell adds no privilege --------------------------------------

def test_the_tauri_shell_exposes_no_commands():
    """Tauri's appeal is a bridge to native code, and that bridge is what this must not
    have: a command here is a path from a button to the host process, and from there to
    the broker, that does not pass through gates/."""
    # Comments stripped first: lib.rs explains at length that it has no commands, and
    # naming the thing you refuse is not the same as doing it. Same reason the server's
    # send-only test parses an AST instead of grepping.
    rust = "\n".join(f.read_text() for f in (TAURI / "src").glob("*.rs"))
    code = "\n".join(re.sub(r"//.*", "", line) for line in rust.splitlines())
    assert "#[tauri::command]" not in code
    assert "invoke_handler" not in code


def test_the_desktop_build_has_no_capability_the_browser_lacks():
    caps = json.loads((TAURI / "capabilities" / "default.json").read_text())
    assert caps["permissions"] == ["core:default"], caps["permissions"]


def test_the_shell_can_only_reach_localhost():
    conf = json.loads((TAURI / "tauri.conf.json").read_text())
    csp = conf["app"]["security"]["csp"]
    assert csp, "a null CSP would let the shell reach anything"
    connect = re.search(r"connect-src ([^;]+)", csp).group(1).split()
    assert all(h == "'self'" or "127.0.0.1" in h for h in connect), connect
