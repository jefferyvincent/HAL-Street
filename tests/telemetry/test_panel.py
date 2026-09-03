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
    """The digit-to-view map, from the one file that declares it.

    It moved out of `useShortcuts` when the footer started reading it too: the legend
    and the binding were two hand-kept lists, so a key could be advertised after it
    stopped working. One constant, both callers.
    """
    block = re.search(r"const VIEW_KEYS[^;]+;", (SRC / "constants" / "keys.ts").read_text())
    assert block, "constants/keys.ts no longer declares VIEW_KEYS — this test has drifted"
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
    ids = set(re.findall(r'\["(\w+)", ICON\.\w+\]', source))
    assert ids, "useTabs no longer lists its tabs this way — this test has drifted"
    assert ids == tabs(), f"chrome bar tabs and routes disagree: {ids ^ tabs()}"


def test_the_footer_advertises_only_shortcuts_that_are_bound():
    """The same rule as the tabs, for the keyboard: no key drawn that does nothing.

    Enforced by construction now rather than by comparing two lists: the legend and
    the handler both read `constants/keys.ts`, so neither can spell a key of its own.
    Checking that they still do is what keeps the guarantee — a footer that goes back
    to printing "J" in its markup is a footer that can outlive its binding.
    """
    legend = (SRC / "hooks" / "useShortcutLegend.ts").read_text()
    handler = (SRC / "hooks" / "useShortcuts.ts").read_text()
    footer = (SRC / "components" / "StatusBar.tsx").read_text()

    for name, body in (("the legend", legend), ("the handler", handler)):
        assert "KEY." in body and "VIEW_KEYS" in body, f"{name} no longer reads constants/keys.ts"
        assert not re.search(r'"[A-Za-z0-9]"', body), f"{name} spells a key of its own"

    assert not re.search(r"<b[^>]*>[A-Z0-9]</b>", footer), "the footer draws a key of its own"
    assert "useShortcutLegend" in footer, "the footer no longer reads the bound keys"


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


def test_no_word_reaches_the_screen_outside_the_string_table():
    """Rule 3 of `apps/desktop/CLAUDE.md`, enforced where the eye cannot see it.

    A literal in JSX is easy to spot in review. A literal handed to a *library* is
    not: `createPriceLine({title: "LIVE"})` draws a word on the chart axis from
    inside a hook, where nothing that reads like markup appears. That one survived a
    full pass over every component precisely because it did not look like a string
    being rendered.

    Narrow on purpose — `title:` is the property that reaches a user in both places
    it is used here (the chart's price-line labels and the DOM's tooltip). A word
    spelled at either is a word no `locales/*.json` can translate.
    """
    offenders = []
    for f in sorted((SRC / "hooks").glob("*.ts")) + \
             sorted((SRC / "components").glob("*.tsx")) + \
             sorted((SRC / "views").glob("*.tsx")):
        for m in re.finditer(r'title:\s*"([^"]+)"', f.read_text()):
            offenders.append(f'{rel(f)}: title: "{m.group(1)}"')
    assert not offenders, (
        "user-facing words outside the string table — they must come from "
        f"useStrings(): {offenders}"
    )


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


# --- a click has to do something visible -------------------------------------------

def test_selecting_a_record_also_shows_it():
    """The regression the accordion introduced.

    Collapsing the decision record by default was right — it is a rationale and
    sixteen verdicts sitting under the run's numbers, the equity curve and the open
    book. But the run journal and the JOURNAL tab both selected a record and left
    it closed, so clicking a row changed a selection nobody could see and read as a
    dead control.

    Choosing a thing and looking at it are one action here.
    """
    store = (SRC / "stores" / "ui.ts").read_text()
    assert "showDecision" in store, "no action selects and opens together"
    action = store[store.index("showDecision: (selected)"):]
    assert "decisionOpen: true" in action[:200], "selecting must open the record"

    # The *call site*, not the presence of the name — a mutation that changed the
    # handler back to a bare `select` left the import untouched and walked straight
    # through an earlier version of this check.
    #
    # Searched across the panel rather than in two named files. Both places that bind
    # this have since moved once — the tape's row handler into a hook — and naming the
    # file made the test fail on a refactor that changed nothing about the behaviour.
    # What must hold is that every binding of `showDecision` is also called.
    bound = 0
    for path in SRC.rglob("*.ts*"):
        source = path.read_text()
        for handler in re.finditer(r"const (\w+) = useUI\(\(s\) => s\.showDecision\)",
                                   source):
            bound += 1
            name = handler.group(1)
            after = source[handler.end():]
            # Called here, or handed out by a hook for its consumer to call. Both are
            # a binding that goes somewhere; only a binding that goes nowhere is the
            # dead control this test exists for.
            used = re.search(rf"\b{name}\(", after) or re.search(
                rf"return \{{[^}}]*\b{name}\b", after)
            assert used, f"{path.name} binds showDecision and neither calls nor returns it"
    assert bound >= 2, (
        f"only {bound} place(s) select a record; the tape and the journal both should"
    )


