#!/usr/bin/env python3
"""
XOYO System Monitor — real-time hardware vitals.
Reports CPU temp, RAM, disk, CPU% to orchestrator and dashboard.
Port: 8044
"""
from fastapi import FastAPI
import psutil, time, subprocess, os, re

app = FastAPI()

def get_cpu_temperature() -> float:
    """Read CPU temperature via psutil sensors or fallback to lm-sensors."""
    try:
        temps = psutil.sensors_temperatures()
        for name in ["coretemp", "cpu_thermal", "k10temp", "acpitz"]:
            if name in temps and temps[name]:
                return round(temps[name][0].current, 1)
    except Exception:
        pass
    try:
        out = subprocess.check_output(["sensors"], text=True, timeout=3)
        matches = re.findall(r'Core\s+\d+:\s+\+(\d+\.\d+)°C', out)
        if matches:
            return round(sum(float(m) for m in matches) / len(matches), 1)
    except Exception:
        pass
    return -1.0

@app.get("/vitals")
def get_vitals():
    """Full system vitals snapshot."""
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.expanduser("~"))
    cpu_temp = get_cpu_temperature()

    alerts = []
    throttle = False
    if cpu_temp > 85:
        alerts.append(f"CPU temperature critical: {cpu_temp}°C")
        throttle = True
    if ram.percent > 90:
        alerts.append(f"RAM critically low: {ram.percent:.0f}% used")
        throttle = True
    if cpu_percent > 95:
        alerts.append(f"CPU overloaded: {cpu_percent:.0f}%")
        throttle = True
    if disk.percent > 95:
        alerts.append("Disk almost full")

    if throttle:
        try:
            import redis, json
            rc = redis.Redis(host='127.0.0.1', port=6379, db=0)
            rc.publish("xoyo:events", json.dumps({"type": "system_throttle", "pause": True}))
        except:
            pass

    return {
        "cpu_percent":    cpu_percent,
        "cpu_temp_c":     cpu_temp,
        "ram_used_gb":    round(ram.used / 1e9, 2),
        "ram_total_gb":   round(ram.total / 1e9, 2),
        "ram_percent":    ram.percent,
        "disk_free_gb":   round(disk.free / 1e9, 1),
        "disk_percent":   disk.percent,
        "alerts":         alerts,
        "status":         "critical" if alerts else "healthy",
        "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%S")
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "system_monitor", "port": 8044}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8044)
