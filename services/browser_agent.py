import os
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
from playwright.async_api import async_playwright

app = FastAPI(title="Browser AI Agent")

class PromptRequest(BaseModel):
    ai_name: str
    prompt: str
    file_path: Optional[str] = None

@app.post("/prompt_ai")
async def prompt_ai(req: PromptRequest):
    ai_name = req.ai_name.lower()
    
    if ai_name not in ["gemini", "chatgpt", "claude"]:
        raise HTTPException(status_code=400, detail="ai_name must be gemini, chatgpt, or claude")
        
    if req.file_path and not os.path.exists(req.file_path):
        raise HTTPException(status_code=400, detail=f"File not found: {req.file_path}")
        
    try:
        async with async_playwright() as p:
            # Use persistent context to maintain login sessions
            user_data_dir = os.path.expanduser("~/.config/xoyo-browser-ai")
            
            # If the user data dir doesn't exist, playwright will create it
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False, # Must be false to see the UI, or for captchas
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            page = await context.new_page()
            
            import re
            if ai_name == "gemini":
                await page.goto("https://gemini.google.com/")
                await page.wait_for_load_state("networkidle")
                
                # Check for upload file if requested
                if req.file_path and os.path.exists(req.file_path):
                    async with page.expect_file_chooser() as fc_info:
                        await page.get_by_label("Upload file", exact=False).first.click(timeout=5000)
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(req.file_path)
                    await page.wait_for_timeout(2000) # wait for upload
                
                # Find the text box (rich text editor)
                editor = page.get_by_role("textbox", name=re.compile("prompt|message|ask", re.IGNORECASE))
                if await editor.count() == 0: editor = page.get_by_role("textbox").first
                await editor.fill(req.prompt)
                
                # Hit enter or click send
                await page.keyboard.press("Enter")
                
            elif ai_name == "chatgpt":
                await page.goto("https://chatgpt.com/")
                await page.wait_for_load_state("networkidle")
                
                if req.file_path and os.path.exists(req.file_path):
                    async with page.expect_file_chooser() as fc_info:
                        await page.get_by_label("Attach files", exact=False).first.click(timeout=5000)
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(req.file_path)
                    await page.wait_for_timeout(2000)
                
                # fill the prompt area
                editor = page.get_by_role("textbox", name=re.compile("message", re.IGNORECASE))
                if await editor.count() == 0: editor = page.get_by_role("textbox").first
                await editor.fill(req.prompt)
                await page.keyboard.press("Enter")
                
            elif ai_name == "claude":
                await page.goto("https://claude.ai/")
                await page.wait_for_load_state("networkidle")
                
                if req.file_path and os.path.exists(req.file_path):
                    async with page.expect_file_chooser() as fc_info:
                        # Find the attach button
                        await page.get_by_role("button", name=re.compile(r"attachment|upload", re.IGNORECASE)).first.click(timeout=5000)
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(req.file_path)
                    await page.wait_for_timeout(2000)
                
                editor = page.get_by_role("textbox")
                if await editor.count() > 1: editor = editor.last
                else: editor = editor.first
                await editor.fill(req.prompt)
                await page.keyboard.press("Enter")
                
            # Wait a few seconds for the request to be sent
            await page.wait_for_timeout(3000)
            await context.close()
            
            return {"status": "success", "message": f"Prompt sent to {ai_name} successfully."}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8064)