def test_no_view_calls_a_selector_the_store_no_longer_has():
    # `open` was superseded by `showDecision` and removed. A view still calling it
    # would be a runtime error on click, which is exactly the failure this whole
    # test exists for.
    store = (SRC / "stores" / "ui.ts").read_text()
    # The implementation object only. The interface above it declares the same names,
    # so searching the whole file finds a removed action's *type* and passes.
    body = store[store.index("export const useUI = create<UI>"):]
    provided = set(re.findall(r"^\s{2}(\w+):", body, re.MULTILINE))
    for path in SRC.rglob("*.tsx"):
        for used in re.findall(r"useUI\(\(s\) => s\.(\w+)\)", path.read_text()):
            assert used in provided, \
                f"{path.name} reads useUI().{used}, which the store does not provide"


def test_a_row_can_reach_the_trade_it_became():
    """The run journal shows the verdict; the position is two views away otherwise,
    and nothing said the two were the same trade.

    Scanned across the tape and whatever hook feeds it, because the row-building moved
    into one and naming the component made this fail on a refactor that changed
    nothing a reader would see.
    """
    tape = "\n".join(p.read_text() for p in SRC.rglob("*.ts*")
                     if "Tape" in p.name or "useDecisions" in p.name)
    assert "structure_id" in tape, "a row carries no handle to its position"
    assert "chart(" in tape, "and nothing takes the reader to it"


def test_the_price_scale_is_a_control_rather_than_a_decision():
    """Both scalings are wanted and they cannot both be the default.

    Scaling to the levels pulls a stop three times the credit away into view and
    flattens every candle; scaling to the price draws the candles properly and puts
    the stop off the bottom. The first made the chart unreadable, the second made
    someone ask where their stop had gone. So it is a toggle, and a level the drawn
    range does not reach is *named* rather than silently absent — otherwise there is
    no way to tell "no stop" from "stop somewhere below".
    """
    store = (SRC / "stores" / "ui.ts").read_text()
    assert "chartFit" in store and "toggleFit" in store
    # Levels by default. Scaling to the candles draws them beautifully and puts the
    # stop off the bottom, and the stop is the first thing anyone opening a position
    # chart looks for — losing it is worse than a compressed body.
    assert 'chartFit: "working"' in store, \
        "the default must show the price with the levels that can sit beside it"

    canvas = (SRC / "hooks" / "useStructureChartCanvas.ts").read_text()
    # The default keeps only levels within one candle-range of the price. Including
    # everything is geometry rather than preference: measured on a live QQQ spread,
    # the stop sits four ranges away and takes the candles from 69% of the height to
    # 18%. Entry and target cost nothing and stay.
    assert "v >= floor - span && v <= ceiling + span" in canvas, \
        "the default scale does not filter distant levels"
    assert 'fit === "levels"' in canvas, "the toggle must still be able to add them"

    chart = (SRC / "components" / "StructureChart.tsx").read_text()
    assert "toggleFit" in chart, "the toggle is not reachable"
    assert "offscreen" in chart, "an unreachable level must say so"

    canvas = (SRC / "hooks" / "useStructureChartCanvas.ts").read_text()
    assert 'fit === "levels"' in canvas, "the canvas ignores the setting"


def test_the_forming_candle_is_drawn_differently_and_moves():
    # Hollow, so it reads as unfinished rather than as a fifth interpretation of
    # green and red — and extended by the live mark, or it draws a body excluding a
    # price the structure is at right now.
    canvas = (SRC / "hooks" / "useStructureChartCanvas.ts").read_text()
    assert "c.forming" in canvas
    assert "Math.max(c.high, live)" in canvas and "Math.min(c.low, live)" in canvas
    assert 'color: "transparent"' in canvas, "the body must be hollow"
    # And it keeps its direction. Painting it a third colour said "unfinished" and
    # took the direction with it, which is most of what a candle is for.
    forming = canvas[canvas.index("c.forming\n"):canvas.index("c.forming\n") + 700]
    assert "CHART_COLOR.up" in forming and "CHART_COLOR.down" in forming, \
        "a forming candle must still be green or red"


