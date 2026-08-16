#!/bin/bash
# Same as restart.sh, but binds to 0.0.0.0 so the backend alone is reachable
# from other devices on the same network (not just this machine).
# Run from inside the backend/ folder:  ./restart_lan.sh
set -e

PORT=8000

PID=$(lsof -ti tcp:$PORT || true)
if [ -n "$PID" ]; then
  echo "Stopping existing process(es) on port $PORT ($(echo $PID | tr '\n' ' '))..."
  kill $PID 2>/dev/null || true
  sleep 1
fi

echo "Starting backend (LAN-accessible)..."
uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT
