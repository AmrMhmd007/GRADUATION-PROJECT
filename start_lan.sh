#!/bin/bash
# Same as start.sh, but exposes the backend + dashboard on your local
# network (Wi-Fi/Ethernet) instead of just this machine, so someone else
# on the same network — e.g. a friend testing the system — can open it too.
# Run from the project root:  ./start_lan.sh
# Ctrl+C stops everything it started.

set -e
cd "$(dirname "$0")"

# --- 0. Find this Mac's LAN IP. ---
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
if [ -z "$LAN_IP" ]; then
  echo "Couldn't detect a LAN IP automatically (not on Wi-Fi/Ethernet?) — falling back to localhost-only."
  LAN_IP="localhost"
fi

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
  echo "Killing existing process(es) on port $PORT ($(echo $PID | tr '\n' ' '))..."
  # Deliberately unquoted so multiple PIDs (one per line) word-split into
  # separate arguments — quoting "$PID" here passes them as one invalid
  # multi-line argument and kill rejects it.
  kill $PID 2>/dev/null || true
  sleep 1
fi
source venv/bin/activate
# --host 0.0.0.0 makes it listen on every network interface, not just
# localhost, so another device on the same Wi-Fi can actually reach it.
uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT > ../backend.log 2>&1 &
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
echo ""
echo "=================================================================="
echo " Share this link with your friend (same Wi-Fi network required):"
echo "   http://$LAN_IP:5173"
echo "=================================================================="
echo ""
cleanup() {
  echo ""
  echo "Stopping backend (pid $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "Source Code/dashboard"
# --host exposes the dev server on the LAN too (default is localhost-only).
# VITE_API_BASE_URL points the dashboard's own API calls at this Mac's LAN
# IP instead of "localhost" — otherwise your friend's browser would try to
# reach a backend running on *their* machine, which doesn't exist.
VITE_API_BASE_URL="http://$LAN_IP:8000" npm run dev -- --host
