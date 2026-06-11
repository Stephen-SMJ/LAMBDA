#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

for pid_file in "$ROOT_DIR"/backend*.pid "$ROOT_DIR"/frontend*.pid; do
  if [[ -f "$pid_file" ]]; then
    kill "$(cat "$pid_file")" 2>/dev/null || true
    rm -f "$pid_file"
  fi
done

echo "LAMBDA Local stopped."
