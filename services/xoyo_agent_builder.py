import os
import re
import uuid
import json
import requests
import ast
import tempfile
import subprocess
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="XOYO Self-Healing Agent Builder")

class BuildRequest(BaseModel):
    request: str

def call_groq(prompt: str, error_context: str = "") -> dict:
    from dotenv import load_dotenv
    load_dotenv("/home/shashank/xoyo/.env")
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in .env")
        
    system_prompt = (
        "You are an Antigravity-tier Python Developer. Generate a robust, standalone Python function.\n"
        "Rules:\n"
        "1. MUST include all necessary imports INSIDE the function body.\n"
        "2. MUST return a plain text string. Do NOT return JSON.\n"
        "3. Catch exceptions and return a descriptive string starting with 'Error: '.\n"
        "4. DO NOT use destructive OS commands like rm -rf.\n"
        "5. Output YOUR ENTIRE RESPONSE as a valid JSON object with exactly three string fields: \"function_name\", \"function_code\", and \"description\".\n"
    )
    
    user_prompt = prompt
    if error_context:
        user_prompt += f"\n\nYOUR PREVIOUS ATTEMPT FAILED WITH THIS ERROR:\n{error_context}\nFIX THE SYNTAX AND LOGIC ERRORS."
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    
    return json.loads(content.strip())


def sandbox_test_code(code: str) -> str:
    """Executes a syntax and dry-run test of the code. Returns empty string if passed, else traceback."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(code)
        temp_path = f.name
        
    try:
        # Step 1: Strict syntax and AST check
        import ast
        ast.parse(code)
        compile(code, "<string>", "exec")
        
        # Step 2: Py_compile syntax check
        result = subprocess.run([sys.executable, "-m", "py_compile", temp_path], capture_output=True, text=True)
        if result.returncode != 0:
            return result.stderr
            
        return "" # Passed!
    except Exception as e:
        return str(e)
    finally:
        os.unlink(temp_path)

@app.post("/build_tool")
async def build_tool(req: BuildRequest):
    try:
        error_context = ""
        data = {}
        # Iterative Self-Healing Loop (Max 3 Tries)
        for attempt in range(3):
            data = call_groq(req.request, error_context)
            
            func_name = data["function_name"]
            func_code = data["function_code"]
            desc = data["description"]
            
            # Run the testing sandbox
            test_error = sandbox_test_code(func_code)
            if not test_error:
                break # Passed!
            
            # Failed, loop back
            error_context = test_error
            if attempt == 2:
                raise ValueError(f"Failed to generate working code after 3 attempts. Last error: {test_error}")

        # Inject safely into agent_tools.py using AST-aware logic
        tools_path = os.path.join(os.path.dirname(__file__), "agent_tools.py")
        with open(tools_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if f"def {func_name}(" in content:
            new_func_name = f"{func_name}_{uuid.uuid4().hex[:4]}"
            import re as _re
            func_code = _re.sub(rf"^def {_re.escape(func_name)}\s*\(", f"def {new_func_name}(", func_code, count=1, flags=re.MULTILINE)
            func_name = new_func_name
            
        # Robust AST insertion

        # Robust AST insertion
        match = re.search(r'TOOLS_REGISTRY\s*=\s*\{', content)
        if not match:
            raise ValueError("TOOLS_REGISTRY block not found in agent_tools.py")
        
        split_idx = match.end()
        part1 = content[:match.start()]
        part2 = content[split_idx:]
            
        new_code_section = f"\n{func_code}\n\n"
        new_registry_entry = f'\n    "{func_name}": {func_name},'
        
        numbers = re.findall(r'^(\d+)\.', part2, re.MULTILINE)
        next_num = int(numbers[-1]) + 1 if numbers else 1
        new_schema_entry = f"{next_num}. `{func_name}(...)` - {desc}\n"
        
        part2_updated = part2.replace(
            "To use a tool, output a JSON block",
            f"{new_schema_entry}\nTo use a tool, output a JSON block"
        )
        part2_updated = part2_updated.replace(
            "TOOLS_REGISTRY = {",
            "TOOLS_REGISTRY = {" + new_registry_entry
        )
        
        final_content = part1 + new_code_section + part2_updated
        
        # Verify final file is valid syntax before saving
        import ast
        ast.parse(final_content)
        compile(final_content, "<string>", "exec")
        
        with open(tools_path, "w", encoding="utf-8") as f:
            f.write(final_content)
            
        return {
            "status": "success", 
            "message": f"Tool '{func_name}' successfully built, tested, and registered.", 
            "code": func_code,
            "attempts": attempt + 1
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8116)
