"""Whether `./start.sh panel` opens a browser, and when it must not.

Opening one is a convenience; opening one in the wrong place is a papercut that
outlives the convenience. Three cases have to stay apart:

  * a desktop session — open it, that is the whole point;
  * a headless box or an SSH session — there is no browser to open, and `xdg-open`
    on a machine with no display either fails silently or hangs holding the terminal;
  * somebody who said not to — a flag and an environment variable, because the person
    running this under a process manager cannot pass a flag.

The decision is separated from the act so it can be asserted without launching
anything. `wait_until_listening` is the other half: the browser must open *after* the
port answers, or the reader's first impression of the panel is a connection-refused
page they then have to reload.
"""

from __future__ import annotations

import socket

import pytest

from halstreet.telemetry import browser

DESKTOP = {"DISPLAY": ":0"}


def _open(**over):
    kwargs = {"disabled": False, "environ": DESKTOP, "platform": "linux", "built": True}
    return browser.should_open(**{**kwargs, **over})


# --- when to open -----------------------------------------------------------------

def test_a_desktop_session_opens_the_panel():
    assert _open().open is True


def test_wayland_counts_as_a_display():
    """A Wayland session has no DISPLAY unless XWayland happens to be up."""
    assert _open(environ={"WAYLAND_DISPLAY": "wayland-0"}).open is True


def test_a_headless_box_does_not():
    got = _open(environ={})
    assert got.open is False
    assert "display" in got.why


def test_an_ssh_session_with_no_display_does_not():
    """The common one: the agent runs on a box you are logged into from elsewhere.

    Opening a browser there is at best a no-op and at worst `xdg-open` blocking with
    the terminal held, which looks exactly like the panel having failed to start.
    """
    got = _open(environ={"SSH_CONNECTION": "10.0.0.2 22 10.0.0.9 22"})
    assert got.open is False


def test_ssh_with_x_forwarding_still_opens():
    # A forwarded display is a display. Refusing here would be guessing at intent.
    assert _open(environ={"SSH_CONNECTION": "x", "DISPLAY": "localhost:10.0"}).open is True


@pytest.mark.parametrize("plat", ["darwin", "win32"])
def test_a_platform_that_has_no_display_variable_still_opens(plat):
    """macOS and Windows have a GUI without ever setting DISPLAY.

    Reading their empty environment as headless would disable the feature on two of
    the three platforms this could run on.
    """
    assert _open(environ={}, platform=plat).open is True


# --- when not to, because somebody said so ------------------------------------------

def test_the_flag_wins_over_everything():
    assert _open(disabled=True).open is False


def test_the_environment_variable_also_turns_it_off():
    """A process manager or a systemd unit cannot pass a flag."""
    got = _open(environ={**DESKTOP, browser.NO_BROWSER: "1"})
    assert got.open is False


@pytest.mark.parametrize("value", ["0", "", "false", "no"])
def test_the_variable_set_to_a_falsey_value_does_not_disable_it(value):
    """`HALSTREET_NO_BROWSER=0` means "no, do not disable it".

    Treating mere presence as truth is the classic reading, and it makes the variable
    impossible to turn back off without unsetting it.
    """
    assert _open(environ={**DESKTOP, browser.NO_BROWSER: value}).open is True


def test_it_always_says_why_it_declined():
    """A silent no-op reads as a broken feature. Constitution VII."""
    for env in ({}, {"SSH_CONNECTION": "x"}):
        assert _open(environ=env).why
    assert _open(disabled=True).why


def test_it_says_nothing_when_it_is_going_to_open():
    assert _open().why == ""


def test_it_does_not_open_a_page_that_has_not_been_built():
    """`/` is a 404 until `npm run build` has run — the API serves without it.

    The panel already prints a note saying so. Opening a browser onto the 404 anyway
    turns a clear message into a confusing screen, and the reader's conclusion is
    that the panel is broken rather than unbuilt.
    """
    got = _open(built=False)
    assert got.open is False
    assert "built" in got.why


def test_an_unbuilt_bundle_is_reported_as_its_own_reason():
    """Not folded into "no display": the fix is different and it is a one-liner."""
    assert _open(built=False).why != _open(environ={}).why


# --- waiting for the port -----------------------------------------------------------

def test_it_waits_until_the_port_actually_answers():
    """Opening before `serve` binds shows a connection-refused page, which the reader
    has to notice and reload — a worse first impression than no browser at all."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert browser.wait_until_listening(port, timeout=2.0) is True


def test_it_gives_up_rather_than_hanging_when_nothing_ever_binds():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Nothing is listening on that port now: the socket above is closed.
    assert browser.wait_until_listening(port, timeout=0.3, interval=0.05) is False


def test_giving_up_is_not_an_exception():
    """This runs in a background thread beside a serving process.

    A raise there is an unraisable-exception traceback printed over the panel's own
    startup output, for a convenience that did not work.
    """
    browser.wait_until_listening(1, timeout=0.1, interval=0.05)
