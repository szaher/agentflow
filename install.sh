#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${AGENTFLOW_HOME:-$HOME/.local/share/agentflow}"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$DEST" "$BIN_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '.git' "$SOURCE_DIR/" "$DEST/"
else
  rm -rf "$DEST"
  mkdir -p "$DEST"
  cp -a "$SOURCE_DIR/." "$DEST/"
fi
ln -sfn "$DEST/bin/agentflow" "$BIN_DIR/agentflow"
chmod +x "$DEST/bin/agentflow" "$DEST/scripts/"*.sh 2>/dev/null || true

echo "Installed Agentflow to: $DEST"
echo "CLI: $BIN_DIR/agentflow"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo 'Add ~/.local/bin to PATH. For zsh, add this line to ~/.zshrc:'
    echo 'export PATH="$HOME/.local/bin:$PATH"'
    ;;
esac
