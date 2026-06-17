from fastapi import FastAPI
from pydantic import BaseModel
import asyncio, sys, os, tempfile, subprocess, json

app = FastAPI()

# Add orchestrator to path to import call_llm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.llm_router import call_llm

class ERARequest(BaseModel):
    task: str
    max_iterations: int = 5

def _execute_code(code: str) -> tuple[bool, str]:
    """Execute Python code in a temporary file and return (success, output)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        tmp_path = f.name
    
    try:
        # Run code with a strict timeout
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout: Code took longer than 10 seconds to execute."
    except Exception as e:
        return False, f"System Error: {e}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def _extract_code(llm_output: str) -> str:
    """Extract Python code from markdown blocks."""
    if "```python" in llm_output:
        parts = llm_output.split("```python")
        if len(parts) > 1:
            return parts[1].split("```")[0].strip()
    elif "```" in llm_output:
        parts = llm_output.split("```")
        if len(parts) > 1:
            return parts[1].strip()
    return llm_output.strip()

@app.post("/era_loop")
async def era_loop(req: ERARequest):
    """Run the Empirical Research Assistance self-correcting loop."""
    iteration = 1
    
    # Prompt the LLM to write the initial code
    prompt = f"""
You are the Empirical Research Assistant (ERA).
Your goal is to write a standalone Python script to solve the following task.
The script MUST print the final result to stdout. 
Task: {req.task}
Return ONLY valid Python code inside a ```python block.
"""
    history = [{"role": "user", "content": prompt}]
    
    while iteration <= req.max_iterations:
        print(f"[ERA] Iteration {iteration}/{req.max_iterations}...")
        
        # 1. Generate Code
        try:
            llm_response = await asyncio.to_thread(call_llm, history, 1000, 0.7, "reasoning")
        except Exception as e:
            return {"status": "error", "message": f"LLM Call Failed: {e}"}
            
        history.append({"role": "assistant", "content": llm_response})
        
        code = _extract_code(llm_response)
        if not code:
            return {"status": "failed", "message": "Failed to extract code from LLM output."}
            
        # 2. Execute Code
        print(f"[ERA] Testing Code...")
        success, output = _execute_code(code)
        
        if success:
            print(f"[ERA] Success! Output: {output}")
            return {
                "status": "success",
                "iterations": iteration,
                "final_code": code,
                "output": output
            }
            
        # 3. Handle Failure and Feedback
        print(f"[ERA] Code Failed: {output[:200]}...")
        feedback = f"The code failed to execute or produced an error. Fix the code based on this output/traceback:\n\n{output}\n\nReturn the fully fixed code inside a ```python block."
        history.append({"role": "user", "content": feedback})
        
        iteration += 1
        
    return {
        "status": "max_iterations_reached",
        "message": f"Failed after {req.max_iterations} iterations.",
        "last_code": code,
        "last_error": output
    }

@app.get("/health")
def health():
    return {"status": "ok", "engine": "ERA V6", "autonomous": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8061)
