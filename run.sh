#!/usr/bin/env bash
set -euo pipefail

# Lucid Voice — local dev launcher.
# Starts the FastAPI backend and the Vite frontend together.
# Run from anywhere; paths are resolved relative to this script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

# --- Prerequisite checks -----------------------------------------------------
# The ML/web deps require Python >= 3.10. macOS often ships an older stock
# python3 (e.g. 3.9), so probe known names and pick the first >= 3.10.
PYTHON=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$cand"
      break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  echo "ERROR: no Python >= 3.10 found. Install Python 3.11+ and try again." >&2
  echo "       (found: $(python3 --version 2>&1 || echo 'none'))" >&2
  exit 1
fi
echo "==> Using $PYTHON ($("$PYTHON" --version 2>&1))"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node not found. Install Node 18+ and try again." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found. Install Node 18+ (which provides npm) and try again." >&2
  exit 1
fi

# FFmpeg is required by Coqui XTTS-v2 (torchcodec) for local voice synthesis.
# Not fatal: /speak still serves cached audio and falls back gracefully without it.
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg not found — local XTTS voice synthesis will be unavailable" >&2
  echo "         (cached + ElevenLabs paths still work). Install: brew install ffmpeg" >&2
fi

# --- Backend: virtualenv -----------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating Python virtualenv at backend/.venv"
  "$PYTHON" -m venv "$VENV_DIR"
else
  echo "==> Reusing existing virtualenv at backend/.venv"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# --- Backend: dependencies ---------------------------------------------------
REQUIREMENTS="$BACKEND_DIR/requirements.txt"
STAMP="$VENV_DIR/.requirements.stamp"
if [ ! -f "$STAMP" ] || [ "$REQUIREMENTS" -nt "$STAMP" ]; then
  echo "==> Installing backend dependencies (this can take a while; ML deps are heavy)"
  pip install --upgrade pip >/dev/null
  pip install -r "$REQUIREMENTS"
  touch "$STAMP"
else
  echo "==> Backend dependencies up to date; skipping install"
fi

# --- Backend: .env -----------------------------------------------------------
if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo "==> Creating backend/.env from .env.example"
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
else
  echo "==> backend/.env already exists; leaving it untouched"
fi

# --- Launch backend in the background ----------------------------------------
echo "==> Starting backend on http://localhost:8000"
(
  cd "$BACKEND_DIR"
  exec uvicorn app.main:app --reload --port 8000
) &
BACKEND_PID=$!

# Kill the backend when this script exits for any reason.
cleanup() {
  echo ""
  echo "==> Shutting down backend (pid $BACKEND_PID)"
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- Frontend: dependencies --------------------------------------------------
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "==> Installing frontend dependencies"
  (cd "$FRONTEND_DIR" && npm install)
else
  echo "==> Frontend dependencies present; skipping npm install"
fi

# --- Launch frontend in the foreground ---------------------------------------
echo "==> Starting frontend on http://localhost:5173"
echo "    (Ctrl-C to stop both servers)"
(cd "$FRONTEND_DIR" && npm run dev)
