#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.logs"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "$LOG_DIR" "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/workspaces"

if ! command -v xelatex >/dev/null 2>&1; then
  if [[ "${LAMBDA_AUTO_INSTALL_SYSTEM_DEPS:-0}" == "1" ]]; then
    echo "xelatex is not installed. Installing LaTeX and CJK fonts..."
    "$ROOT_DIR/scripts/install-system-deps.sh"
  else
    echo "Warning: xelatex is not installed. PDF/Chinese LaTeX reports will not compile."
    echo "Install once with: ./scripts/install-system-deps.sh"
    echo "Or run with LAMBDA_AUTO_INSTALL_SYSTEM_DEPS=1 ./start.sh to install automatically."
  fi
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo "Created backend/.env. Edit it with your model API key if needed."
fi

cd "$BACKEND_DIR"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/backend.pid"

cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
  npm install
fi
VITE_DEV_API_TARGET="http://127.0.0.1:$BACKEND_PORT" npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/frontend.pid"

echo "LAMBDA Local is starting."
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Logs:     $LOG_DIR"
