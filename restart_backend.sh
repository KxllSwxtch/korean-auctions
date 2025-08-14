#!/bin/bash

echo "🔄 Restarting KCar Backend Server..."
echo "=================================="

# Navigate to backend directory
cd /Users/admin/Desktop/Coding/AutoBaza/backend

# Activate virtual environment
source venv/bin/activate

# Kill any existing uvicorn processes
echo "📍 Stopping existing backend processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

# Start the backend server
echo "🚀 Starting backend server on port 8000..."
echo "📌 The server will reload automatically when you make changes"
echo ""
echo "Access the API at: http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=================================="

# Run uvicorn with auto-reload
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0