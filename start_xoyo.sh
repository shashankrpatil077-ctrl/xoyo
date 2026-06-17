#!/bin/bash
set -uo pipefail
# XOYO Omega — i3‑1115G4, 8 GB Complete Launch
export DISPLAY=${DISPLAY:-:0}
cd /home/shashank/xoyo
export PYTHONPATH=/home/shashank/xoyo
echo "🚀 Booting XOYO Omega..."

# Create a logs directory to prevent the terminal from getting spammed
mkdir -p logs

echo "1/10: Starting Core Infrastructure (Redis)..."
redis-server --daemonize yes || true

# Activate virtual environment
source venv/bin/activate

echo "2/10: Starting Orchestrator & Massive Workers..."
# Call stop script to ensure a completely clean slate
./stop_xoyo.sh

# Start the Mythos-Class OS Controller (Unrestricted Subsystem)
/home/shashank/xoyo/venv/bin/python services/mythos_os.py > logs/mythos_os.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)
/home/shashank/xoyo/venv/bin/python orchestrator/main.py > logs/orchestrator.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 2 removed)
/home/shashank/xoyo/venv/bin/python services/workers_massive.py > logs/workers_massive.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "3/10: Starting Scientific & Reasoning Engines..."
/home/shashank/xoyo/venv/bin/python services/active_inference.py > logs/active_inference.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/advanced_idle.py > logs/advanced_idle.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/bayesian_surprise.py > logs/bayesian_surprise.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/debate_service.py > logs/debate.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/dreamer_server.py > logs/dreamer.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/hyperagents_dgm.py > logs/dgm.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/materials_discovery.py > logs/materials.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/math_services.py > logs/math.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/nngpt_service.py > logs/nngpt.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/physics_server.py > logs/physics.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/bmssp_solver.py > logs/bmssp_solver.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/era_engine.py > logs/era_engine.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "4/10: Starting Heavy ML Services (DISABLED FOR LITE MODE)..."
# /home/shashank/xoyo/venv/bin/python services/florence_server.py > logs/florence_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/mamba_server.py > logs/mamba_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/nitro_server.py > logs/nitro_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/rwkv_server.py > logs/rwkv_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/smolvla_server.py > logs/smolvla_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/dino_server.py > logs/dino_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/llm_server.py > logs/llm_server.log 2>&1 || true &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "5/10: Starting Memory & Safety..."
/home/shashank/xoyo/venv/bin/python services/memory_manager.py > logs/memory.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/memory_advanced.py > logs/memory_advanced.log 2>&1 &  # DISABLED (Crash risk)
/home/shashank/xoyo/venv/bin/python services/constitutional_ai.py > logs/constitutional.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/intent_bnn.py > logs/intent.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/flow_policy.py > logs/flow.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/priority_engine.py > logs/priority.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/diag2diag.py > logs/diag2diag.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "6/10: Starting Perception & Voice Systems (DISABLED FOR 8GB LITE MODE)..."
# /home/shashank/xoyo/venv/bin/python services/camera_server.py > logs/camera.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/yolo_server.py > logs/yolo.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/vision_server.py > logs/vision.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/wakeword_server.py > logs/wakeword.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/affective_loop.py > logs/affective.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/prosody_server.py > logs/prosody.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/scene_generator.py > logs/scene.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/neural_tts.py > logs/neural_tts.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/whisper_server.py > logs/whisper_server.log 2>&1 || true &  # DISABLED (Too slow on i3)
# /home/shashank/xoyo/venv/bin/python services/screen_awareness.py > logs/screen_awareness.log 2>&1 || true & # DISABLED (Memory leak risk)
# boot optimized (sleep 1 removed)

echo "7/10: Starting XOYO Tools & Generators..."
/home/shashank/xoyo/venv/bin/python services/progress_vocalizer.py > logs/progress_vocalizer.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/memory_personal.py > logs/memory_personal.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/memory_retrieval.py > logs/memory_retrieval.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/ppt_generator.py > logs/ppt_generator.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/docx_generator.py > logs/docx_generator.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/image_generator.py > logs/image_generator.log 2>&1 & # DISABLED (Needs OpenVINO fix)
/home/shashank/xoyo/venv/bin/python services/desktop_control.py > logs/desktop_control.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/system_monitor.py > logs/system_monitor.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/web_agent.py > logs/web_agent.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/office_agent.py > logs/office_agent.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/google_agent.py > logs/google_agent.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/xoyo_agent_builder.py > logs/xoyo_agent_builder.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "8/10: Starting Metacognitive Watchdogs + Event Bridge..."
/home/shashank/xoyo/venv/bin/python services/stuck_detector.py > logs/stuck_detector.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/agent_trace.py > logs/agent_trace.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/task_doctor.py > logs/task_doctor.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/interrupt_fsm.py > logs/interrupt_fsm.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/ws_event_bridge.py > logs/ws_event_bridge.log 2>&1 &
# boot optimized (sleep 3 removed)
# boot optimized (sleep 1 removed)

echo "9/10: Task Queue (DISABLED FOR LITE MODE)..."
# /home/shashank/xoyo/venv/bin/python services/celery_setup.py > logs/celery_setup.log 2>&1 || true & # DISABLED (Redundant)
# /home/shashank/xoyo/venv/bin/python services/task_queue.py > logs/task_queue.log 2>&1 || true &     # DISABLED (Redundant)
# task_manager.py is a library module (no port) — imported by orchestrator, not started separately
# boot optimized (sleep 1 removed)

echo "10/10: Starting Background Daemons & Activity Stream..."
/home/shashank/xoyo/venv/bin/python services/crystallization_daemon.py > logs/crystallization.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python self_improve.py > logs/self_improve.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/memory_consolidator.py > logs/consolidation.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/voice_pipeline.py > logs/voice_pipeline.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python services/deep_research.py > logs/deep_research.log 2>&1 || true &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/activity_stream.py > logs/activity_stream.log 2>&1 &
# boot optimized (sleep 3 removed)
/home/shashank/xoyo/venv/bin/python services/subagent_supervisor.py > logs/subagent_supervisor.log 2>&1 &
# boot optimized (sleep 3 removed)
# /home/shashank/xoyo/venv/bin/python xoyo_daemon.py > logs/xoyo_daemon.log 2>&1 &
# boot optimized (sleep 3 removed)

echo ""
echo "✅ XOYO Omega v3.0 (Smart Mode) — Optimized services launched!"
echo "🌐 Dashboard: http://localhost:9000"
echo "🎤 Core APIs active, heavy ML disabled for 8GB RAM."
echo "🧠 Metacognitive watchdogs active."
echo "📂 Check 'logs/' for any service issues."
echo "🛑 Stop: ./stop_xoyo.sh"
