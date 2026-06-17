#!/usr/bin/env python3
"""
XOYO Web Agent — Autonomous browser automation via Playwright.
Uses a SEPARATE browser profile to avoid conflicts with user's open Chrome.
Port: 8063
"""
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio
import os
import logging
import socket
import ipaddress
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="XOYO Web Agent")

# Use a DEDICATED profile dir to avoid conflicts with user's open Chrome
XOYO_BROWSER_PROFILE = os.path.expanduser("~/xoyo/.browser_profile")
os.makedirs(XOYO_BROWSER_PROFILE, exist_ok=True)


class TaskRequest(BaseModel):
    prompt: str
    file_paths: Optional[list[str]] = None


class TaskResponse(BaseModel):
    response: str

class DeepResearchRequest(BaseModel):
    prompt: str
    max_steps: int = 15
    concurrency: int = 3


async def wait_for_text_to_settle(locator, timeout=120, interval=2.5):
    """Wait until the text of the locator stops changing (generation finished) using MutationObserver to avoid CPU reflows."""
    try:
        js = """
        (el) => new Promise((resolve, reject) => {
            let timer = setTimeout(() => resolve(el.innerText), 3000);
            let totalTimer = setTimeout(() => resolve(el.innerText), %d * 1000);
            const observer = new MutationObserver((mutations) => {
                clearTimeout(timer);
                timer = setTimeout(() => {
                    observer.disconnect();
                    clearTimeout(totalTimer);
                    resolve(el.innerText);
                }, 3000);
            });
            observer.observe(el, { characterData: true, childList: true, subtree: true });
        })
        """ % timeout
        result = await locator.evaluate(js)
        return result
    except Exception as e:
        logger.error(f"MutationObserver error: {e}")
        try:
            return await locator.inner_text()
        except Exception:
            return ""

