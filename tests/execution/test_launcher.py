"""Finding the MCP launcher, whatever PATH the caller happens to have.

`uvx` is installed into the project's own virtualenv — `install.sh` puts it there
so the repo stays self-contained — which means it sits beside the interpreter that
is running. Resolving it from there rather than from PATH is what makes the client
usable by anything that can import it.

The gap was not theoretical. `start.sh` exports `.venv/bin`, so every documented
entry point worked and the failure was invisible until the panel was started some
other way: its structure-chart route then failed with a bare "No such file or
directory" naming nothing, the chart drew no price line, and its NOW field read as
a dash — which looks like missing market data rather than a missing binary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from halstreet.execution.mcp_client import resolve_command


def test_the_launcher_is_found_beside_this_interpreter():
    found = resolve_command("uvx")
    assert Path(found).is_absolute(), found
    assert Path(found).parent == Path(sys.executable).parent


def test_it_does_not_need_path_at_all(monkeypatch):
    # The actual failure: a process started without .venv/bin on PATH.
    monkeypatch.setenv("PATH", "")
    found = resolve_command("uvx")
    assert Path(found).is_file() and os.access(found, os.X_OK)


def test_an_explicit_path_is_honoured_untouched():
    # A caller naming a specific binary means it; searching would override them.
    assert resolve_command("/usr/bin/env") == "/usr/bin/env"
    assert resolve_command("./tools/uvx") == "./tools/uvx"


def test_something_genuinely_missing_falls_through_to_the_message(monkeypatch):
    """Returned unchanged, so the launch fails and *explains* itself.

    The client already turns FileNotFoundError into a sentence naming `uvx` and the
    PATH. Resolving to something wrong here would trade a good error for a worse
    one.
    """
    monkeypatch.setenv("PATH", "")
    assert resolve_command("definitely-not-a-real-binary") == "definitely-not-a-real-binary"


def test_a_directory_is_not_mistaken_for_the_launcher(tmp_path, monkeypatch):
    # `.venv/bin/uvx` being a directory is nonsense, but `is_file` is what stops it
    # being launched — an existence check alone would pass.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "uvx").mkdir()
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))
    monkeypatch.setenv("PATH", "")
    assert resolve_command("uvx") == "uvx"


def test_a_non_executable_file_is_not_launched(tmp_path, monkeypatch):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "uvx").write_text("#!/bin/sh\n")   # present, not executable
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))
    monkeypatch.setenv("PATH", "")
    assert resolve_command("uvx") == "uvx"


def test_the_client_resolves_at_construction(monkeypatch):
    # So the absolute path is what reaches StdioServerParameters, rather than being
    # re-resolved per call against whatever the environment looks like by then.
    from halstreet.execution.mcp_client import AlpacaMCP
    from halstreet.execution.paper_assert import PaperConfig

    cfg = PaperConfig(api_key="PKTEST", secret_key="s",
                      endpoint="https://paper-api.alpaca.markets")
    client = AlpacaMCP(cfg, "uvx", ("alpaca-mcp-server",))
    assert Path(client._command).is_absolute()
