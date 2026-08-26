#!/usr/bin/env bash
#
# HAL Street — one-shot installer.
#
# Far lighter than HAL's setup.sh: no GPU, no Ollama, no ML stack. What this needs
# is a Python venv, the package itself, and `uv` — because all broker traffic goes
# through Alpaca's MCP server, which ships as `uvx alpaca-mcp-server`. Idempotent:
# safe to re-run.
#
#   ./install.sh                everything the agent needs, plus the panel in a browser
#   ./install.sh --desktop      ...and the system libraries the Tauri window needs
#   ./install.sh --help
#
# The desktop shell is the one thing here that needs packages outside this directory,
# which is why it is a flag rather than the default: a repo installer should not reach
# for sudo unless it was asked to. Everything else — the agent, the gates, the CLIs,
# and the panel in a browser — installs with no root at all.
#
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!  %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m   %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

WANT_DESKTOP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --desktop) WANT_DESKTOP=1; shift ;;
    # The header comment is the help text; printing it means the two cannot drift.
    -h|--help) sed -n "3,$(($(grep -n '^set -euo' "$0" | cut -d: -f1) - 2))p" "$0" | sed 's/^# \?//'; exit 0 ;;
    *) warn "Unknown option $1"; exit 1 ;;
  esac
done

# --- 1. Pick a Python ---------------------------------------------------------
# pyproject requires >=3.11. Unlike HAL there are no ML pins to keep happy, so a
# newer interpreter is fine and we just take the best available.
PY=""
for v in python3.13 python3.12 python3.11 python3; do
  command -v "$v" >/dev/null 2>&1 && { PY="$v"; break; }
done
[ -n "$PY" ] || { warn "No python3 found. Install Python 3.11 or newer."; exit 1; }

PYMM="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
  warn "Python $PYMM is too old — HAL Street needs 3.11+."
  exit 1
fi
say "Using $($PY --version) at $(command -v "$PY")"

# venv support is a separate package on Debian/Ubuntu and its absence is the most
# common first-run failure. Check before we try, so the error names the fix.
if ! "$PY" -c 'import ensurepip' 2>/dev/null; then
  warn "This Python has no venv support. Install it first:"
  warn "    sudo apt-get install -y python${PYMM}-venv python3-pip"
  exit 1
fi

# --- 2. Virtualenv ------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  say "Creating .venv"
  "$PY" -m venv .venv
else
  say "Reusing existing .venv"
fi
.venv/bin/python -m pip install --quiet --upgrade pip

# --- 3. The package and its dev tools ----------------------------------------
say "Installing halstreet (editable) + dev tools"
.venv/bin/pip install --quiet -e ".[dev]"
ok "pydantic, httpx, mcp, python-dotenv, structlog, pandas, numpy, pytest, ruff, mypy"

# --- 4. uv, for the Alpaca MCP server ----------------------------------------
# The competition requires broker access via MCP or CLI rather than the REST API.
# Alpaca's official server runs as `uvx alpaca-mcp-server`, so uv is a hard
# dependency, not a convenience. Installed into the venv rather than the system so
# this repo stays self-contained — which is why start.sh puts .venv/bin on PATH.
say "Installing uv (runs the Alpaca MCP server)"
.venv/bin/pip install --quiet uv
ok "$(.venv/bin/uv --version)"

say "Pre-fetching alpaca-mcp-server so the first run isn't a download"
if PATH="$PWD/.venv/bin:$PATH" timeout 300 .venv/bin/uvx alpaca-mcp-server --help >/dev/null 2>&1; then
  ok "alpaca-mcp-server cached"
else
  # --help may exit non-zero depending on the server's CLI; the fetch still warms
  # the uv cache, so this is a note rather than a failure.
  warn "Could not confirm alpaca-mcp-server (network? proxy?). It will be fetched on first run."
fi

# --- 5. Config ----------------------------------------------------------------
if [ ! -f .env ]; then
  say "Creating .env from .env.example"
  cp .env.example .env
  warn "Fill in ALPACA_API_KEY / ALPACA_SECRET_KEY before running."
  warn "PAPER KEYS ONLY — they start with PK. Startup refuses anything else."
else
  ok ".env already present — leaving it alone"
fi

# One file, two accounts: the judged run reads COMP_* names from the same .env, so a
# dev run can never pick them up. Blank is normal until the competition account exists.
grep -q '^COMP_ALPACA_API_KEY=.' .env \
  || warn "COMP_ALPACA_API_KEY is blank — needed only for the judged run (docs/COMPETITION-ACCOUNT.md)."

# --- 6. Panel bundle ----------------------------------------------------------
# The only part of this repo that wants Node, and it is optional: the agent, the
# gates and every CLI work without it. Skipping leaves `./start.sh panel` serving its
# API with nothing to render, which it says plainly rather than failing obscurely.
if command -v npm >/dev/null 2>&1; then
  say "Building the telemetry panel (apps/desktop)"
  if (cd apps/desktop && npm install --no-fund --no-audit >/dev/null 2>&1 && npm run build >/dev/null 2>&1); then
    ok "panel built"
  else
    warn "Panel build failed — the agent is unaffected. Retry: cd apps/desktop && npm install && npm run build"
  fi
else
  warn "No npm — skipping the panel bundle. Everything except ./start.sh panel works without it."
fi

# --- 7. Desktop shell (optional) ----------------------------------------------
# `npm run tauri:dev` wraps the same panel in a native window. On Linux that needs
# WebKitGTK and a few build libraries from the system package manager — Tauri renders
# through the OS web view rather than shipping a browser, which is why the bundle is
# small and why these cannot come from npm.
#
# Nothing else in this repo needs any of it. The panel in a browser is the same page.

