#!/usr/bin/env bash
#
# HAL Street launcher — activate the venv and run a mode, appending output to
# var/log/halstreet.log.
#
#   ./start.sh                  the scheduled loop (scans while the market is open)
#   ./start.sh -- --once        a single pass and exit
#   ./start.sh -- --until-close scan until the bell, then stop
#   ./start.sh -- --submit      actually place approved orders (paper)
#   ./start.sh verify           verify multi-leg orders against a live chain
#   ./start.sh verify -- --submit
#                               ...and actually place them (PAPER, dev account)
#   ./start.sh soak             run a session, then report what it exercised
#   ./start.sh soak -- --submit
#   ./start.sh preflight        check the competition account is clean
#   ./start.sh test             the test suite
#   ./start.sh report           P&L, gate counts, drawdown
#   ./start.sh report -- --export out/
#   ./start.sh panel            read-only dashboard on http://127.0.0.1:8787
#                               (build it once: cd apps/desktop && npm run build)
#   ./start.sh --env comp ...   use the judged account (COMP_* keys in .env)
#
set -euo pipefail
cd "$(dirname "$0")"

# Everything the agent writes lives under var/ — see src/halstreet/paths.py, which
# owns these locations for the Python side. HALSTREET_VAR moves the lot.
VAR="${HALSTREET_VAR:-var}"
LOG="$VAR/log/halstreet.log"
mkdir -p "$VAR/log"

say()  { printf '\033[1;36m==> %s\033[0m\n' "$*" >&2; }

# The wordmark. Chrome, and deliberately cheap: printed once at launch, never per
# cycle — the broker's own server prints a banner on every call and burying the
# agent's output under it is the mistake being avoided, not copied.
#
# Terminal only. `./start.sh` pipes the agent through `tee` into var/log and CI
# captures the lot; block-drawing characters in a log are noise on every run and the
# first thing to break a grep. `[ -t 2 ]` because everything else here says its piece
# on stderr, which keeps stdout clean for `report --export`.
#
# Nothing on these lines is a secret. It is the most screenshot-prone surface in the
# project — the line below it prints a redacted key prefix, and this is the one most
# likely to be cropped into a post.
banner() {
  [ -t 2 ] || return 0
  local a='' r='' z=''
  if [ -z "${NO_COLOR:-}" ]; then a='\033[38;5;214m'; r='\033[38;5;196m'; z='\033[0m'; fi
  printf '%b' "$a" >&2
  cat >&2 <<'ART'
    ██╗  ██╗ █████╗ ██╗     ███████╗████████╗██████╗ ███████╗███████╗████████╗
    ██║  ██║██╔══██╗██║     ██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔════╝╚══██╔══╝
    ███████║███████║██║     ███████╗   ██║   ██████╔╝█████╗  █████╗     ██║
    ██╔══██║██╔══██║██║     ╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══╝     ██║
    ██║  ██║██║  ██║███████╗███████║   ██║   ██║  ██║███████╗███████╗   ██║
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
ART
  printf '%b' "$z" >&2
  printf '    %b●%b  The model proposes; deterministic gates dispose.  %bpaper only%b\n\n' \
    "$r" "$z" "$a" "$z" >&2
}

usage() {
  banner
  # The header comment is the help text, so the two cannot drift — same trick
  # install.sh uses.
  sed -n "3,$(($(grep -n '^set -euo' "$0" | cut -d: -f1) - 2))p" "$0" | sed 's/^# \?//'
}
warn() { printf '\033[1;33m!  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m!  %s\033[0m\n' "$*" >&2; exit 1; }

[ -x .venv/bin/python ] || die "No virtualenv at .venv/ — run ./install.sh first."

# --- PATH: this is load-bearing ----------------------------------------------
# The MCP client launches the Alpaca server as a subprocess via `uvx`, inheriting
# this process's PATH. install.sh puts uv inside .venv rather than on the system,
# so without this line the server is simply not found and every broker call dies
# with a bare FileNotFoundError that says nothing about the cause.
export PATH="$PWD/.venv/bin:$PATH"

