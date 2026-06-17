import asyncio, uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import redis

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
except Exception:
    r = None

@app.get("/events")
async def stream_events():
    async def event_generator():
        if not r:
            yield "data: {\"type\": \"status\", \"content\": \"Redis offline\"}\n\n"
            return
        pubsub = r.pubsub()
        pubsub.subscribe("xoyo:activity")
        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True)
                if message and message.get("data"):
                    yield f"data: {message['data']}\n\n"
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pubsub.unsubscribe()
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/health")
def health():
    return {"status": "ok", "service": "activity_stream", "port": 8053}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8053)
