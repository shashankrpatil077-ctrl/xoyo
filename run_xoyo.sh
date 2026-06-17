#!/bin/bash
# Run this in your own terminal: bash /home/shashank/xoyo/run_xoyo.sh
echo "🚀 Starting XOYO Omega..."
pkill -f "orchestrator/main.py" 2>/dev/null
sleep 1
cd /home/shashank/xoyo
source venv/bin/activate
python orchestrator/main.py
