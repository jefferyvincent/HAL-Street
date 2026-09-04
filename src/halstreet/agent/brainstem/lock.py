"""One agent per journal, enforced by the filesystem.

Two agents ran against this account for three hours before anyone noticed, and the
only symptom was a scan cadence that alternated 13m39s and 16m22s — which no single
thirty-minute scheduler can produce, but which nobody is watching for. Everything
else looked healthy: both wrote well-formed records to the same file, neither
errored, and the coverage table added them together into one plausible session.

Worse, the stale one was running code from before two fixes that morning, so half
the cycles in the journal were a previous version's behaviour presented as the
current agent's. That is the failure that matters. A judged run is a claim about
what *this* code did.

It survived because the evidence was misleading in both directions. `ps` showed a
single process, which looked conclusive and was not: this repository is often
worked on from inside a Flatpak sandbox, where `ps` sees a private PID namespace
and a host process is simply invisible. Absence from a process list is not absence.

`flock` does not care. It is held on an inode both processes can see, the kernel
releases it when the holder dies however it dies, and there is no stale lock to
clean up after a crash — which is the whole reason for preferring it to a pidfile
whose contents have to be believed.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self


class AlreadyRunning(RuntimeError):
    """Another agent holds this journal."""


class JournalLock:
    """An exclusive claim on one journal, for as long as the process lives."""

    def __init__(self, journal_path: str | Path) -> None:
        self.path = Path(f"{journal_path}.lock")
        self._fd: int | None = None

    def acquire(self) -> None:
        """Take the lock, or raise with whatever the holder left about itself."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            held = self._describe(fd)
            os.close(fd)
            raise AlreadyRunning(
                f"another agent already holds {self.path.name}.\n"
                f"      {held}\n"
                "      Two agents on one account interleave their scans, double the "
                "orders and\n"
                "      write one journal that reads as a single run. Stop the other "
                "one first.\n"
                "      If you cannot see it in `ps`, look outside this shell's PID "
                "namespace —\n"
                "      a Flatpak or container sandbox hides host processes from it "
                "entirely."
            ) from exc

        # Written after the lock is held, so the file only ever describes its owner.
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({
            "pid": os.getpid(),
            "started": datetime.now(UTC).isoformat(),
            "argv0": os.path.basename(sys.argv[0]) if sys.argv else "",
        }).encode() + b"\n")
        os.fsync(fd)
        self._fd = fd

    def _describe(self, fd: int) -> str:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 4096).decode().strip()
            held: dict[str, Any] = json.loads(raw)
        except (OSError, ValueError):
            return "The holder left no details."
        return (f"Held by pid {held.get('pid')} ({held.get('argv0') or 'unknown'}), "
                f"started {held.get('started')}.")

    def release(self) -> None:
        if self._fd is not None:
            # The close alone would release it; unlocking first makes that explicit
            # rather than incidental.
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
