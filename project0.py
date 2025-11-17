"""
Project-0: Powerful AI Coding Platform
Inspired by v0dev and Cursor AI
Using Ollama GLM-4.6:cloud model
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict
import time
from datetime import datetime

app = FastAPI(title="Project-0", description="Powerful AI Coding Platform")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "glm-4.6:cloud"

# System prompt for powerful agent mode with reasoning
SYSTEM_PROMPT = """You are Project-0, an extremely powerful AI coding assistant created for professional software development.

Your capabilities:
- Generate complete, production-ready code in ANY programming language or framework
- Create full-stack applications from scratch
- Design beautiful, modern UIs with best practices
- Solve complex algorithmic and architectural problems
- Debug and optimize existing code
- Write comprehensive documentation and tests

AGENT MODE ENABLED: You think step-by-step, reason through problems, and provide comprehensive solutions.

When responding:
1. **THINK**: Break down the problem and reason about the approach
2. **PLAN**: Outline the solution architecture
3. **IMPLEMENT**: Provide complete, working code with all necessary files
4. **EXPLAIN**: Clarify key decisions and usage instructions

Always:
- Use modern best practices
- Include all imports and dependencies
- Make code production-ready
- Add helpful comments
- Consider edge cases and error handling
- Provide setup instructions when needed

Remember: You're not just writing code - you're engineering solutions that work perfectly."""

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = True

# Store conversation history (in production, use database)
conversation_history: Dict[str, List[Dict]] = {}

async def generate_ai_response(messages: List[Dict], session_id: str) -> AsyncGenerator[str, None]:
    """
    Generate AI response using Ollama with agent reasoning mode
    Streams the response in real-time
    """
    # Prepare messages with system prompt
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + messages
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Add reasoning step
            yield f"data: {json.dumps({'type': 'thinking', 'content': '🧠 Analyzing request...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'thinking', 'content': '📋 Planning solution...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'thinking', 'content': '⚡ Generating code...'})}\n\n"
            await asyncio.sleep(0.3)
            
            # Stream response from Ollama
            async with client.stream(
                "POST",
                OLLAMA_API_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": full_messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_ctx": 8192,  # Use extended context
                    }
                }
            ) as response:
                full_response = ""
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                content = data["message"]["content"]
                                full_response += content
                                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                            
                            if data.get("done", False):
                                # Store in conversation history
                                if session_id not in conversation_history:
                                    conversation_history[session_id] = []
                                conversation_history[session_id].extend([
                                    messages[-1],  # User message
                                    {"role": "assistant", "content": full_response}
                                ])
                                yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

@app.get("/")
async def root():
    """Serve the main application UI"""
    return FileResponse("static/index.html")

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint with streaming support
    """
    session_id = str(time.time())
    messages = [msg.dict() for msg in request.messages]
    
    if request.stream:
        return StreamingResponse(
            generate_ai_response(messages, session_id),
            media_type="text/event-stream"
        )
    else:
        # Non-streaming response
        full_response = ""
        async for chunk in generate_ai_response(messages, session_id):
            if '"type": "content"' in chunk:
                data = json.loads(chunk.replace("data: ", ""))
                full_response += data["content"]
        
        return {"response": full_response}

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME
    }

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║            🚀 PROJECT-0 STARTING UP 🚀               ║
    ║                                                       ║
    ║   Powerful AI Coding Platform                        ║
    ║   Powered by GLM-4.6:cloud                           ║
    ║                                                       ║
    ║   Open: http://localhost:8000                        ║
    ║                                                       ║
    ║   Make sure Ollama is running:                       ║
    ║   $ ollama serve                                     ║
    ║   $ ollama pull glm-4.6:cloud                        ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
