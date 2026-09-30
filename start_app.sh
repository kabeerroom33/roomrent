#!/bin/bash
# Room Rent Manager — Launcher
# Double-click this file or run it in Terminal to start the app

cd "$(dirname "$0")/rent-app"

echo "🏠 Room Rent Manager"
echo "================================"

# Check if database exists, init if not
if [ ! -f "data/rent.db" ]; then
    echo "⚙️  First run — importing your Excel data..."
    python3 init_db.py
    echo ""
fi

echo "✅ Starting server at http://localhost:8080"
echo "   Press Ctrl+C to stop the server"
echo ""

# Open browser after 2 seconds
(sleep 2 && open http://localhost:8080) &

python3 app.py
