from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel
import subprocess, os, sys

app = FastAPI()

API_KEY = os.getenv("MYTHOS_API_KEY", "mythos-default-secret-key")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/home/shashank/xoyo")

def verify_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

def verify_path(path: str):
    # Resolve any symlinks and relative paths to get the true absolute path
    abs_path = os.path.realpath(path)
    workspace_abs = os.path.realpath(WORKSPACE_DIR)
    # Ensure the resolved path is still within the resolved workspace directory
    if os.path.commonpath([abs_path, workspace_abs]) != workspace_abs:
        raise HTTPException(status_code=403, detail="Path outside workspace sandbox")
    return abs_path

class TerminalCommand(BaseModel):
    command: str
    timeout: int = 600

class FileRead(BaseModel):
    path: str

class FileWrite(BaseModel):
    path: str
    content: str

@app.post("/mythos/terminal", dependencies=[Depends(verify_key)])
async def terminal(req: TerminalCommand):
    """Execute raw bash command with no truncation, no limits."""
    try:
        r = subprocess.run(req.command, shell=True, capture_output=True, text=True, timeout=req.timeout)
        return {
            "status": "success",
            "exit_code": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/mythos/python", dependencies=[Depends(verify_key)])
async def run_python(req: TerminalCommand):
    """Execute python script completely unrestricted."""
    try:
        r = subprocess.run([sys.executable, "-c", req.command], capture_output=True, text=True, timeout=req.timeout)
        return {
            "status": "success",
            "exit_code": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/mythos/read", dependencies=[Depends(verify_key)])
async def read_file(req: FileRead):
    try:
        safe_path = verify_path(req.path)
        with open(safe_path, "r") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except HTTPException as e:
        raise e
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/mythos/write", dependencies=[Depends(verify_key)])
async def write_file(req: FileWrite):
    try:
        safe_path = verify_path(req.path)
        # Create directories if they don't exist
        parent = os.path.dirname(safe_path)
        if parent: os.makedirs(parent, exist_ok=True)
        
        with open(safe_path, "w") as f:
            f.write(req.content)
        return {"status": "success"}
    except HTTPException as e:
        raise e
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
def health():
    return {"status": "ok", "engine": "Mythos-Class OS Controller"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8062)
