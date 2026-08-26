"""Environment loading, and the dev/comp split that runs through one file.

`docs/COMPETITION-ACCOUNT.md` sets the rule this module implements: two accounts,
always, and never point the dev config at the competition account "just to test
something." That is easy to say and easy to violate at 2am, so it is structural
here — but the structure is the **variable prefix**, not the filename.

There is one `.env`. `--env dev` reads `ALPACA_*`; `--env comp` reads
`COMP_ALPACA_*`. A dev run cannot pick up the judged account's credentials because
it never looks at a name they are stored under, and a comp run that has not been
given its own keys fails rather than silently falling back to the dev pair.

This used to be two near-identical files (`.env` and `.env.comp`), which bought
nothing the prefix did not already guarantee and cost a second 130-line file to
keep in sync — they had already drifted. Worse, two files hide the one mistake
that actually ends a competition entry: the same account pasted into both. In one
file that is a two-line comparison, and `load_env` makes it below.

Values already present in the real environment win over the file, so a one-off
`ALPACA_ENV=paper python -m ...` override behaves the way anyone would expect and
CI can inject secrets with no file on disk at all.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = ".env"
ENVS = ("dev", "comp")

#: Which credential names each account reads. The whole dev/comp separation.
KEY_PREFIX: dict[str, str] = {"dev": "ALPACA_", "comp": "COMP_ALPACA_"}


class ConfigError(RuntimeError):
    """The environment could not be loaded for the requested account."""


def env_path(env: str = "dev", root: Path | None = None) -> Path:
    """Where configuration is read from. The same file for every account."""
    if env not in ENVS:
        raise ConfigError(f"unknown env {env!r}; expected one of {sorted(ENVS)}")
    return (root or Path.cwd()) / ENV_FILE


def load_env(env: str = "dev", *, root: Path | None = None, required: bool = True) -> Path | None:
    """Load `.env` into os.environ and check the requested account is configured.

    `required` says whether this run needs an account at all. When it is False a
    missing file returns None instead of raising, and the credential check below is
    skipped — that is the offline path (`report --offline` reads the journal and
    the ledger and never speaks to a broker), and it is also how a deployment that
    injects configuration some other way opts out. Anything that will place an
    order leaves it True.

    Existing environment variables are never overwritten.
    """
    path = env_path(env, root)
    if not path.exists():
        if required:
            raise ConfigError(
                f"{path.name} not found at {path}. "
                "Copy .env.example to .env and fill in your paper keys."
            )
        return None

    try:
        from dotenv import load_dotenv
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ConfigError(
            "python-dotenv is not installed; run `pip install -e .` in the project root"
        ) from exc

    load_dotenv(path, override=False)
    if required:
        _assert_account_configured(env)
    return path


def _assert_account_configured(env: str) -> None:
    """Refuse a run whose account is unconfigured, or is the *other* account.

    Two failures, and the second is the one the old two-file layout could not see.
    A judged run with empty COMP_ keys is an obvious mistake and stops here. A
    judged run whose COMP_ keys were pasted from the dev account is not obvious at
    all — every check downstream passes, because the credentials are real and the
    environment is paper — and it is only discovered when preflight reports an
    account with prior fills in it, or worse, when nobody checks.
    """
    prefix = KEY_PREFIX[env]
    key = (os.environ.get(f"{prefix}API_KEY") or "").strip()
    secret = (os.environ.get(f"{prefix}SECRET_KEY") or "").strip()

    missing = [n for n, v in ((f"{prefix}API_KEY", key), (f"{prefix}SECRET_KEY", secret)) if not v]
    if missing:
        detail = (
            "The judged run reads COMP_* credentials so a dev run can never pick them "
            "up by accident. See docs/COMPETITION-ACCOUNT.md."
            if env == "comp"
            else "Fill in your paper keys — see .env.example."
        )
        raise ConfigError(f"{ENV_FILE} defines no {' or '.join(missing)}. {detail}")

    if env == "comp" and key == (os.environ.get("ALPACA_API_KEY") or "").strip():
        raise ConfigError(
            "COMP_ALPACA_API_KEY is the same credential as ALPACA_API_KEY — the judged "
            "run and the dev account would be the same Alpaca account. The competition "
            "requires a fresh account at $100,000 that development has never touched; "
            "see docs/COMPETITION-ACCOUNT.md."
        )
