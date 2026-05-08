#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "🚀 Starting AL_price_action paper trading system..."

if [ -d "$BACKEND_DIR/.venv" ]; then
    BACKEND_VENV="$BACKEND_DIR/.venv"
elif [ -d "$BACKEND_DIR/venv" ]; then
    BACKEND_VENV="$BACKEND_DIR/venv"
else
    echo "📦 Creating Python virtual environment at backend/.venv..."
    python3 -m venv "$BACKEND_DIR/.venv"
    BACKEND_VENV="$BACKEND_DIR/.venv"
    "$BACKEND_VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
fi

if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "⚠️  Warning: backend/.env not found. Alpaca trading/streaming will be disabled."
fi

BACKEND_PID=""
FRONTEND_PID=""
STARTED_ANY=0

cleanup() {
    if [ -n "${BACKEND_PID:-}${FRONTEND_PID:-}" ]; then
        echo "🛑 Stopping services..."
        [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
        [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

backend_healthy() {
    "$BACKEND_VENV/bin/python" - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:$BACKEND_PORT/api/health', timeout=2).read()
PY
}

port_listening() {
    "$BACKEND_VENV/bin/python" - "$1" "$2" <<'PY' >/dev/null 2>&1
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
s = socket.socket()
s.settimeout(1)
try:
    s.connect((host, port))
finally:
    s.close()
PY
}

# Start backend unless a healthy backend is already serving the target port.
if backend_healthy; then
    echo "✅ Backend already healthy on http://127.0.0.1:$BACKEND_PORT; reusing it."
else
    if port_listening 127.0.0.1 "$BACKEND_PORT"; then
        echo "❌ Port $BACKEND_PORT is already occupied, but /api/health is not healthy."
        echo "   Stop the existing process or start with BACKEND_PORT=<free_port> ./start.sh"
        exit 1
    fi

    echo "🐍 Starting backend on http://127.0.0.1:$BACKEND_PORT ..."
    (
        cd "$BACKEND_DIR"
        source "$BACKEND_VENV/bin/activate"
        exec uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT"
    ) &
    BACKEND_PID=$!
    STARTED_ANY=1

    # Wait for backend health instead of blind sleep.
    for _ in {1..30}; do
        if backend_healthy; then
            break
        fi
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "❌ Backend exited during startup"
            wait "$BACKEND_PID"
        fi
        sleep 1
    done

    if ! backend_healthy; then
        echo "❌ Backend did not become healthy on port $BACKEND_PORT"
        exit 1
    fi
fi

# Start frontend unless something is already serving the target port.
if port_listening "$FRONTEND_HOST" "$FRONTEND_PORT"; then
    echo "✅ Frontend port already in use at http://$FRONTEND_HOST:$FRONTEND_PORT; reusing it."
else
    echo "⚛️  Starting frontend on http://$FRONTEND_HOST:$FRONTEND_PORT ..."
    (
        cd "$FRONTEND_DIR"
        exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
    ) &
    FRONTEND_PID=$!
    STARTED_ANY=1
fi

echo ""
echo "✅ System started!"
echo "   Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "   Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "   API Docs: http://127.0.0.1:$BACKEND_PORT/docs"
echo ""
if [ "$STARTED_ANY" -eq 1 ]; then
    echo "Press Ctrl+C to stop services started by this script"
    wait
else
    echo "No new services were started; existing services are already available."
fi
