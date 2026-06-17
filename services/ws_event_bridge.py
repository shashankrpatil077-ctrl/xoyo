#!/usr/bin/env python3
"""
XOYO WebSocket Event Bridge — Real-time agent process streaming.
Subscribes to Redis pub/sub channels and broadcasts to browser WebSocket clients.
Port: 8055

Architecture:
  Redis Pub/Sub → Background Thread → asyncio Queue → WebSocket broadcast → Browser

Channels:
  xoyo:events  — tool starts, completions, phase transitions
  xoyo:alerts  — errors, warnings, circuit breaker trips
  xoyo:memory  — memory consolidation events
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio, json, threading, time, logging, html
from typing import List, Dict
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xoyo.ws_bridge")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CHANNELS = ["xoyo:events", "xoyo:alerts", "xoyo:memory"]

# ── Connection Manager ────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self.queues: Dict[WebSocket, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.append(ws)
            self.queues[ws] = asyncio.Queue(maxsize=5000)
        log.info(f"WebSocket client connected. Total: {len(self.active)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)
            self.queues.pop(ws, None)
        log.info(f"WebSocket client disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: str):
        async with self._lock:
            clients = list(self.active)
        for ws in clients:
            q = self.queues.get(ws)
            if q:
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    log.warning("Client queue full, disconnecting slow consumer")
                    asyncio.create_task(ws.close())
                    asyncio.create_task(self.disconnect(ws))

manager = ConnectionManager()

# ── Stats ─────────────────────────────────────────────────────
_stats: Dict[str, int] = defaultdict(int)
_total_broadcast = 0

# ── Async Event Queue ─────────────────────────────────────────
_event_queue: asyncio.Queue = None
_main_loop = None

def _get_queue():
    global _event_queue
    if _event_queue is None:
        _event_queue = asyncio.Queue(maxsize=10000)
    return _event_queue

# ── Async Redis Subscriber Task ────────────────────────────────
_redis_task_started = False

async def _start_redis_listener():
    """Background task: subscribe to Redis asynchronously and push events into asyncio queue."""
    global _redis_task_started
    if _redis_task_started:
        return
    _redis_task_started = True

    import redis.asyncio as redis_async
    while True:
        rc = None
        pubsub = None
        try:
            rc = redis_async.Redis(host='127.0.0.1', port=6379, decode_responses=True)
            await rc.ping()
            pubsub = rc.pubsub()
            await pubsub.subscribe(*CHANNELS)
            log.info(f"Async Redis pub/sub connected. Subscribed to: {CHANNELS}")
            
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                
                try:
                    parsed_data = await asyncio.to_thread(json.loads, message["data"])
                except Exception:
                    parsed_data = message["data"]
                    
                event_json = json.dumps({
                    "channel": message["channel"],
                    "data": parsed_data,
                    "ts": time.time()
                })
                _stats[message["channel"]] += 1
                q = _get_queue()
                try:
                    q.put_nowait(event_json)
                except asyncio.QueueFull:
                    log.warning("Internal event queue full, dropping message")
        except Exception as e:
            log.warning(f"Async Redis listener error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        finally:
            if pubsub:
                try: await pubsub.close()
                except Exception: pass
            if rc:
                try: await rc.aclose()
                except Exception: pass

# ── Broadcast Loop (runs in asyncio event loop) ──────────────
async def _broadcast_loop():
    """Continuously dequeue events and broadcast to all WebSocket clients."""
    global _total_broadcast
    q = _get_queue()
    while True:
        try:
            event_json = await asyncio.wait_for(q.get(), timeout=30.0)
            await manager.broadcast(event_json)
            _total_broadcast += 1
        except asyncio.TimeoutError:
            # Send heartbeat ping to keep connections alive
            if manager.active:
                heartbeat = json.dumps({"channel": "heartbeat", "data": "ping", "ts": time.time()})
                await manager.broadcast(heartbeat)
        except Exception as e:
            log.error(f"Broadcast error: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup():
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    asyncio.create_task(_start_redis_listener())
    asyncio.create_task(_broadcast_loop())
    log.info("WebSocket Event Bridge started on port 8055")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    q = manager.queues.get(ws)
    
    async def _sender():
        try:
            while True:
                msg = await q.get()
                await ws.send_text(msg)
        except Exception:
            pass

    sender_task = asyncio.create_task(_sender())

    try:
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                if data == "ping":
                    try:
                        q.put_nowait(json.dumps({"channel": "pong", "ts": time.time()}))
                    except asyncio.QueueFull:
                        pass
            except asyncio.TimeoutError:
                try:
                    q.put_nowait(json.dumps({"channel": "heartbeat", "ts": time.time()}))
                except asyncio.QueueFull:
                    log.warning("Client queue full, dropping message")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sender_task.cancel()
        await manager.disconnect(ws)

# ── REST Endpoints ────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ws_event_bridge",
        "port": 8055,
        "clients": len(manager.active),
        "channels": CHANNELS,
        "total_broadcast": _total_broadcast,
    }

@app.get("/stats")
async def stats():
    return {
        "messages_per_channel": dict(_stats),
        "total_broadcast": _total_broadcast,
        "active_clients": len(manager.active),
        "uptime_info": "Use /health for service status",
    }

# ── Manual event injection (for testing) ──────────────────────
from pydantic import BaseModel

class ManualEvent(BaseModel):
    channel: str = "xoyo:events"
    data: str = '{"type":"test","message":"hello"}'

@app.post("/inject")
async def inject_event(event: ManualEvent):
    """Manually inject an event for testing WebSocket broadcasting."""
    try:
        parsed_data = json.loads(event.data)
    except Exception:
        parsed_data = event.data

    payload = json.dumps({
        "channel": event.channel,
        "data": parsed_data,
        "ts": time.time()
    })
    await manager.broadcast(payload)
    return {"status": "injected", "clients_reached": len(manager.active)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8055)
