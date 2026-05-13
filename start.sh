#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.logs"

mkdir -p "$LOG_DIR" "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/workspaces"

if ! command -v xelatex >/dev/null 2>&1; then
  echo "Warning: xelatex is not installed. PDF/Chinese LaTeX reports will not compile."
  echo "Install once with: ./scripts/install-system-deps.sh"
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

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/backend.pid"

cd "$FRONTEND_DIR"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run dev -- --host 0.0.0.0 --port 3000 > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/frontend.pid"

echo "LAMBDA Local is starting."
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "Logs:     $LOG_DIR"
