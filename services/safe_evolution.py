import os
import ast
import py_compile
import shutil
import importlib.util
import traceback
import sys
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.evolution")

def verify_syntax(filepath: str) -> bool:
    """Verifies that the file is syntactically valid Python."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        py_compile.compile(filepath, doraise=True)
        return True
    except Exception as e:
        log.error(f"Syntax validation failed for {filepath}: {e}")
        return False

def verify_runtime_load(filepath: str, module_name: str) -> tuple[bool, str]:
    """Attempts to safely load the module to catch missing imports or top-level runtime crashes."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None:
            return False, "Failed to create spec."
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return True, "Success"
    except Exception as e:
        tb = traceback.format_exc()
        log.error(f"Runtime load failed for {filepath}:\n{tb}")
        return False, tb

def safe_evolve(target_file: str, new_content: str) -> dict:
    """
    Safely applies a self-evolution patch.
    1. Writes to temporary sandbox file.
    2. Runs AST parsing and compilation.
    3. Runs module import test.
    4. Overwrites original ONLY if 100% successful.
    """
    sandbox_file = target_file + ".sandbox.tmp"
    
    try:
        with open(sandbox_file, 'w') as f:
            f.write(new_content)
        
        # Step 1: Syntax
        if not verify_syntax(sandbox_file):
            return {"success": False, "error": "Syntax Error detected. Patch rejected."}
            
        # Step 2: Runtime Import Test
        module_name = os.path.basename(target_file).replace('.py', '_sandbox')
        ok, error = verify_runtime_load(sandbox_file, module_name)
        if not ok:
            return {"success": False, "error": f"Runtime Error during import:\n{error}"}
            
        # Step 3: Atomic Replace (100% Safe)
        backup_file = target_file + ".bak"
        if os.path.exists(target_file):
            shutil.copy2(target_file, backup_file)
            
        shutil.move(sandbox_file, target_file)
        log.info(f"Successfully evolved {target_file}")
        return {"success": True, "message": "Code evolved and verified safely."}
        
    except Exception as e:
        return {"success": False, "error": f"Evolution framework error: {e}"}
    finally:
        if os.path.exists(sandbox_file):
            os.remove(sandbox_file)

if __name__ == "__main__":
    # Internal test
    test_content = "def add(a, b): return a + b\n"
    res = safe_evolve("test_math.py", test_content)
    print(res)
    if os.path.exists("test_math.py"): os.remove("test_math.py")