def test_a_forming_candle_exists_even_before_the_broker_publishes_its_bar():
    """There is always a gap, and it is exactly when someone is watching.

    A 15-minute bar for 18:00 does not exist at 18:03, so the newest candle the
    server can send is the *previous* bucket and nothing on the chart is forming —
    while a live mark for right now is already in hand. The panel builds that candle
    out of the marks as they arrive.

    Its high and low are kept across polls so it grows the way a real one does
    rather than resetting to a dot every twenty seconds, and it resets when the
    bucket turns over so one period's extremes never leak into the next.
    """
    hook = (SRC / "hooks" / "useStructureLevels.ts").read_text()
    assert "useFormingCandle" in hook
    # Grown rather than replaced, so it does not reset to a dot every poll. Matched on
    # the arithmetic rather than on a variable name — the previous version of this
    # pinned `current.high` and failed on a rename that changed nothing.
    assert "Math.max(" in hook and "Math.min(" in hook
    assert "candle.high, live" in hook and "candle.low, live" in hook
    assert "candle.time === time" in hook, "it must reset when the bucket turns over"
    # And when the bar size changes. A different bar size is a different candle, not
    # the same one continued — without this, switching the timeframe carried the old
    # candle's high and low across and the chart you came back to was not the one you
    # left.
    assert "current.bucketMs === bucketMs" in hook
    # Appended only when it is newer than what the server sent, or it would sit on
    # top of a real candle for the same period.
    assert "forming.time > candles[candles.length - 1]" in hook


def test_the_forming_candle_keeps_its_identity_when_nothing_moved():
    """It is a `useMemo` dependency, and that makes object identity load-bearing.

    Returning a fresh object every render re-derived the whole series and re-ran the
    canvas effect — which calls `fitContent`. The chart was re-fitted on every render
    whether or not anything had moved, so it never held still, and any scroll or zoom
    was undone within seconds. The symptom reads as the opposite of the cause: a chart
    that re-fits constantly looks like one that never returns to where it was.
    """
    hook = (SRC / "hooks" / "useStructureLevels.ts").read_text()
    assert "return candle;" in hook, "no early return means a new object every render"


def test_the_chart_refits_only_when_its_shape_changes():
    """`chartShape` decides, and it has its own tests under vitest."""
    canvas = (SRC / "hooks" / "useStructureChartCanvas.ts").read_text()
    assert "chartShape(series, candles, lines)" in canvas
    assert "series.length && reshaped" in canvas, "it must not fit on every render"


def test_switching_the_bar_size_builds_a_new_canvas():
    """Rather than reusing one that still holds the old chart's zoom, scroll and
    price-scale override."""
    book = (SRC / "views" / "BookView.tsx").read_text()
    assert 'key={`${charting}:${timeframe ?? "auto"}`}' in book


