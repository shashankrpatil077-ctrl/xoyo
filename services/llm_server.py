from fastapi import FastAPI
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import uvicorn

app = FastAPI()

device = "cuda" if torch.cuda.is_available() else "cpu"
model_name = "Qwen/Qwen2.5-72B-Instruct"

print(f"Loading {model_name} on {device}...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
    max_memory={0: "180GB"}  # leave 12GB for other services
)
print("Model loaded.")

class ChatRequest(BaseModel):
    messages: list
    max_tokens: int = 400
    temperature: float = 0.7

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    inputs = tokenizer.apply_chat_template(
        req.messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            inputs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    
    generated = outputs[0][inputs.shape[-1]:]
    reply = tokenizer.decode(generated, skip_special_tokens=True)
    
    return {
        "choices": [{"message": {"role": "assistant", "content": reply.strip()}}]
    }

@app.get("/health")
def health():
    return {"status": "ok", "model": model_name}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
