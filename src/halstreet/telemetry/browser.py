"""Whether to open a browser at the panel, and waiting until there is one to open.

`./start.sh panel` printed a URL and left the reader to find it. Opening it is a
small kindness with two ways to become an irritation, so both are decided here rather
than inline at the call site — which also means they can be asserted without
launching anything.

**Not on a machine with no display.** `xdg-open` on a headless box either fails
silently or blocks holding the terminal, and the second looks exactly like the panel
having failed to start. An SSH session is the common case: the agent runs on a box
you are logged into from somewhere else, and the browser you want is not there.

**Not after being told no.** A flag for a person, an environment variable for a
process manager or a systemd unit that cannot pass one.

The wait is the other half. `serve()` binds a moment after this decision is made, and
a browser opened before that shows a connection-refused page the reader has to notice
and reload — a worse first impression than no browser at all.
"""

from __future__ import annotations

import contextlib
import socket
import sys
import time
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass

#: Set this to a truthy value to stop the panel opening a browser.
NO_BROWSER = "HALSTREET_NO_BROWSER"

#: Values that mean "yes, disable it". Anything else — including `0` and the empty
#: string — leaves it on. Reading mere presence as truth is the usual shortcut, and it
#: makes `HALSTREET_NO_BROWSER=0` impossible to interpret as anyone would expect.
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Platforms with a GUI that never set a display variable. Reading their empty
#: environment as headless would disable this on two of the three platforms it runs on.
_ALWAYS_GUI = frozenset({"darwin", "win32"})

#: How long to wait for the port to answer before giving up on the convenience.
DEFAULT_TIMEOUT = 8.0
DEFAULT_INTERVAL = 0.15


@dataclass(frozen=True)
class Verdict:
    """Whether to open, and — when not — the reason, so it is never a silent no-op."""

    open: bool
    why: str = ""


def should_open(*, disabled: bool, built: bool = True,
                environ: Mapping[str, str] | None = None,
                platform: str | None = None) -> Verdict:
    """Decide, without opening anything."""
    env = environ if environ is not None else {}
    plat = platform if platform is not None else sys.platform

    if disabled:
        return Verdict(False, "--no-browser")
    # Its own reason rather than folded into the display check: the API and the socket
    # serve perfectly well unbuilt, so this is not "there is nothing to open" — it is
    # a different fix, and a one-line one the panel already prints above.
    if not built:
        return Verdict(False, "apps/desktop/dist is not built")
    if str(env.get(NO_BROWSER, "")).strip().lower() in _TRUTHY:
        return Verdict(False, f"{NO_BROWSER} is set")
    if plat in _ALWAYS_GUI:
        return Verdict(True)
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        # A forwarded display is a display; refusing over SSH here would be guessing
        # at intent when the environment has already answered the question.
        return Verdict(True)
    if env.get("SSH_CONNECTION") or env.get("SSH_TTY"):
        return Verdict(False, "no display on this SSH session")
    return Verdict(False, "no display")


def wait_until_listening(port: int, *, host: str = "127.0.0.1",
                         timeout: float = DEFAULT_TIMEOUT,
                         interval: float = DEFAULT_INTERVAL) -> bool:
    """Block until something accepts on `port`, or the timeout runs out.

    Never raises. This runs in a thread beside a serving process, where an exception
    is an unraisable-exception traceback printed over the panel's own startup output —
    for a convenience that did not work.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=interval):
                return True
        except OSError:
            time.sleep(interval)
    return False


def open_when_ready(url: str, port: int, **kwargs: object) -> None:
    """Wait for the port, then hand the URL to the desktop. Silent if either fails.

    Failure here is not worth a message: the URL is already on screen, the panel is
    already serving, and the only thing lost is a click saved.
    """
    if not wait_until_listening(port, **kwargs):  # type: ignore[arg-type]
        return
    # Suppressed rather than logged, deliberately: this runs in a thread beside the
    # panel's own startup output, the URL is already on screen, the server is already
    # serving, and the only thing lost is a saved click. A traceback there would be
    # the loudest thing on the terminal for the least important failure on it.
    with contextlib.suppress(Exception):
        webbrowser.open(url)
