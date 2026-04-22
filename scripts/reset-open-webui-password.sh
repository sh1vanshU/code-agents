#!/usr/bin/env bash
# Reset Open WebUI password(s) in webui.db (bcrypt). Stop "open-webui serve" first.
#
# Examples:
#   ./scripts/reset-open-webui-password.sh '12345678'           # all users
#   ./scripts/reset-open-webui-password.sh 'secret' --email 'you@example.com'
#   OPEN_WEBUI_RESET_PASSWORD='12345678' ./scripts/reset-open-webui-password.sh
#   ./scripts/reset-open-webui-password.sh --dry-run
#
# Optional: OPEN_WEBUI_PYTHON=/path/to/venv/bin/python if open-webui is not on PATH.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# pipx installs ~/.local/bin/open-webui as a symlink into the venv; dirname must follow it.
_real_path() {
  local p=$1
  while [[ -L "$p" ]]; do
    local target
    target=$(readlink "$p")
    if [[ $target != /* ]]; then
      target="$(dirname "$p")/$target"
    fi
    p=$target
  done
  printf '%s' "$p"
}

resolve_python() {
  if [[ -n "${OPEN_WEBUI_PYTHON:-}" ]]; then
    printf '%s' "$OPEN_WEBUI_PYTHON"
    return 0
  fi
  local bin real
  bin=$(command -v open-webui) || return 1
  real=$(_real_path "$bin")
  printf '%s' "$(dirname "$real")/python"
}

if ! PY="$(resolve_python)"; then
  echo "open-webui not on PATH and OPEN_WEBUI_PYTHON unset." >&2
  echo "Install: pipx install open-webui --python python3.12" >&2
  echo "Or set OPEN_WEBUI_PYTHON to the venv python that has open_webui installed." >&2
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/reset_open_webui_password.py" "$@"
