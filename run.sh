#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f "$HOME/.config/fads/runtime.env" ]]; then
  set -a
  source "$HOME/.config/fads/runtime.env"
  set +a
fi
exec ./node_modules/.bin/next start --hostname "${HOSTNAME:-127.0.0.1}" --port "${PORT:-8808}"
