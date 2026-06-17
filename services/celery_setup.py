import subprocess, os, time

# 1. Free the port and clean old processes
os.system("fuser -k 8050/tcp 2>/dev/null; pkill -f celery 2>/dev/null; pkill -f uvicorn 2>/dev/null")
time.sleep(2)

# 2. Install dependencies
subprocess.check_call(["pip", "install", "celery", "redis"])

# 3. Write the FastAPI + Celery app
app_code = '''import json
from fastapi import FastAPI, Request
from celery import Celery
import uvicorn

app = FastAPI()
celery_app = Celery("tasks", broker="redis://localhost:6379", backend="redis://localhost:6379")

@celery_app.task
def echo(payload):
    return payload

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/submit")
async def submit(request: Request):
    payload = await request.json()
    task = echo.delay(payload)
    return {"task_id": task.id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8050)
'''

with open("/home/shashank/xoyo/services/task_queue.py", "w") as f:
    f.write(app_code)
print("✅ File written")

# 4. Start Redis
subprocess.Popen(["redis-server", "--daemonize", "yes"])
time.sleep(2)
print("✅ Redis started")

# 5. Start Celery worker
subprocess.Popen(["celery", "-A", "task_queue.celery_app", "worker", "--loglevel=info"],
                 cwd="/home/shashank/xoyo/services")
time.sleep(2)
print("✅ Celery worker started")

# 6. Start FastAPI server
subprocess.Popen(["python3", "/home/shashank/xoyo/services/task_queue.py"])
time.sleep(4)
print("✅ FastAPI server started on port 8050")
