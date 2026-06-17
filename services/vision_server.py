from fastapi import FastAPI
from pydantic import BaseModel, field_validator
import httpx
import uvicorn
import base64
import binascii

app = FastAPI()

class VisionRequest(BaseModel):
    image_base64: str
    prompt: str = "Describe this image in detail. Pay attention to any UI elements, text, applications, or actionable areas if it is a desktop screenshot."
    max_tokens: int = 200

    @field_validator('image_base64')
    @classmethod
    def validate_image_base64(cls, v):
        MAX_SIZE_MB = 5
        MAX_BASE64_LENGTH = int((MAX_SIZE_MB * 1024 * 1024 * 4) / 3)
        if len(v) > MAX_BASE64_LENGTH:
            raise ValueError(f"Image base64 string exceeds maximum allowed size of {MAX_SIZE_MB}MB.")
            
        try:
            # Strip standard data URL prefix if present
            if v.startswith("data:image"):
                v = v.split(",", 1)[1]
            decoded = base64.b64decode(v, validate=True)
        except binascii.Error:
            raise ValueError("Invalid base64 string provided.")
            
        # Check magic numbers for common image formats (JPEG, PNG, GIF, WEBP)
        is_jpeg = decoded.startswith(b'\xff\xd8')
        is_png = decoded.startswith(b'\x89PNG\r\n\x1a\n')
        is_gif = decoded.startswith(b'GIF87a') or decoded.startswith(b'GIF89a')
        is_webp = decoded.startswith(b'RIFF') and decoded[8:12] == b'WEBP'
        
        if not (is_jpeg or is_png or is_gif or is_webp):
            raise ValueError("Decoded base64 does not match a supported image format (JPEG, PNG, GIF, WEBP).")

        return v

@app.post("/v1/chat/completions")
async def vision_chat(req: VisionRequest):
    try:
        # Proxy to Ollama
        async with httpx.AsyncClient() as client:
            payload = {
                "model": "llava",  # Lite mode vision model
                "messages": [
                    {
                        "role": "user",
                        "content": req.prompt,
                        "images": [req.image_base64]
                    }
                ],
                "stream": False,
                "options": {
                    "num_predict": req.max_tokens
                }
            }
            response = await client.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=120)
            if response.status_code != 200:
                raise Exception(f"Ollama returned {response.status_code}")
            
            data = response.json()
            reply = data.get("message", {}).get("content", "")
            return {"choices": [{"message": {"role": "assistant", "content": reply}}]}
    except Exception as e:
        return {"error": str(e), "choices": [{"message": {"role": "assistant", "content": "[Vision model unavailable]"}}]}

@app.get("/health")
def health():
    return {"status": "ok", "mode": "ollama_proxy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