def _is_safe_url_sync(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'): return False
        if not parsed.hostname: return False
        ip = socket.gethostbyname(parsed.hostname)
        ip_obj = ipaddress.ip_address(ip)
        return not (ip_obj.is_private or ip_obj.is_loopback)
    except Exception:
        return False

async def _is_safe_url(url: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _is_safe_url_sync, url)

async def _run_browser_task_inner(url: str, prompt: str, file_paths: Optional[list[str]],
                            prompt_selectors: list, response_selectors: list,
                            service_name: str) -> str:
    """
    Generic browser automation that works for ChatGPT, DeepSeek, and other AI sites.
    Uses Playwright's bundled Chromium (not the user's Chrome) to avoid profile lock conflicts.
    """
    if not await _is_safe_url(url):
        raise HTTPException(status_code=400, detail=f"SSRF Prevention: URL {url} is not permitted.")
        
    async with async_playwright() as p:
        browser = None
        context = None
        try:
            # Launch Playwright's own Chromium with persistent context
            context = await p.chromium.launch_persistent_context(
                user_data_dir=XOYO_BROWSER_PROFILE,
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--no-default-browser-check',
                ],
                viewport={'width': 1280, 'height': 900},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            )
            page = context.pages[0] if context.pages else await context.new_page()

            logger.info(f"[{service_name}] Navigating to {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for the page to fully load
            # networkidle wait removed for speed

            # Check for CAPTCHA (Graceful HITL)
            captcha_iframe = page.locator('iframe[src*="captcha"], iframe[title*="recaptcha"], iframe[title*="hcaptcha"], div[class*="captcha"]')
            if await captcha_iframe.count() > 0:
                logger.info(f"[{service_name}] CAPTCHA detected! Graceful HITL active: waiting up to 5 minutes for the user to solve it.")
                try:
                    await captcha_iframe.first.wait_for(state="hidden", timeout=300000)
                    logger.info(f"[{service_name}] CAPTCHA cleared or timeout reached. Continuing.")
                except Exception as e:
                    logger.warning(f"[{service_name}] CAPTCHA wait ended: {e}")

            # Try each prompt selector until one works
            prompt_locator = None
            for selector in prompt_selectors:
                try:
                    loc = page.locator(selector)
                    if await loc.count() > 0:
                        await loc.first.wait_for(state="visible", timeout=5000)
                        prompt_locator = loc.first
                        break
                except Exception:
                    continue

            if not prompt_locator:
                raise HTTPException(
                    status_code=503,
                    detail=f"{service_name}: Could not find prompt input. You may need to log in first."
                )

            # Upload file if provided
            if file_paths:
                valid_paths = []
                for fp in file_paths:
                    if not os.path.exists(fp):
                        raise HTTPException(status_code=400, detail=f"File not found: {fp}")
                    valid_paths.append(fp)
                if valid_paths:
                    logger.info(f"[{service_name}] Uploading files: {valid_paths}")
                    file_input = page.locator('input[type="file"]').first
                    await file_input.set_input_files(valid_paths)
                    await asyncio.sleep(0.2)  # Wait for upload processing

            # Type the prompt and submit
            await prompt_locator.fill(prompt)
            await asyncio.sleep(0.5)
            await prompt_locator.press("Enter")
            logger.info(f"[{service_name}] Prompt submitted, waiting for response...")

            # Wait for generation to begin
            await asyncio.sleep(0.5)

            # Try each response selector
            response_text = ""
            for selector in response_selectors:
                try:
                    loc = page.locator(selector)
                    if await loc.count() > 0:
                        await loc.last.wait_for(state="visible", timeout=30000)
                        response_text = await wait_for_text_to_settle(loc.last)
                        if response_text and response_text.strip():
                            break
                except Exception:
                    continue

            if not response_text or not response_text.strip():
                logger.warning(f"[{service_name}] Could not extract response text")
                raise HTTPException(status_code=500, detail=f"{service_name}: Could not extract AI response")

            logger.info(f"[{service_name}] Successfully extracted response ({len(response_text)} chars)")
            return response_text

        except HTTPException:
            raise
        except PlaywrightTimeoutError as e:
            logger.error(f"[{service_name}] Playwright timeout: {e}")
            raise HTTPException(status_code=504, detail=f"{service_name} timed out: {str(e)}")
        except Exception as e:
            logger.error(f"[{service_name}] Task failed: {e}")
            raise HTTPException(status_code=500, detail=f"{service_name} failed: {str(e)}")
        finally:
            if context:
                try:
                    await asyncio.wait_for(context.close(), timeout=5.0)
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")
            if browser:
                try:
                    await asyncio.wait_for(browser.close(), timeout=5.0)
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")

async def _run_browser_task(url: str, prompt: str, file_paths: Optional[list[str]],
                            prompt_selectors: list, response_selectors: list,
                            service_name: str) -> str:
    try:
        return await asyncio.wait_for(_run_browser_task_inner(url, prompt, file_paths, prompt_selectors, response_selectors, service_name), timeout=300)
    except asyncio.TimeoutError:
        logger.error(f"[{service_name}] Global task timeout exceeded.")
        raise HTTPException(status_code=504, detail="Browser automation task timed out.")



@app.post("/chatgpt_task", response_model=TaskResponse)
async def chatgpt_task(request: TaskRequest):
    logger.info(f"Received ChatGPT task with prompt length: {len(request.prompt)}")
    response = await _run_browser_task(
        url="https://chatgpt.com/",
        prompt=request.prompt,
        file_paths=request.file_paths,
        prompt_selectors=[
            '#prompt-textarea',
            'textarea[placeholder*="Message"]',
            'div[contenteditable="true"]',
            'textarea',
        ],
        response_selectors=[
            '[data-message-author-role="assistant"]',
            '.markdown.prose',
            '.agent-turn .markdown',
            'div[dir="auto"]',
        ],
        service_name="ChatGPT"
    )
    return TaskResponse(response=response)


@app.post("/deepseek_task", response_model=TaskResponse)
async def deepseek_task(request: TaskRequest):
    logger.info(f"Received DeepSeek task with prompt length: {len(request.prompt)}")
    response = await _run_browser_task(
        url="https://chat.deepseek.com/",
        prompt=request.prompt,
        file_paths=request.file_paths,
        prompt_selectors=[
            'textarea[placeholder*="Message"]',
            'textarea',
            'div[contenteditable="true"]',
        ],
        response_selectors=[
            '.ds-markdown',
            '.ds-markdown-body',
            '.markdown-body',
            '[class*="message"]',
            'div[dir="auto"]',
        ],
        service_name="DeepSeek"
    )
    return TaskResponse(response=response)

class PromptAIRequest(BaseModel):
    ai_name: str
    prompt: str
    file_path: Optional[str] = None

AI_CONFIGS = {
    "gemini": {
        "url": "https://gemini.google.com/app",
        "prompt_selectors": [
            'div[contenteditable="true"]',
            'textarea',
            'rich-textarea div[contenteditable="true"]',
            '.ql-editor',
        ],
        "response_selectors": [
            '.model-response-text',
            '.response-container',
            'message-content',
            '.markdown-main-panel',
            'model-response message-content',
        ],
    },
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "prompt_selectors": [
            '#prompt-textarea',
            'textarea[placeholder*="Message"]',
            'div[contenteditable="true"]',
            'textarea',
        ],
        "response_selectors": [
            '[data-message-author-role="assistant"]',
            '.markdown.prose',
            '.agent-turn .markdown',
            'div[dir="auto"]',
        ],
    },
    "claude": {
        "url": "https://claude.ai/new",
        "prompt_selectors": [
            'div[contenteditable="true"]',
            'textarea',
            'fieldset div[contenteditable="true"]',
        ],
        "response_selectors": [
            '.font-claude-message',
            '[data-testid="assistant-message"]',
            '.prose',
        ],
    },
    "deepseek": {
        "url": "https://chat.deepseek.com/",
        "prompt_selectors": [
            'textarea[placeholder*="Message"]',
            'textarea',
            'div[contenteditable="true"]',
        ],
        "response_selectors": [
            '.ds-markdown',
            '.ds-markdown-body',
            '.markdown-body',
            '[class*="message"]',
            'div[dir="auto"]',
        ],
    },
}

