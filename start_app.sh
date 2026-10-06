#!/bin/bash
# Room Rent Manager — Launcher
# Double-click this file or run it in Terminal to start the app

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/rent-app"
PYTHON="$ROOT_DIR/.venv-1/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi
PORT="${PORT:-8080}"

echo "🏠 Room Rent Manager"
echo "================================"

# Check if database exists, init if not
if [ ! -f "data/rent.db" ]; then
    echo "⚙️  First run — importing your Excel data..."
    "$PYTHON" init_db.py
    echo ""
fi

echo "✅ Starting server at http://localhost:$PORT"
echo "   Press Ctrl+C to stop the server"
echo ""

# Open browser after 2 seconds
(sleep 2 && open "http://localhost:$PORT") &

PORT="$PORT" "$PYTHON" app.py
