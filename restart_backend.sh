#!/bin/bash
set -euo pipefail

echo "Restarting AutoBaza Parser API..."
echo "=================================="

# Run from the repository root regardless of the caller's cwd
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

echo "Stopping existing backend processes..."
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 2

echo "Starting backend server on port 8000..."
echo "The server reloads automatically on code changes."
echo "API: http://localhost:8000  Docs: http://localhost:8000/docs"
echo "Press Ctrl+C to stop the server"
echo "=================================="

# main.py hydrates os.environ from the repo-local .env on startup,
# so the bare uvicorn command needs no --env-file flag.
exec uvicorn main:app --reload --host 0.0.0.0 --port 8000
