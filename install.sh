#!/usr/bin/env bash
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${AGENTFLOW_INSTALL_ROOT:-$HOME/.local/share/agentflow-meta}"
BIN_DIR="${AGENTFLOW_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$(dirname "$INSTALL_ROOT")" "$BIN_DIR"
rm -rf "$INSTALL_ROOT"
mkdir -p "$INSTALL_ROOT"
cp -R "$SRC/src" "$SRC/bin" "$SRC/examples" "$INSTALL_ROOT/"
cp "$SRC/README.md" "$SRC/ARCHITECTURE.md" "$SRC/LICENSE" "$SRC/pyproject.toml" "$INSTALL_ROOT/"
cat > "$BIN_DIR/agentflow" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="$INSTALL_ROOT/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m agentflow "\$@"
WRAPPER
chmod +x "$BIN_DIR/agentflow"
echo "Installed Agentflow to $INSTALL_ROOT"
echo "Launcher: $BIN_DIR/agentflow"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH if needed." ;;
esac
"$BIN_DIR/agentflow" --version
