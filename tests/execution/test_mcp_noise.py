"""Keeping the broker subprocess's chatter out of the agent's own output.

Every broker call spawns `uvx alpaca-mcp-server` fresh — that is the connect-per-call
design, and it is deliberate. What was not deliberate is that FastMCP prints a
fifteen-line ASCII banner to stderr on every start, so a single scan over six
discovered symbols buries the agent's own log under several hundred lines of box
drawing. Running `./start.sh` showed nothing else at all.

No environment variable turns it off: `FASTMCP_LOG_LEVEL=ERROR` removes the one INFO
line and leaves the banner, and `FASTMCP_DISABLE_BANNER` is not a thing this version
reads. The supported lever is `stdio_client(errlog=...)`.

Routing that to `DEVNULL` would be the easy answer and the wrong one. The broker's
stderr is where a real failure appears — `get_news` limit 100 came back as
`HTTP 400: invalid limit: larger than the allowed maximum of 50`, on stderr, and that
is how the bug was found at all. So this filters rather than silences: the decoration
goes, and anything that might be a diagnosis is passed straight through.

The bias is deliberate and one-directional. An unrecognised line is *kept*. Losing a
banner line matters not at all; losing the one line that explains a broken scan is the
failure this file exists to avoid.
"""

from __future__ import annotations

import io

from halstreet.execution import mcp_noise

BANNER = """

╭──────────────────────────────────────────────────────────────────────────────╮
│                                                                              │
│                         ▄▀▀ ▄▀█ █▀▀ ▀█▀ █▀▄▀█ █▀▀ █▀█                        │
│                         █▀  █▀█ ▄▄█  █  █ ▀ █ █▄▄ █▀▀                        │
│                                                                              │
│                                FastMCP 3.4.7                                 │
│                            https://gofastmcp.com                             │
│                  🖥  Server:      Alpaca MCP Server, 3.4.7                    │
│                  🚀 Deploy free: https://horizon.prefect.io                  │
╰──────────────────────────────────────────────────────────────────────────────╯

[08/28/26 10:28:33] INFO     Starting MCP server 'Alpaca MCP    transport.py:241
                             Server' with transport 'stdio'
"""


def _through(text: str) -> str:
    sink = io.StringIO()
    quiet = mcp_noise.Quiet(sink)
    quiet.write(text)
    quiet.flush()
    return sink.getvalue()


# --- what goes ----------------------------------------------------------------------

def test_the_whole_banner_disappears():
    assert _through(BANNER).strip() == ""


def test_the_startup_log_line_goes_with_it():
    assert "Starting MCP server" not in _through(BANNER)


def test_six_starts_leave_nothing_behind():
    """One scan over a discovered universe is six committees and many more calls."""
    assert _through(BANNER * 6).strip() == ""


def test_the_wrapped_half_of_the_startup_line_goes_too():
    """Rich wraps the INFO message and aligns the remainder under it.

        [08/28/26 10:28:33] INFO     Starting MCP server 'Alpaca MCP    transport.py:241
                                     Server' with transport 'stdio'

    The second line carries none of the markers that identify the first, so matching
    line by line leaves `Server' with transport 'stdio'` on screen once per call —
    which is the noise, just narrower.
    """
    assert "with transport" not in _through(BANNER)


def test_an_indented_line_after_something_real_is_not_swallowed_as_a_continuation():
    """The rule is "indented, and following start-up chatter" — both halves.

    Dropping every indented line after any line at all would eat the body of every
    traceback the broker ever prints.
    """
    tb = 'RuntimeError: boom\n    during handling of the above\n'
    assert "during handling" in _through(tb)


# --- what must survive ----------------------------------------------------------------

def test_the_error_that_found_the_news_limit_bug_still_comes_through():
    """The exact line, because this is the case the filter must not cost us."""
    line = ("ValueError: HTTP error 400: Bad Request - {'message': "
            "'invalid limit: larger than the allowed maximum of 50'}\n")
    assert line in _through(BANNER + line)


def test_a_traceback_survives_intact():
    tb = ('Traceback (most recent call last):\n'
          '  File "x.py", line 1, in <module>\n'
          '    raise RuntimeError("boom")\n'
          'RuntimeError: boom\n')
    assert _through(tb) == tb


def test_an_unrecognised_line_is_kept_rather_than_dropped():
    """The bias, stated as a test. A banner line lost costs nothing; the one line
    explaining a broken scan is the whole reason this filters instead of silencing."""
    assert "something nobody predicted" in _through("something nobody predicted\n")


def test_a_warning_about_credentials_survives():
    assert "APCA" in _through("WARNING: APCA_API_KEY_ID not set\n")


def test_an_error_log_line_is_not_mistaken_for_the_startup_one():
    """`INFO ... Starting MCP server` goes; an ERROR at the same shape does not."""
    line = "[08/28/26 10:28:33] ERROR    Tool call failed        server.py:118\n"
    assert "Tool call failed" in _through(line)


# --- the mechanics it is easy to get wrong --------------------------------------------

