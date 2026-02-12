#!/usr/bin/env bash
set -euo pipefail

# Nanoclaw installer for macOS/Linux
# Usage: curl -fsSL https://openclaw.ai/install.sh | bash

PKG_NAME="nanoclaw-ai"
REPO_URL="https://github.com/luthebao/nanoclaw.git"
INSTALL_METHOD="${NANOCLAW_INSTALL_METHOD:-pypi}" # pypi | git
GIT_DIR="${NANOCLAW_GIT_DIR:-$HOME/nanoclaw}"

info() {
  printf "\033[36m[INFO]\033[0m %s\n" "$*"
}

ok() {
  printf "\033[32m[OK]\033[0m %s\n" "$*"
}

warn() {
  printf "\033[33m[WARN]\033[0m %s\n" "$*"
}

err() {
  printf "\033[31m[ERROR]\033[0m %s\n" "$*" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    return 1
  fi
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    ok "uv already installed"
    return 0
  fi

  info "Installing uv..."
  require_cmd curl
  curl -LsSf https://astral.sh/uv/install.sh | sh

  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  fi

  require_cmd uv
  ok "uv installed"
}

ensure_on_path_notice() {
  if command -v nanoclaw >/dev/null 2>&1; then
    return 0
  fi

  warn "'nanoclaw' not found in current PATH yet."
  warn "Open a new terminal or add ~/.local/bin to PATH:"
  printf '  export PATH="$HOME/.local/bin:$PATH"\n'
}

install_from_pypi() {
  info "Installing ${PKG_NAME} from PyPI via uv tool..."
  uv tool install --upgrade "$PKG_NAME"
  ok "Installed ${PKG_NAME}"
}

install_from_git() {
  require_cmd git
  info "Installing from git checkout: ${REPO_URL}"

  if [ ! -d "$GIT_DIR/.git" ]; then
    git clone "$REPO_URL" "$GIT_DIR"
  else
    info "Repo exists at $GIT_DIR, updating..."
    git -C "$GIT_DIR" pull --rebase
  fi

  uv tool install --upgrade "$GIT_DIR"
  ok "Installed nanoclaw from $GIT_DIR"
}

main() {
  info "Nanoclaw Installer"

  case "$INSTALL_METHOD" in
    pypi|git) ;;
    *)
      err "Invalid NANOCLAW_INSTALL_METHOD: $INSTALL_METHOD (expected: pypi|git)"
      exit 2
      ;;
  esac

  install_uv

  if [ "$INSTALL_METHOD" = "git" ]; then
    install_from_git
  else
    install_from_pypi
  fi

  ensure_on_path_notice

  if command -v nanoclaw >/dev/null 2>&1; then
    ok "nanoclaw version: $(nanoclaw --version 2>/dev/null || echo installed)"
    ok "Run: nanoclaw onboard"
  else
    ok "Install completed"
  fi
}

main "$@"
