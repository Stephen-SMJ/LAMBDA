# LAMBDA Local

Local-first data analysis agent with the same LAMBDA chat UI, local file storage,
SQLite persistence, and local code execution.

This repository is the open-source/local edition. It does not require
PostgreSQL, Aliyun OSS, OpenSandbox, Docker, invite codes, email verification,
Cloudflare Turnstile, or an admin backend.

## Features

- Chat-based data analysis with tool execution.
- Local-only single-user mode. No login, registration, invite code, admin panel,
  public case study publishing, or cloud account is required.
- Local Python and shell tools.
- Persistent Python variables within the same conversation.
- Local workspaces under `backend/data/workspaces/<conversation_id>`.
- Local SQLite database at `backend/data/lambda_local.db`.
- File upload, generated file gallery, PDF/report artifacts, and chat history.
- English/Chinese UI and prompt preference support.
- Compatible with OpenAI-compatible model APIs.

## Security Model

This local edition executes code on the host machine. It is intended for trusted
single-user desktop/local deployments. Do not expose the backend directly to
untrusted users unless you add isolation back with Docker, OpenSandbox, or a
similar sandbox.

## Quick Start

Requirements:

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- Optional for PDF/Chinese reports: TeX Live with XeLaTeX

Start both backend and frontend. Python packages from `backend/requirements.txt`
are installed automatically into the local virtual environment:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set OPENAI_API_KEY / OPENAI_BASE_URL / DEFAULT_MODEL.
./start.sh
```

Open:

```text
http://localhost:3000
```

If those ports are already used, choose different local ports:

```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 ./start.sh
```

Stop:

```bash
./stop.sh
```

## Manual Setup

Backend:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Optional LaTeX Support

Install these system dependencies once if you want LAMBDA Local to compile
LaTeX/PDF reports, including Chinese reports:

```bash
./scripts/install-system-deps.sh
```

This installs `pdflatex`, `xelatex`, Chinese LaTeX packages (`xeCJK`/`ctex`),
and Noto CJK fonts for Chinese charts.

If you want `./start.sh` to install these system packages automatically when
`xelatex` is missing, run:

```bash
LAMBDA_AUTO_INSTALL_SYSTEM_DEPS=1 ./start.sh
```

This uses `sudo apt-get`, so it is opt-in rather than silently modifying the OS.

## Configuration

Core local settings in `backend/.env`:

```env
LOCAL_MODE=true
DATABASE_URL=sqlite:///./data/lambda_local.db
FILE_STORAGE_MODE=local
CODE_EXECUTION_MODE=local
LOCAL_WORKSPACE_ROOT=./data/workspaces

OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini
```

Optional model providers:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
XIAOMI_API_KEY=
XIAOMI_BASE_URL=https://token-plan-sgp.xiaomimimo.com/v1
```

## Data Layout

Runtime files are intentionally ignored by git:

```text
backend/data/
  lambda_local.db
  uploads/
  workspaces/
```

Generated charts, reports, notebooks, and other artifacts are stored inside the
conversation workspace and shown through the Files panel.

## Desktop App Direction

The recommended desktop path is Tauri:

- Keep this FastAPI backend as a local sidecar process.
- Package the React frontend with Tauri.
- Start/stop the backend from the desktop shell.
- Store user data under the OS app data directory instead of the repo directory.

Electron is also possible, but Tauri is usually smaller and better suited for a
local utility app.
