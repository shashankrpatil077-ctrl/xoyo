import json
from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from celery import Celery
import uvicorn

app = FastAPI()
celery_app = Celery("tasks", broker="redis://127.0.0.1:6379", backend="redis://127.0.0.1:6379")
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True
)

@celery_app.task
def echo(payload):
    return payload

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/submit")
async def submit(request: Request):
    payload = await request.json()
    task = await run_in_threadpool(echo.delay, payload)
    return {"task_id": task.id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8050)
