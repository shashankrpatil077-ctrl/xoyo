import time
import subprocess
import requests
import logging
import threading

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("xoyo.precacher")

class LightweightPreCacher:
    def __init__(self):
        self.last_title = ""
        self.running = False
        self.cache = {}

    def get_active_window_title(self):
        try:
            # Requires xdotool
            result = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], 
                                    capture_output=True, text=True, timeout=1)
            return result.stdout.strip()
        except Exception:
            return ""

    def pre_fetch_solution(self, error_text: str):
        if error_text in self.cache:
            return
        log.info(f"Pre-caching solution for detected error: {error_text}")
        
        # Simulate background LLM request to XOYO proxy
        # Since this is a lightweight loop, we don't await, we let the thread handle it.
        try:
            # We send a non-blocking background request to the main Orchestrator
            # so the answer is ready in XOYO's memory bank if the user asks.
            payload = {
                "model": "qwen",
                "messages": [{"role": "user", "content": f"Briefly explain how to fix this error: {error_text}"}],
                "max_tokens": 150
            }
            res = requests.post("http://127.0.0.1:9000/v1/chat/completions", json=payload, timeout=10)
            if res.status_code == 200:
                answer = res.json()["choices"][0]["message"]["content"]
                self.cache[error_text] = answer
                log.info("Pre-cache complete. Ready for user.")
        except Exception as e:
            log.debug(f"Pre-cache failed: {e}")

    def watch_loop(self):
        self.running = True
        while self.running:
            title = self.get_active_window_title()
            if title and title != self.last_title:
                self.last_title = title
                # Lightweight heuristic: Only trigger if title contains error keywords
                title_lower = title.lower()
                if any(kw in title_lower for kw in ["error", "exception", "traceback", "failed"]):
                    # Spawn a thread to fetch so we don't block the watcher
                    threading.Thread(target=self.pre_fetch_solution, args=(title,), daemon=True).start()
            
            # Sleep 2 seconds to ensure 0% CPU footprint
            time.sleep(2)

if __name__ == "__main__":
    watcher = LightweightPreCacher()
    log.info("Starting Ultra-Lightweight Predictive Pre-Cacher (8GB RAM Safe)")
    watcher.watch_loop()