def _without_comments(source: str) -> str:
    """TypeScript with its comments removed, for checks that mean "in the code".

    Crude — it does not know a `//` inside a string literal from one that starts a
    comment — and that is the safe direction here: it removes more than it should,
    so a check built on it can produce a false pass and never a false failure on
    prose.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def test_the_bar_sizes_offered_come_from_the_server():
    """A copy in the panel is a second list to keep in step, and the one that drifts
    is always the one nobody is testing.

    Scanned across the whole panel rather than in the file this happened to live in
    when it was written. The property belongs to the panel, not to `StructureChart` —
    and the first refactor to move the picker into a hook broke this test while
    breaking nothing a reader would care about, which is a test asserting the wrong
    thing.
    """
    panel = "\n".join(p.read_text() for p in SRC.rglob("*.ts*"))
    assert "chart.timeframes" in panel, "the panel hardcodes its own list"
    assert "chart.auto" in panel, "no way back to letting the window decide"

    # And no bar size is named in code. Comments are stripped first: the first version
    # of this check matched the sentence "a switch from 1Hour to 15Min" in a docstring
    # explaining why the panel must not name them, which is a test failing on its own
    # documentation.
    code = _without_comments(panel)
    hardcoded = [tf for tf in ("1Min", "5Min", "15Min", "1Hour", "1Day") if tf in code]
    assert not hardcoded, f"the panel names its own bar sizes: {hardcoded}"


def test_the_forming_candle_has_room_to_the_right():
    """Pressed against the frame is where a candle is hardest to read.

    Its wick gets clipped by the edge, which is the half that moves. `fitContent`
    also collapses the offset it was given, so it has to be reapplied after.
    """
    canvas = (SRC / "hooks" / "useStructureChartCanvas.ts").read_text()
    assert canvas.count("rightOffset") >= 2, \
        "the offset must survive fitContent, which resets it"


def _pending_source() -> str:
    """The loading view, wherever its parts live.

    It began as one component and a refactor moved its tile logic into a hook. These
    checks are about what the view *shows*, not about which file shows it, and the
    first version named the file — so the refactor failed them while breaking nothing
    a reader would notice. That is a test asserting the wrong thing.
    """
    return "\n".join(
        p.read_text() for p in SRC.rglob("*.ts*")
        if "ChartPending" in p.name or "useChartPending" in p.name
    )


def test_the_loading_view_shows_what_is_already_known():
    """The chart route takes about seven hundred milliseconds — it spawns an MCP
    subprocess and waits on Alpaca — and runs again on every change of bar size. The
    whole view used to collapse to one line of text for that long.

    Almost none of that wait was necessary. The name, the size, the legs, their fills,
    their live prices and the position's P&L are on the panel before anyone clicks:
    they come from the snapshot and the marks route, and both have long since
    answered. Only the price history and the two policy levels derived from it are
    genuinely unknown.
    """
    pending = _pending_source()

    # The real leg table, not a placeholder for one.
    assert "<LegTable chart={null}" in pending
    # And the figures that were already in hand.
    assert "t.chart.pnl" in pending and "t.chart.last" in pending
    assert "row.entry" in pending, "the entry price is on the ledger, not the chart route"


def test_the_loading_view_does_not_compute_the_policy_levels_itself():
    """The two holes are holes on purpose.

    Target and stop come from `manager.exit_levels`, which a test pins to
    `evaluate_exit`. Deriving them in the panel to avoid a placeholder would be the
    one way this picture could come to disagree with what the agent will actually do,
    which is worse than any loading state.
    """
    pending = _pending_source()
    assert "take_profit" not in pending and "stop_loss" not in pending
    for level in ("t.chart.target", "t.chart.stop"):
        # Whatever the surrounding shape, the value beside these two is nothing.
        line = next(ln for ln in pending.splitlines() if level in ln)
        assert "null" in line, f"{level} is being computed rather than left blank"


def test_the_loading_view_reserves_the_height_the_chart_will_take():
    """So the page does not jump when the data lands, which is the other half of what
    makes a loading state read as busy rather than broken."""
    pending = (SRC / "components" / "ChartPending.tsx").read_text()
    canvas = (SRC / "components" / "StructureChart.tsx").read_text()
    assert "h-[320px]" in pending
    assert "h-[320px]" in canvas, "the two heights have to match or the layout shifts"


def test_the_placeholder_animation_can_be_turned_off():
    """A pulsing block is close to the top of the list of things that setting exists
    for, and the placeholder still reads as a gap without it."""
    css = (SRC / "styles" / "globals.css").read_text()
    assert "@keyframes shimmer" in css
    block = css[css.index("@keyframes shimmer"):]
    assert "prefers-reduced-motion" in block
    assert "animation: none" in block[block.index("prefers-reduced-motion"):]


def test_the_ticker_stops_scrolling_for_reduced_motion_too():
    css = (SRC / "styles" / "globals.css").read_text()
    block = css[css.index("@keyframes ticker"):]
    assert "prefers-reduced-motion" in block


# --- binding beyond loopback ----------------------------------------------------------
#
# The panel served 127.0.0.1 only, and the comment saying so argued that binding to
# 0.0.0.0 "is a mistake that should not be one flag away". That is right about the
# default and wrong as an absolute: reading the desk from a phone on your own network is
# an ordinary thing to want, and the alternative is the operator editing the source.
#
# So the flag exists and the warning is loud. What it must never be is quiet — the
# difference between a considered choice and an accident is whether anyone was told
# what went onto the wire.

def test_loopback_needs_no_warning():
    from halstreet.telemetry.server import exposure_warning
    assert exposure_warning("127.0.0.1") is None
    assert exposure_warning("localhost") is None
    assert exposure_warning("::1") is None


def test_any_other_address_is_warned_about():
    from halstreet.telemetry.server import exposure_warning
    for host in ("0.0.0.0", "192.168.1.199", "::"):  # noqa: S104 - the case under test
        warning = exposure_warning(host)
        assert warning is not None, host


def test_the_warning_names_what_is_actually_on_the_wire():
    """"Exposed to the network" is not enough for anyone to weigh. Equity, open
    positions and the account's own P&L are what a reader would want named before
    deciding, so the warning names them."""
    from halstreet.telemetry.server import exposure_warning
    warning = exposure_warning("0.0.0.0")  # noqa: S104 - the case under test
    assert "equity" in warning and "position" in warning
    assert "read-only" in warning, "the one reassurance that is actually true"


def test_serve_still_defaults_to_loopback():
    """The flag changes what is possible, not what happens by default."""
    import inspect

    from halstreet.telemetry.server import serve
    assert inspect.signature(serve).parameters["host"].default == "127.0.0.1"


def test_the_panel_cli_defaults_to_loopback():
    from halstreet.cli.panel import build_parser
    assert build_parser().parse_args([]).host == "127.0.0.1"
