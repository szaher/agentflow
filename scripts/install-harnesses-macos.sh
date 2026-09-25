#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

run() {
  echo "+ $*"
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper intentionally targets macOS. Use the vendors' official install docs on other systems." >&2
  exit 2
fi

command -v brew >/dev/null || { echo "Homebrew is required for this helper." >&2; exit 2; }
command -v npm >/dev/null || { echo "npm/Node.js is required for Pi." >&2; exit 2; }

command -v claude >/dev/null || run brew install --cask claude-code
command -v codex >/dev/null || run brew install --cask codex
command -v pi >/dev/null || run npm install -g --ignore-scripts @earendil-works/pi-coding-agent

echo
[[ "$DRY_RUN" == "1" ]] && { echo "Dry run complete."; exit 0; }

echo "Installed binaries (where available):"
command -v claude >/dev/null && claude --version || true
command -v codex >/dev/null && codex --version || true
command -v pi >/dev/null && pi --version || true

echo
printf '%s\n' "Authentication is intentionally not automated:" \
  "  Claude Code: run 'claude' and sign in" \
  "  Codex:       run 'codex' and sign in" \
  "  Pi:          run 'pi', then /login"
