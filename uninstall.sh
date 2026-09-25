#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${AGENTFLOW_INSTALL_ROOT:-$HOME/.local/share/agentflow-meta}"
BIN_DIR="${AGENTFLOW_BIN_DIR:-$HOME/.local/bin}"
rm -rf "$INSTALL_ROOT"
rm -f "$BIN_DIR/agentflow"
echo "Removed Agentflow."
