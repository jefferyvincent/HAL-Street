"""Keep the broker subprocess's decoration out of the agent's own output.

Every call spawns `uvx alpaca-mcp-server` fresh — connect-per-call, deliberately — and
FastMCP prints a fifteen-line ASCII banner to stderr each time it starts. One scan
over six discovered symbols is dozens of starts, so `./start.sh` showed a wall of box
drawing and nothing of its own.

No environment variable turns it off in this version: `FASTMCP_LOG_LEVEL=ERROR`
removes the single INFO line and leaves the banner standing. The supported lever is
`stdio_client(errlog=...)`, which is what this is written for.

**It filters rather than silences, and that distinction is the whole design.** Pointing
`errlog` at `DEVNULL` is one word and throws away the channel a real failure arrives
on: `get_news` with `limit=100` came back as `HTTP 400: invalid limit: larger than the
allowed maximum of 50` on exactly this stream, and that is how the bug was found.

So the bias runs one way only — **an unrecognised line is kept.** Losing a banner line
costs nothing. Losing the one line that explains why a scan came back empty is the
failure this module exists to prevent, and a filter that guesses in the other
direction would be worse than the noise.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Callable
from typing import TextIO

#: Characters that only appear in the banner's box and lettering. A line built out of
#: these is decoration; no diagnostic is drawn in box-drawing glyphs.
_BOX = "╭╮╰╯│─█▀▄"

#: Fragments that identify FastMCP's own start-up chatter. Deliberately specific
#: strings rather than a shape, so a line that merely resembles one is kept.
_STARTUP = (
    "Starting MCP server",
    "gofastmcp.com",
    "Deploy free",
)


#: How long to wait for the reader to drain at the end of a call. Long enough for a
#: pipe that already has EOF; short enough that a wedged one cannot stall a scan.
_DRAIN_TIMEOUT = 2.0

#: How far rich indents the wrapped remainder of a log line. Anything shallower is
#: ordinary indentation — a traceback body, a YAML fragment — and is kept.
_WRAP_INDENT = 8


def box_edge(line: str) -> str:
    """`"open"`, `"close"`, or `""` — and whether an opening box carries a title.

    rich draws tracebacks in the same characters as FastMCP's banner, so "is this a
    box" cannot decide anything on its own. What separates them is the title: the
    banner is an untitled frame, and rich labels its panels — `╭── Traceback ──╮`.
    """
    text = line.strip()
    if text.startswith("╭"):
        # Any letter or digit in the top edge is a title, and a titled box is content.
        return "titled" if any(ch.isalnum() for ch in text) else "open"
    if text.startswith("╰"):
        return "close"
    return ""


def is_noise(line: str, *, after_startup: bool = False) -> bool:
    """Is this line pure decoration? Anything uncertain is not.

    `after_startup` says the previous line was FastMCP's own start-up chatter, which
    is the only context in which a deeply indented continuation is dropped — rich
    wraps that message and aligns the remainder under it, and the remainder carries
    none of the markers that identified the first half. Both halves of the condition
    are load-bearing: dropping every indented line after any line at all would eat
    the body of every traceback the broker prints.
    """
    text = line.strip()
    if not text:
        return True
    if after_startup and line[:_WRAP_INDENT].isspace() and "[" not in line[:_WRAP_INDENT]:
        return True
    # A line made only of box glyphs and spaces — the frame, and the ASCII lettering
    # inside it. `all()` over an empty string is True, hence the guard above.
    if all(ch in _BOX or ch.isspace() for ch in text):
        return True
    # The banner's contents sit inside the frame, so they start and end with a bar.
    if text.startswith("│") and text.endswith("│"):
        return True
    # `[ts] INFO  Starting MCP server ...` and its wrapped continuation. Matched on
    # INFO specifically: the same shape at ERROR is the thing we are keeping.
    return any(mark in text for mark in _STARTUP) and "ERROR" not in text


class Quiet:
    """A `TextIO`-shaped sink that drops the banner and forwards everything else.

    Buffers to a newline because a pipe hands over whatever arrived rather than whole
    lines. Filtering per `write()` would let half a banner through whenever a chunk
    boundary landed mid-line — intermittently, and only under load.

    Nothing here raises. It sits inside a broker call, and an exception on the way to
    stderr would fail a trade over a cosmetic concern.
    """

    def __init__(self, sink: TextIO) -> None:
        self._sink = sink
        self._buf = ""
        # Whether the last line we dropped was start-up chatter, so its wrapped
        # remainder can be recognised as belonging to it.
        self._after_startup = False
        # None, "banner" (an untitled frame) or "content" (a titled one, whose body
        # is passed through whole — a rich traceback is drawn in the same characters).
        self._box: str | None = None

    def write(self, text: str) -> int:
        try:
            self._buf += str(text)
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if self._keep(line):
                    self._sink.write(line + "\n")
        except Exception:  # noqa: S110 - a stderr writer may not fail a trade
            pass
        return len(text)

    def _keep(self, line: str) -> bool:
        """Whether one line survives, advancing the box and wrap state as it goes.

        Ordered so the box decision comes first: inside a titled box every line is
        content, including ones that would otherwise look like decoration, because
        that is exactly what a rich traceback body is.
        """
        edge = box_edge(line)
        if edge == "open":                       # untitled frame — the banner
            self._box, self._after_startup = "banner", False
            return False
        if edge == "titled":                     # rich labels what it draws
            self._box, self._after_startup = "content", False
            return True
        if edge == "close":
            was, self._box, self._after_startup = self._box, None, False
            return was != "banner"
        if self._box == "banner":
            return False
        if self._box == "content":
            return True
        noise = is_noise(line, after_startup=self._after_startup)
        # A blank line ends a wrapped log message; it does not begin one.
        self._after_startup = noise and bool(line.strip())
        return not noise

    def flush(self) -> None:
        # The tail matters: a subprocess can die mid-line, and that half-line is
        # usually the interesting one. It is emitted whole rather than held.
        try:
            if self._buf and self._keep(self._buf):
                self._sink.write(self._buf)
            self._buf = ""
            self._sink.flush()
        except Exception:  # noqa: S110 - a stderr writer may not fail a trade
            pass

    # `stdio_client` only writes and flushes, but it types the parameter as TextIO
    # and anyio may close it on teardown.
    def close(self) -> None:
        self.flush()

    @property
    def encoding(self) -> str:
        return getattr(self._sink, "encoding", "utf-8")


def quiet_stderr(sink: TextIO | None = None) -> tuple[TextIO, Callable[[], None]]:
    """A real pipe whose far end is filtered. Returns `(writer, close)`.

    A pipe rather than a `Quiet` handed straight to `stdio_client`, because that
    `errlog` is passed to `subprocess.Popen` as `stderr=` — the broker writes to an
    operating-system descriptor, not through Python, so an object without `fileno()`
    fails before the process is even spawned. That is a failed trade in exchange for
    a tidy terminal, which is the wrong way round.

    The reader is a daemon thread, one per call. Beside spawning a whole `uvx`
    subprocess that is not a cost worth avoiding, and daemon so a wedged pipe can
    never keep the agent alive at shutdown.
    """
    out = sink if sink is not None else sys.stderr
    read_fd, write_fd = os.pipe()
    writer = os.fdopen(write_fd, "w", buffering=1, errors="replace")

    def pump() -> None:
        quiet = Quiet(out)
        # `errors="replace"` on both ends: this is a subprocess's stderr, it can carry
        # a partial multi-byte sequence when the process dies mid-write, and a decode
        # error here would lose the rest of the stream — including whatever killed it.
        with contextlib.suppress(Exception), os.fdopen(read_fd, "r", errors="replace") as reader:
            for line in reader:
                quiet.write(line)
        quiet.flush()

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()

    def close() -> None:
        # Closing the write end is what gives the reader EOF and ends the thread.
        # Idempotent: `call()` closes it in a `finally` and the context manager above
        # it may already have.
        with contextlib.suppress(Exception):
            writer.close()
        # Then wait for the pump to drain. Without this the last lines a failing
        # broker wrote are still in the pipe when the call returns, and whether they
        # ever reach the terminal depends on scheduling — so the diagnosis for a
        # failure would appear only sometimes. Bounded, because a wedged reader must
        # not be able to hold a trading loop.
        thread.join(timeout=_DRAIN_TIMEOUT)

    return writer, close