def test_a_line_split_across_two_writes_is_still_recognised():
    """A pipe hands over whatever arrived, not whole lines.

    Filtering per `write()` call rather than per line would let half a banner through
    whenever the chunk boundary landed mid-line — intermittently, and only under load.
    """
    sink = io.StringIO()
    quiet = mcp_noise.Quiet(sink)
    quiet.write("│      FastMCP 3.4")
    quiet.write(".7      │\n")
    quiet.flush()
    assert sink.getvalue().strip() == ""


def test_a_real_line_split_across_writes_still_arrives_whole():
    sink = io.StringIO()
    quiet = mcp_noise.Quiet(sink)
    quiet.write("RuntimeError: ")
    quiet.write("the broker said no\n")
    quiet.flush()
    assert sink.getvalue() == "RuntimeError: the broker said no\n"


def test_a_trailing_line_with_no_newline_is_not_swallowed_on_flush():
    """The subprocess can die mid-line, and that half-line is the interesting one."""
    sink = io.StringIO()
    quiet = mcp_noise.Quiet(sink)
    quiet.write("RuntimeError: killed mid-sen")
    quiet.flush()
    assert "killed mid-sen" in sink.getvalue()


def test_it_never_raises_whatever_it_is_handed():
    """This is a stderr writer inside a broker call. A raise here fails the trade."""
    quiet = mcp_noise.Quiet(io.StringIO())
    for junk in ("", "\x00\x00", "\n" * 50, "üñïçø∂é ✅\n"):
        quiet.write(junk)
    quiet.flush()


def test_a_closed_sink_does_not_take_the_call_down_with_it():
    sink = io.StringIO()
    quiet = mcp_noise.Quiet(sink)
    sink.close()
    quiet.write("anything\n")
    quiet.flush()


# --- boxes that are content, not decoration -------------------------------------------
#
# rich draws tracebacks in the same box characters as the banner. Filtering every
# `│ ... │` line ate the *body* of a real traceback and left its header and footer
# behind — a fragment that looks like a rendering fault and says nothing. Worse than
# keeping the banner and worse than dropping the traceback: a diagnostic that states
# something false, which is the one thing Constitution VII forbids.
#
# The discriminator is the title. FastMCP's banner is an untitled box; rich titles its
# tracebacks and panels.

TRACEBACK_BOX = """\
╭─────────── Traceback (most recent call last) ────────────╮
│ /path/to/server.py:118 in call_tool                      │
│     raise ValueError(msg)                                │
╰──────────────────────────────────────────────────────────╯
ValueError: HTTP error 400: Bad Request
"""


def test_a_titled_box_survives_whole():
    got = _through(TRACEBACK_BOX)
    assert "Traceback" in got
    assert "raise ValueError(msg)" in got, "the body is the part worth having"
    assert "server.py:118" in got


def test_an_untitled_box_is_still_dropped():
    assert _through(BANNER).strip() == ""


def test_a_banner_directly_after_a_traceback_is_still_dropped():
    """The box state must reset at `╰`, or one traceback keeps everything after it."""
    assert "FastMCP" not in _through(TRACEBACK_BOX + BANNER)


def test_a_traceback_directly_after_a_banner_still_survives():
    assert "raise ValueError(msg)" in _through(BANNER + TRACEBACK_BOX)


def test_the_error_line_under_a_traceback_box_survives():
    assert "HTTP error 400" in _through(TRACEBACK_BOX)


# --- through a real pipe --------------------------------------------------------------
#
# `stdio_client` hands `errlog` to `subprocess.Popen` as `stderr=`, so it must be a
# real file descriptor — the subprocess writes to the OS, not through Python. A
# `TextIO`-shaped object raises `AttributeError: no attribute 'fileno'` before the
# broker is even spawned, which is a failed trade rather than a tidy terminal.

def test_the_writer_has_a_real_file_descriptor():
    """The whole reason this is a pipe and not a wrapper object."""
    writer, close = mcp_noise.quiet_stderr()
    try:
        assert isinstance(writer.fileno(), int)
    finally:
        close()


def test_a_banner_written_to_the_fd_never_reaches_the_terminal(capsys):
    writer, close = mcp_noise.quiet_stderr()
    writer.write(BANNER)
    writer.flush()
    close()
    assert capsys.readouterr().err.strip() == ""


def test_an_error_written_to_the_fd_does(capsys):
    writer, close = mcp_noise.quiet_stderr()
    writer.write("RuntimeError: the broker said no\n")
    writer.flush()
    close()
    assert "the broker said no" in capsys.readouterr().err


def test_closing_waits_for_the_pipe_to_drain(capsys):
    """Otherwise the last lines a failing broker wrote are still in flight.

    Whether they reached the terminal would then depend on thread scheduling, so the
    diagnosis for a failure would appear only sometimes — which is worse than never,
    because it cannot be reproduced.
    """
    writer, close = mcp_noise.quiet_stderr()
    writer.write("RuntimeError: written right before close\n")
    close()
    assert "written right before close" in capsys.readouterr().err


def test_closing_twice_is_not_an_error():
    """`call()` closes it in a `finally`, and the context manager may have already."""
    _, close = mcp_noise.quiet_stderr()
    close()
    close()