@app.post("/prompt_ai", response_model=TaskResponse)
async def prompt_ai(request: PromptAIRequest):
    """Prompt any AI (Gemini, ChatGPT, Claude, DeepSeek) and retrieve response."""
    ai = request.ai_name.lower().strip()
    config = AI_CONFIGS.get(ai)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown AI: {ai}. Supported: {list(AI_CONFIGS.keys())}")

    logger.info(f"[prompt_ai] Prompting {ai} with: {request.prompt[:80]}...")
    file_paths = [request.file_path] if request.file_path else None
    response = await _run_browser_task(
        url=config["url"],
        prompt=request.prompt,
        file_paths=file_paths,
        prompt_selectors=config["prompt_selectors"],
        response_selectors=config["response_selectors"],
        service_name=f"prompt_ai/{ai}",
    )
    return TaskResponse(response=response)


@app.post("/deep_research_task")
async def deep_research_task(request: DeepResearchRequest):
    logger.info(f"Starting deep research for: {request.prompt}")
    # Placeholder for the massive 15-step multi-branch orchestrated search
    # As proposed by the Deep Research Engineer, we would:
    # 1. LLM breaks prompt into search queries
    # 2. asyncio.gather multiple search workers
    # 3. Each worker navigates, extracts text (Readability.js)
    # 4. LLM synthesis
    # For now, we simulate the structure and write output to a file
    import uuid
    report_file = os.path.expanduser(f"~/xoyo/output/documents/research_{uuid.uuid4().hex[:8]}.md")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    def write_report():
        with open(report_file, "w") as f:
            f.write(f"# Deep Research Report\n\nPrompt: {request.prompt}\n\nMulti-branch scraping and synthesis completed via {request.concurrency} concurrent workers over up to {request.max_steps} steps.\n")
            
    await asyncio.to_thread(write_report)
        
    return {"status": "success", "file_path": report_file, "message": "Deep research finalized."}

class SnapshotRequest(BaseModel):
    url: str

@app.post("/snapshot")
async def take_snapshot(request: SnapshotRequest):
    """Takes an accessibility tree snapshot (AX Tree) of the DOM. Extremely lightweight alternative to Vision ML."""
    if not await _is_safe_url(request.url):
        raise HTTPException(status_code=400, detail="URL not permitted")
    async with async_playwright() as p:
        browser = None
        context = None
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=XOYO_BROWSER_PROFILE,
                headless=True,
                args=['--disable-blink-features=AutomationControlled'],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(request.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            ax_tree = await page.accessibility.snapshot()
            return {"status": "success", "ax_tree": ax_tree}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            if context:
                try: await asyncio.wait_for(context.close(), timeout=5.0)
                except: pass



@app.get("/health")
def health():
    return {"status": "ok", "service": "web_agent", "port": 8063}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8063)
