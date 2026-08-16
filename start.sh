#!/bin/bash
# Starts the whole stack: mosquitto (if installed), backend, dashboard.
# Run from the project root:  ./start.sh
# Ctrl+C stops everything it started.

set -e
cd "$(dirname "$0")"

# --- 1. Mosquitto (MQTT broker) ---
if command -v mosquitto >/dev/null 2>&1; then
  if ! pgrep -x mosquitto >/dev/null 2>&1; then
    echo "Starting mosquitto..."
    mosquitto -d
  else
    echo "mosquitto already running."
  fi
else
  echo "mosquitto not found on PATH — skipping (backend will retry MQTT in the background)."
fi

# --- 2. Backend (FastAPI/uvicorn) ---
echo "Starting backend..."
cd "Source Code/backend"
PORT=8000
PID=$(lsof -ti tcp:$PORT || true)
if [ -n "$PID" ]; then
  echo "Killing existing process on port $PORT (pid $PID)..."
  kill "$PID"
  sleep 1
fi
source venv/bin/activate
uvicorn app.main:app --reload --port $PORT > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..
echo "Backend starting (pid $BACKEND_PID) — logging to backend.log"

# Give it a moment, then sanity-check it actually came up.
sleep 2
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo "Backend failed to start — check backend.log:"
  tail -n 30 backend.log
  exit 1
fi

# --- 3. Dashboard (Vite dev server) ---
echo "Starting dashboard..."
cleanup() {
  echo ""
  echo "Stopping backend (pid $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "Source Code/dashboard"
npm run dev
