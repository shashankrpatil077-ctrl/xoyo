#!/bin/bash
echo "🛑 Stopping all XOYO services..."

# 1. Kill daemon and self_improve first
pkill -f "python.*xoyo_daemon.py" 2>/dev/null || true
pkill -f "python.*self_improve.py" 2>/dev/null || true
sleep 1

# 2. Kill orchestrator and all services
pkill -f "/home/shashank/xoyo/venv/bin/python.*orchestrator/main.py" 2>/dev/null || true
pkill -f "/home/shashank/xoyo/venv/bin/python.*services/" 2>/dev/null || true
pkill -f "playwright.*browser" 2>/dev/null || true

# 3. Aggressively kill processes holding XOYO ports to prevent [Errno 98]
echo "🧹 Cleaning up held ports (8000-9005)..."
pids=$(lsof -ti tcp:8000-9005 2>/dev/null)
if [ ! -z "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
fi

# 4. Clean up any remaining python processes related to xoyo
kill -9 $(ps aux | grep '[p]ython' | grep 'xoyo' | awk '{print $2}') 2>/dev/null || true

# 5. Clean stale Redis state
redis-cli DEL xoyo:pending_actions xoyo:status 2>/dev/null || true

echo "✅ All XOYO services have been shut down and ports cleared."