# --- .env: parse, never source ------------------------------------------------
# Same rule as HAL's launcher: the file holds secrets and sourcing it would
# execute whatever is in there. We only need to read a couple of values.
# _env_val <file> <key>
_env_val() { sed -n "s/^$2=//p" "$1" 2>/dev/null | tail -1 | tr -d '"'\'''; }

MODE="loop"
ENV_NAME="dev"
ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    verify|preflight|test|loop|report|panel|soak) MODE="$1"; shift ;;
    -h|--help) usage; exit 0 ;;
    --env) ENV_NAME="${2:?--env needs dev or comp}"; shift 2 ;;
    --) shift; ARGS+=("$@"); break ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

# One file, two accounts. Which credentials get read is decided by the variable
# prefix below, not by which file we open — see src/halstreet/config.py.
ENV_FILE=".env"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Run ./install.sh, then fill in your paper keys."

# --- Refuse live credentials before doing anything ----------------------------
# Python asserts this too, at the point of every order. Checking here as well means
# a misconfigured launch fails immediately and visibly rather than after a scan.
DECLARED="$(_env_val "$ENV_FILE" ALPACA_ENV)"
[ "$DECLARED" = "paper" ] || die "ALPACA_ENV in $ENV_FILE is '${DECLARED:-unset}', not 'paper'. Refusing to start."

KEY_VAR=ALPACA_API_KEY; [ "$ENV_NAME" = "comp" ] && KEY_VAR=COMP_ALPACA_API_KEY
KEY="$(_env_val "$ENV_FILE" "$KEY_VAR")"
[ -n "$KEY" ] || die "$KEY_VAR is empty in $ENV_FILE.$([ "$ENV_NAME" = comp ] \
  && echo ' The judged run needs its own account — see docs/COMPETITION-ACCOUNT.md.')"

# The mistake one file makes visible and two files could not: the same account
# pasted under both names. Python refuses this too, at load_env.
if [ "$ENV_NAME" = "comp" ] && [ "$KEY" = "$(_env_val "$ENV_FILE" ALPACA_API_KEY)" ]; then
  die "COMP_ALPACA_API_KEY is the same credential as ALPACA_API_KEY — the judged run would trade the dev account."
fi
case "$KEY" in
  AK*) die "$KEY_VAR looks like a LIVE credential (AK…). Refusing to start." ;;
  PK*) : ;;
  *)   die "$KEY_VAR does not carry the paper PK… prefix. Refusing to guess." ;;
esac

banner
say "env=$ENV_NAME  key=${KEY:0:6}…  mode=$MODE  log=$LOG"

run() { say "$*"; "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }

# --- Can the virtualenv actually run this? ------------------------------------
#
# Every mode below shells into .venv/bin/python, so a venv that cannot import the
# package fails seven different ways depending on which one you typed. Checked once,
# here, and the real error is *shown* rather than swallowed.
#
# That last part is the point. This used to live inside the `loop` branch as
#
#     if ! .venv/bin/python -c 'import halstreet.agent.run' 2>/dev/null; then
#       warn "The agent loop isn't built yet (halstreet.agent.run does not exist)."
#
# — scaffolding from before the loop existed, kept long after it did. With stderr
# discarded, *any* import failure printed that line, so a stale virtualenv reported
# itself as a missing feature and sent a reader looking through the source for code
# that was sitting right there. A diagnostic that can state something false about the
# codebase is worse than no diagnostic.
if ! import_error="$(.venv/bin/python -c 'import halstreet' 2>&1)"; then
  warn "The virtualenv cannot import halstreet, so no mode can run. Python said:"
  printf '%s\n' "$import_error" | sed 's/^/      /' >&2
  case "$import_error" in
    *"No module named 'halstreet'"*)
      warn "halstreet is not installed in .venv. Run ./install.sh." ;;
    *"No module named"*)
      warn "A dependency is missing from .venv. Run ./install.sh." ;;
    *)
      warn "Run ./install.sh. If this survives a rebuild it is a code error, not setup." ;;
  esac
  exit 2
fi

case "$MODE" in
  verify)
    run .venv/bin/python -m halstreet.cli.verify --env "$ENV_NAME" "${ARGS[@]}"
    ;;
  preflight)
    run .venv/bin/python -m halstreet.cli.preflight --env "$ENV_NAME" "${ARGS[@]}"
    ;;
  test)
    run .venv/bin/python -m pytest tests -v "${ARGS[@]}"
    ;;
  report)
    run .venv/bin/python -m halstreet.cli.report --env "$ENV_NAME" "${ARGS[@]}"
    ;;
  soak)
    # A whole session, then a report of which lifecycle events the run actually
    # reached. The offline equivalent is tests/agent/test_soak.py.
    run .venv/bin/python -m halstreet.cli.soak --env "$ENV_NAME" "${ARGS[@]}"
    ;;
  panel)
    # Read-only telemetry view over the journal, ledger and circuit state. Safe to
    # start and stop mid-run; it holds no state and cannot reach the broker.
    run .venv/bin/python -m halstreet.cli.panel "${ARGS[@]}"
    ;;
  loop)
    run .venv/bin/python -m halstreet.agent.run --env "$ENV_NAME" "${ARGS[@]}"
    ;;
esac
