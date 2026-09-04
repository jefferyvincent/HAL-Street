"""Shared test doubles.

One thing lives here rather than in each test file: how a fake Anthropic client is
called. The production code streams — it has to, because the SDK refuses a
non-streaming request whose `max_tokens` implies it could run past ten minutes, and
the judge's ceiling is 32,000. That refusal is a `ValueError` raised before anything
reaches the network, so it took a live run to find and it failed *every* cycle.

The fakes here therefore stream and nothing else. `create` is present and raises, so
a future edit that quietly goes back to `messages.create` fails the whole suite
instead of passing it and shipping an agent that cannot make a decision.
"""

from __future__ import annotations

from typing import Any, Self


class _Stream:
    """The context manager `client.messages.stream(...)` returns."""

    def __init__(self, message: Any) -> None:
        self._message = message

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get_final_message(self) -> Any:
        return self._message


class StreamingOnly:
    """Mixin for a fake `client.messages`: answer `stream`, refuse `create`.

    Implement `respond(**kwargs)` and return the message the SDK would have.
    """

    def stream(self, **kwargs: Any) -> _Stream:
        return _Stream(self.respond(**kwargs))

    def create(self, **kwargs: Any) -> Any:
        raise AssertionError(
            "this call must stream. `messages.create` refuses any request whose "
            "max_tokens implies it could take longer than ten minutes — the judge "
            "sits at 32,000 — and it refuses with a ValueError raised before the "
            "request is sent, so every cycle fails and nothing reaches the broker."
        )

    def respond(self, **kwargs: Any) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError
