#!/bin/bash
# Kills any running backend (uvicorn) on port 8000 and starts it fresh.
# Run this from inside the backend/ folder:  ./restart.sh
set -e

PORT=8000

PID=$(lsof -ti tcp:$PORT || true)
if [ -n "$PID" ]; then
  echo "Stopping existing backend (pid $PID) on port $PORT..."
  kill "$PID"
  sleep 1
fi

echo "Starting backend..."
uvicorn app.main:app --reload --port $PORT
