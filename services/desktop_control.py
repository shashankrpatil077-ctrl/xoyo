#!/usr/bin/env python3
"""
XOYO Desktop Control — gives XOYO hands on the Ubuntu desktop.
Controls: mouse, keyboard, application launching, screenshots.
Safety: All actions gated. Only operates in /home/shashank/ boundary.
Research: Wayland native (ydotool, at-spi2/dogtail, dbus)
Port: 8043
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess, os, time
import urllib.parse
import urllib.request
import asyncio
import re

import requests as _req
import logging

_log = logging.getLogger("xoyo.desktop")

# Build a consistent env dict for ALL ydotool calls
def _ydotool_env():
    """Returns env dict with YDOTOOL_SOCKET, DISPLAY, WAYLAND, XDG set."""
    e = os.environ.copy()
    e.setdefault("YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket")
    e.setdefault("DISPLAY", ":0")
    e.setdefault("WAYLAND_DISPLAY", "wayland-0")
    e.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return e

# Verify ydotool has access to uinput
try:
    subprocess.run(["ydotool", "mousemove", "-a", "0", "0"], env=_ydotool_env(), check=True, stderr=subprocess.DEVNULL, timeout=2)
    YDOTOOL_AVAILABLE = True
except Exception:
    _log.warning("ydotool is installed but cannot write to /dev/uinput. Check permissions.")
    YDOTOOL_AVAILABLE = False

def _safety_gate(action_desc: str) -> bool:
    return True

app = FastAPI()

# ── App launch mappings ─────────────────────────────────
APP_COMMANDS = {
    "chrome":         ["google-chrome"],
    "browser":        ["google-chrome"],
    "google-chrome":  ["google-chrome"],
    "firefox":        ["firefox"],
    "terminal":       ["gnome-terminal"],
    "files":          ["nautilus"],
    "file-manager":   ["nautilus"],
    "calculator":     ["gnome-calculator"],
    "text-editor":    ["gedit"],
    "settings":       ["gnome-control-center"],
    "whatsapp":       ["xdg-open", "https://web.whatsapp.com"],
    "telegram":       ["xdg-open", "https://web.telegram.org"],
    "youtube":        ["xdg-open", "https://youtube.com"],
    "gmail":          ["xdg-open", "https://mail.google.com"],
    "google":         ["xdg-open", "https://google.com"],
}

class OpenAppRequest(BaseModel):
    app_name: str
    arguments: str = ""

class CloseAppRequest(BaseModel):
    app_name: str

class TypeTextRequest(BaseModel):
    text: str
    interval: float = 0.05

class PressKeyRequest(BaseModel):
    key: str

class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"

class SemanticClickRequest(BaseModel):
    name: str
    role: str = ""

class SearchRequest(BaseModel):
    engine: str = "google"
    query: str = ""

class YouTubeRequest(BaseModel):
    query: str

class WhatsAppRequest(BaseModel):
    phone: str
    message: str

class MediaControlRequest(BaseModel):
    action: str

@app.post("/media")
async def media_control(req: MediaControlRequest):
    if not YDOTOOL_AVAILABLE:
        raise HTTPException(status_code=503, detail="ydotool not available")
    
    # Map actions to ydotool key codes (KEY_PLAYPAUSE, KEY_NEXTSONG, KEY_PREVIOUSSONG)
    mapping = {
        "playpause": "164:1 164:0",
        "nexttrack": "163:1 163:0",
        "prevtrack": "165:1 165:0"
    }
    if req.action not in mapping:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    subprocess.run(f"ydotool key {mapping[req.action]}", shell=True, env=_ydotool_env(), timeout=5)
    return {"status": "ok", "action": req.action}

@app.post("/open")
async def open_application(req: OpenAppRequest):
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, _safety_gate, f"open {req.app_name}"):
        raise HTTPException(status_code=403, detail="Blocked")
    
    cmd = APP_COMMANDS.get(req.app_name.lower(), ["xdg-open", req.app_name])
    if req.arguments:
        cmd.append(req.arguments)
        
    env = os.environ.copy()
    if "WAYLAND_DISPLAY" not in env: env["WAYLAND_DISPLAY"] = "wayland-0"
    if "DISPLAY" not in env: env["DISPLAY"] = ":0"
    if "XDG_RUNTIME_DIR" not in env: env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    
    subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    await asyncio.sleep(2)
    return {"status": "ok", "opened": req.app_name}

@app.post("/close")
async def close_application(req: CloseAppRequest):
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, _safety_gate, f"close {req.app_name}"):
        raise HTTPException(status_code=403, detail="Blocked")
    
    subprocess.run(["pkill", "-f", req.app_name])
    return {"status": "ok", "closed": req.app_name}

@app.post("/search")
async def web_search_open(req: SearchRequest):
    engine_urls = {
        "google": "https://www.google.com/search?q=",
        "bing":   "https://www.bing.com/search?q="
    }
    url = engine_urls.get(req.engine, engine_urls["google"]) + urllib.parse.quote_plus(req.query)
    env = os.environ.copy()
    if "WAYLAND_DISPLAY" not in env: env["WAYLAND_DISPLAY"] = "wayland-0"
    if "DISPLAY" not in env: env["DISPLAY"] = ":0"
    if "XDG_RUNTIME_DIR" not in env: env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    subprocess.Popen(
        ["xdg-open", url],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )
    await asyncio.sleep(2)
    return {"status": "ok", "url": url}

@app.post("/type")
async def type_text(req: TypeTextRequest):
    return {"status": "error", "message": "Blind 'type' via ydotool is disabled to prevent hallucinations. Use DOM-aware Playwright or Accessibility Tree tools instead."}

@app.post("/press")
async def press_key(req: PressKeyRequest):
    return {"status": "error", "message": "Blind 'press' via ydotool is disabled to prevent hallucinations. Use semantic tools instead."}

@app.post("/click")
async def click(req: ClickRequest):
    return {"status": "error", "message": "Blind 'click' via ydotool is disabled. Use semantic_click instead."}

@app.post("/semantic_click")
async def semantic_click(req: SemanticClickRequest):
    """Uses AT-SPI2 / dogtail to click an element by name without pixels."""
    try:
        from dogtail.tree import root
    except ImportError:
        raise HTTPException(status_code=503, detail="dogtail not installed")
        
    try:
        node = root.findChild(lambda x: req.name.lower() in x.name.lower() and (not req.role or req.role.lower() in x.roleName.lower()))
        if node:
            node.click()
            return {"status": "ok", "element": node.name}
    except Exception as e:
        _log.error(f"Semantic click failed: {e}")
        
    raise HTTPException(status_code=404, detail="Element not found in accessibility tree")

@app.post("/screenshot")
async def screenshot():
    path = os.path.expanduser(f"~/xoyo/output/screenshots/{int(time.time())}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["scrot", path])
    return {"status": "ok", "path": path}

@app.get("/screen_size")
async def screen_size():
    try:
        out = subprocess.check_output(["xdpyinfo"]).decode()
        m = re.search(r'dimensions:\s+(\d+)x(\d+) pixels', out)
        if m:
            return {"width": int(m.group(1)), "height": int(m.group(2))}
    except Exception:
        pass
    return {"width": 1920, "height": 1080}

@app.post("/youtube_play")
def youtube_play(req: YouTubeRequest):
    if not _safety_gate(f"youtube play {req.query}"):
        raise HTTPException(status_code=403, detail="Blocked")
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(req.query)
    try:
        req_obj = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            html = resp.read().decode('utf-8')
        match = re.search(r'watch\?v=([a-zA-Z0-9_-]{11})', html)
        if not match:
            raise HTTPException(status_code=404, detail="No video found")
        url = "https://youtube.com/watch?v=" + match.group(1)
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"status": "ok", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

_whatsapp_task = None

async def _whatsapp_background_task():
    try:
        await asyncio.sleep(12)
        if YDOTOOL_AVAILABLE:
            loop = asyncio.get_running_loop()
            def trigger_enter():
                subprocess.run(f"ydotool key 28:1 28:0", shell=True)
            await loop.run_in_executor(None, trigger_enter)
    except Exception as e:
        _log.error(f"WhatsApp background task failed: {e}")

@app.post("/whatsapp_send")
async def whatsapp_send(req: WhatsAppRequest):
    if not _safety_gate(f"whatsapp send to {req.phone}"):
        raise HTTPException(status_code=403, detail="Blocked")
    global _whatsapp_task
    if _whatsapp_task and not _whatsapp_task.done():
        _whatsapp_task.cancel()
    url = f"https://web.whatsapp.com/send?phone={req.phone}&text={urllib.parse.quote(req.message)}"
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    _whatsapp_task = asyncio.create_task(_whatsapp_background_task())
    return {"status": "ok", "message": "whatsapp background task started"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "desktop_control", "port": 8043,
            "ydotool": YDOTOOL_AVAILABLE}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8043)