# Running inside a Flatpak (a sandboxed VS Code terminal, say) is worth detecting
# rather than muddling through. The sandbox has its own runtime, so a library the host
# has looks missing from in here, and `sudo apt-get` cannot reach the host's package
# manager at all. When the portal is available we ask the host the question instead of
# answering it wrongly.
IN_SANDBOX=0
[ -f /.flatpak-info ] && IN_SANDBOX=1

# Run a command where the answer is actually true: on the host when we are boxed in
# and can get out, otherwise right here.
sys() {
  if [ "$IN_SANDBOX" = 1 ] && command -v flatpak-spawn >/dev/null 2>&1; then
    flatpak-spawn --host sh -c "$1" 2>/dev/null
  else
    sh -c "$1" 2>/dev/null
  fi
}

desktop_packages() {
  # Echoes: <package manager label>|<install command>
  case "$(uname -s)" in
    Darwin)
      # WebKit is part of the OS; only the compiler toolchain is missing on a fresh Mac.
      if xcode-select -p >/dev/null 2>&1; then echo "macos|"; else echo "macos|xcode-select --install"; fi ;;
    Linux)
      if   sys 'command -v apt-get' >/dev/null 2>&1; then
        echo "apt|sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev"
      elif sys 'command -v dnf' >/dev/null 2>&1; then
        echo "dnf|sudo dnf install -y webkit2gtk4.1-devel openssl-devel curl wget file libappindicator-gtk3-devel librsvg2-devel && sudo dnf group install -y \"C Development Tools and Libraries\""
      elif sys 'command -v pacman' >/dev/null 2>&1; then
        echo "pacman|sudo pacman -S --needed --noconfirm webkit2gtk-4.1 base-devel curl wget file openssl appmenu-gtk-module libappindicator-gtk3 librsvg"
      elif sys 'command -v zypper' >/dev/null 2>&1; then
        echo "zypper|sudo zypper install -y webkit2gtk3-devel libopenssl-devel curl wget file libappindicator3-1 librsvg-devel"
      else
        echo "unknown|"
      fi ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows|" ;;
    *) echo "unknown|" ;;
  esac
}

desktop_ready() {
  case "$(uname -s)" in
    Darwin|MINGW*|MSYS*|CYGWIN*) return 0 ;;   # system web view, nothing to install
    *) sys 'pkg-config --exists webkit2gtk-4.1' ;;
  esac
}

say "Checking the desktop shell's system libraries"
[ "$IN_SANDBOX" = 1 ] && note "(inside a Flatpak sandbox — asking the host, not this runtime)"
IFS='|' read -r PKGMGR PKGCMD <<EOF
$(desktop_packages)
EOF

if desktop_ready; then
  ok "webkit2gtk-4.1 present — the Tauri window will build"
elif [ "$WANT_DESKTOP" = 1 ] && [ -z "$PKGCMD" ]; then
  warn "No known package manager here ($PKGMGR). Install WebKitGTK 4.1 and a C toolchain,"
  warn "then see https://tauri.app/start/prerequisites/"
elif [ "$WANT_DESKTOP" = 1 ] && [ "$IN_SANDBOX" = 1 ]; then
  warn "This shell is inside a Flatpak sandbox, which cannot install host packages."
  note "Run this in a terminal on the host:"
  note "  $PKGCMD"
elif [ "$WANT_DESKTOP" = 1 ]; then
  say "Installing them with $PKGMGR (this needs sudo)"
  note "$PKGCMD"
  # Deliberately not silenced: sudo is about to ask for a password, and the package
  # list is exactly what someone should be able to read before typing it.
  if eval "$PKGCMD"; then
    if desktop_ready; then
      ok "webkit2gtk-4.1 installed"
    else
      warn "Installed, but pkg-config still cannot see webkit2gtk-4.1. Check PKG_CONFIG_PATH."
    fi
  else
    warn "Package install failed — the agent and the browser panel are unaffected."
  fi
else
  warn "webkit2gtk-4.1 is missing — only the Tauri window needs it."
  note "The panel in a browser (./start.sh panel) works without it."
  note "To install:  ./install.sh --desktop"
  [ -n "$PKGCMD" ] && note "which runs:  $PKGCMD"
fi

# Tauri also needs a Rust toolchain, which is a user-level install rather than a
# system one — so it is pointed at, never installed behind someone's back.
if [ "$WANT_DESKTOP" = 1 ] && ! sys 'command -v cargo' >/dev/null 2>&1; then
  warn "No cargo — the Tauri window also needs Rust: https://rustup.rs"
fi

# --- 8. Smoke test ------------------------------------------------------------
say "Running the test suite"
if .venv/bin/python -m pytest tests -q; then
  ok "tests pass"
else
  warn "Tests failed — the install is probably fine, but something is wrong. Look above."
  exit 1
fi

say "Done."
cat <<'EOF'
   Next:
     ./start.sh verify       scan a live chain, build structures, submit nothing
     ./start.sh verify -- --submit
                             place the test structures (PAPER, dev account)
     ./start.sh preflight    check the competition account is clean
     ./start.sh              run the agent loop
     ./start.sh panel        read-only panel at http://127.0.0.1:8787

   All broker traffic goes through Alpaca's MCP server. Paper only — the startup
   assertion refuses live credentials and cannot be turned off.
EOF
