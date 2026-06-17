#!/usr/bin/env python3
"""XOYO Watchdog Daemon v2 — LITE-Mode Aware

Monitors running services and restarts them if they crash.
RESPECTS the LITE_MODE flag: does NOT launch heavy ML/perception services on 8GB systems.
Does NOT auto-send propose_code_rewrite — logs crashes for manual review instead.
"""
import subprocess
import time
import sys
import os
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.daemon")

PYTHON = sys.executable
os.makedirs("logs", exist_ok=True)

# ─── LITE MODE CONFIG ───────────────────────────────────────
# When True, heavy ML and perception services are NOT launched.
# This saves ~2GB RAM on systems with ≤8GB.
LITE_MODE = True

# ─── SERVICE REGISTRY ───────────────────────────────────────
# (name, command, requires_heavy)
# requires_heavy=True means the service is SKIPPED in LITE_MODE
SERVICES = [
    # Core Infrastructure (always on)
    ("Mythos OS",         f"{PYTHON} services/mythos_os.py",         False),
    ("Orchestrator",      f"{PYTHON} orchestrator/main.py",          False),
    ("Workers",           f"{PYTHON} services/workers_massive.py",   False),

    # Scientific & Reasoning (lightweight, always on)
    ("Active Inference",  f"{PYTHON} services/active_inference.py",  False),
    ("Advanced Idle",     f"{PYTHON} services/advanced_idle.py",     False),
    ("Bayesian Surprise", f"{PYTHON} services/bayesian_surprise.py", False),
    ("Debate",            f"{PYTHON} services/debate_service.py",    False),
    ("Dreamer",           f"{PYTHON} services/dreamer_server.py",    False),
    ("DGM",              f"{PYTHON} services/hyperagents_dgm.py",    False),
    ("Materials",         f"{PYTHON} services/materials_discovery.py",False),
    ("Math Solvers",      f"{PYTHON} services/math_services.py",     False),
    ("NNGPT",             f"{PYTHON} services/nngpt_service.py",     False),
    ("Physics",           f"{PYTHON} services/physics_server.py",    False),
    ("ERA Engine",        f"{PYTHON} services/era_engine.py",        False),

    # Memory, Safety & Routing (always on)
    ("Memory Manager",    f"{PYTHON} services/memory_manager.py",    False),
    ("Constitutional AI", f"{PYTHON} services/constitutional_ai.py", False),
    ("Intent BNN",        f"{PYTHON} services/intent_bnn.py",        False),
    ("Flow Policy",       f"{PYTHON} services/flow_policy.py",       False),
    ("Priority Engine",   f"{PYTHON} services/priority_engine.py",   False),
    ("Diag2Diag",         f"{PYTHON} services/diag2diag.py",         False),

    # Watchdogs (always on)
    ("Stuck Detector",    f"{PYTHON} services/stuck_detector.py",    False),
    ("Agent Trace",       f"{PYTHON} services/agent_trace.py",       False),
    ("Progress Vocalizer",f"{PYTHON} services/progress_vocalizer.py",False),

    # Tools & Generators (always on)
    ("Desktop Control",   f"{PYTHON} services/desktop_control.py",   False),
    ("Presentation Gen",  f"{PYTHON} services/pptx_generator.py",    False),
    ("Scene Generator",   f"{PYTHON} services/scene_generator.py",   False),

    # ─── HEAVY SERVICES (LITE_MODE=True → SKIPPED) ─────────
    ("Memory Advanced",   f"{PYTHON} services/memory_advanced.py",   True),
    ("Camera",            f"{PYTHON} services/camera_server.py",     True),
    ("YOLO",              f"{PYTHON} services/yolo_server.py",       True),
    ("Vision Router",     f"{PYTHON} services/vision_server.py",     True),
    ("Wakeword",          f"{PYTHON} services/wakeword_server.py",   True),
    ("Affective Loop",    f"{PYTHON} services/affective_loop.py",    True),
    ("Prosody",           f"{PYTHON} services/prosody_server.py",    True),
    ("Neural TTS",        f"{PYTHON} services/neural_tts.py",        True),
    ("Whisper STT",       f"{PYTHON} services/whisper_server.py",    True),
]

processes = {}
MAX_RESTARTS = 3  # Max restarts per service before giving up
restart_counts = {}

def start_service(name, cmd):
    """Start a service and track its process."""
    try:
        err_log = open(f"logs/{name.replace(' ', '_')}.err", "a")
        p = subprocess.Popen(cmd.split(), stdout=subprocess.DEVNULL, stderr=err_log)
        processes[name] = {"process": p, "cmd": cmd, "err_log": err_log}
        log.info(f"[+] Started {name} (PID: {p.pid})")
    except Exception as e:
        log.error(f"[-] Failed to start {name}: {e}")

def monitor_loop():
    """Monitor running services. Restart crashed ones up to MAX_RESTARTS."""
    log.info("🚀 XOYO Daemon v2 — Monitoring services (LITE_MODE=%s)...", LITE_MODE)
    while True:
        for name, data in list(processes.items()):
            p = data["process"]
            if p.poll() is not None:
                count = restart_counts.get(name, 0)
                if count >= MAX_RESTARTS:
                    log.error(f"[X] {name} crashed {count} times — giving up. Manual intervention needed.")
                    del processes[name]
                    continue

                log.warning(f"[!] {name} crashed (Exit: {p.returncode}, restart {count+1}/{MAX_RESTARTS})")
                restart_counts[name] = count + 1

                # Close old log handle
                try:
                    data["err_log"].close()
                except Exception:
                    pass

                # Log the crash for manual review (NO auto-rewrite)
                try:
                    with open(f"logs/{name.replace(' ', '_')}.err", "r") as f:
                        traceback = f.seek(0, 2); f.seek(max(f.tell() - 2000, 0), 0); traceback = f.read()
                    if "Traceback" in traceback or "Error" in traceback:
                        log.error(f"[CRASH] {name}:\n{traceback[-500:]}")
                except Exception:
                    pass

                start_service(name, data["cmd"])
        time.sleep(10)


if __name__ == "__main__":
    log.info("XOYO Daemon v2 starting (LITE_MODE=%s)...", LITE_MODE)

    # Start Redis (handled by start_xoyo.sh)
    # os.system("sudo systemctl start redis-server 2>/dev/null || true")
    time.sleep(1)

    # Launch services respecting LITE_MODE
    for name, cmd, requires_heavy in SERVICES:
        if requires_heavy and LITE_MODE:
            log.info(f"[SKIP] {name} — disabled in LITE_MODE")
            continue
        # Check if the service file actually exists
        parts = cmd.split()
        script_path = parts[-1] if len(parts) >= 2 else ""
        if script_path and not os.path.isfile(script_path):
            log.warning(f"[SKIP] {name} — file not found: {script_path}")
            continue
        start_service(name, cmd)
        time.sleep(0.01)  # Stagger startups to avoid RAM spike

    try:
        monitor_loop()
    except KeyboardInterrupt:
        log.info("Shutting down all services...")
        for name, data in processes.items():
            data["process"].terminate()
        sys.exit(0)
