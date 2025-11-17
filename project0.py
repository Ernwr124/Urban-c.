"""
Project-0: Powerful AI Coding Platform
Inspired by v0dev and Cursor AI
Using Ollama GLM-4.6:cloud model
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict
import time
from datetime import datetime

app = FastAPI(title="Project-0", description="Powerful AI Coding Platform")

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

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application UI"""
    return HTML_TEMPLATE

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

# Embedded HTML/CSS/JS for the UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Powerful AI Coding Platform</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
            background: #000000;
            color: #ffffff;
            height: 100vh;
            overflow: hidden;
        }

        .container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        /* Header */
        .header {
            background: #000000;
            border-bottom: 1px solid #333;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #ffffff 0%, #888888 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 18px;
            color: #000;
        }

        .logo-text {
            font-size: 20px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            background: #111;
            border: 1px solid #333;
            border-radius: 6px;
            font-size: 13px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: #00ff00;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Chat Area */
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            scroll-behavior: smooth;
        }

        .message {
            margin-bottom: 24px;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }

        .message-role {
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .user-role {
            color: #ffffff;
        }

        .assistant-role {
            color: #888888;
        }

        .message-content {
            padding: 16px;
            border-radius: 12px;
            line-height: 1.6;
            font-size: 14px;
        }

        .user-message .message-content {
            background: #1a1a1a;
            border: 1px solid #333;
        }

        .assistant-message .message-content {
            background: #0a0a0a;
            border: 1px solid #222;
        }

        .thinking-indicator {
            display: inline-block;
            padding: 8px 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            font-size: 13px;
            color: #888;
            margin-bottom: 12px;
        }

        /* Code blocks */
        pre {
            background: #0d0d0d;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            overflow-x: auto;
            margin: 12px 0;
        }

        code {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            color: #e0e0e0;
        }

        /* Input Area */
        .input-area {
            padding: 24px;
            background: #000000;
            border-top: 1px solid #333;
        }

        .input-container {
            display: flex;
            gap: 12px;
            max-width: 1200px;
            margin: 0 auto;
        }

        .input-wrapper {
            flex: 1;
            position: relative;
        }

        #messageInput {
            width: 100%;
            padding: 16px 60px 16px 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            color: #ffffff;
            font-size: 14px;
            font-family: inherit;
            resize: none;
            outline: none;
            transition: border-color 0.2s;
            min-height: 56px;
            max-height: 200px;
        }

        #messageInput:focus {
            border-color: #666;
        }

        #messageInput::placeholder {
            color: #666;
        }

        #sendButton {
            position: absolute;
            right: 12px;
            bottom: 12px;
            width: 36px;
            height: 36px;
            background: #ffffff;
            color: #000000;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }

        #sendButton:hover:not(:disabled) {
            background: #e0e0e0;
            transform: translateY(-1px);
        }

        #sendButton:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: #000;
        }

        ::-webkit-scrollbar-thumb {
            background: #333;
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #444;
        }

        /* Loading animation */
        .loading {
            display: inline-block;
        }

        .loading::after {
            content: '...';
            animation: dots 1.5s infinite;
        }

        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }

        /* Welcome screen */
        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            text-align: center;
            padding: 24px;
        }

        .welcome-logo {
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #ffffff 0%, #888888 100%);
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 36px;
            color: #000;
            margin-bottom: 24px;
        }

        .welcome-title {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: -1px;
        }

        .welcome-subtitle {
            font-size: 16px;
            color: #888;
            margin-bottom: 32px;
            max-width: 500px;
        }

        .example-prompts {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 12px;
            max-width: 800px;
            width: 100%;
        }

        .example-prompt {
            padding: 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }

        .example-prompt:hover {
            background: #222;
            border-color: #666;
            transform: translateY(-2px);
        }

        .example-prompt-title {
            font-weight: 600;
            margin-bottom: 4px;
            font-size: 14px;
        }

        .example-prompt-text {
            font-size: 12px;
            color: #888;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="logo">
                <div class="logo-icon">0</div>
                <div class="logo-text">Project-0</div>
            </div>
            <div class="status-indicator">
                <div class="status-dot"></div>
                <span>GLM-4.6 Ready</span>
            </div>
        </div>

        <!-- Chat Container -->
        <div class="chat-container">
            <div class="messages" id="messages">
                <div class="welcome">
                    <div class="welcome-logo">0</div>
                    <div class="welcome-title">Welcome to Project-0</div>
                    <div class="welcome-subtitle">
                        The most powerful AI coding platform. Create anything from a simple script to a full-stack application. 
                        Just describe what you want to build.
                    </div>
                    <div class="example-prompts">
                        <div class="example-prompt" onclick="useExample(&quot;Create a full-stack todo app with React and Node.js&quot;)">
                            <div class="example-prompt-title">🚀 Full-Stack App</div>
                            <div class="example-prompt-text">Create a complete application</div>
                        </div>
                        <div class="example-prompt" onclick="useExample(&quot;Build a REST API with authentication and database&quot;)">
                            <div class="example-prompt-title">🔧 REST API</div>
                            <div class="example-prompt-text">Backend with auth & DB</div>
                        </div>
                        <div class="example-prompt" onclick="useExample(&quot;Design a modern landing page with animations&quot;)">
                            <div class="example-prompt-title">🎨 UI Design</div>
                            <div class="example-prompt-text">Beautiful frontend page</div>
                        </div>
                        <div class="example-prompt" onclick="useExample(&quot;Create a Python script for data analysis with pandas&quot;)">
                            <div class="example-prompt-title">📊 Data Script</div>
                            <div class="example-prompt-text">Analysis & visualization</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Input Area -->
            <div class="input-area">
                <div class="input-container">
                    <div class="input-wrapper">
                        <textarea 
                            id="messageInput" 
                            placeholder="Describe what you want to build... (Shift+Enter for new line)"
                            rows="1"
                        ></textarea>
                        <button id="sendButton" onclick="sendMessage()">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let isProcessing = false;
        let messageHistory = [];

        // Auto-resize textarea
        const messageInput = document.getElementById('messageInput');
        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });

        // Handle Enter key
        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        function useExample(text) {
            messageInput.value = text;
            messageInput.focus();
            messageInput.style.height = 'auto';
            messageInput.style.height = messageInput.scrollHeight + 'px';
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message || isProcessing) return;
            
            isProcessing = true;
            const sendButton = document.getElementById('sendButton');
            sendButton.disabled = true;
            
            // Clear input
            input.value = '';
            input.style.height = 'auto';
            
            // Remove welcome screen
            const welcome = document.querySelector('.welcome');
            if (welcome) {
                welcome.remove();
            }
            
            // Add user message
            addMessage('user', message);
            messageHistory.push({role: 'user', content: message});
            
            // Create assistant message container
            const messagesDiv = document.getElementById('messages');
            const assistantDiv = document.createElement('div');
            assistantDiv.className = 'message assistant-message';
            assistantDiv.innerHTML = 
                '<div class="message-header">' +
                    '<span class="message-role assistant-role">Project-0</span>' +
                '</div>' +
                '<div class="thinking-indicator">' +
                    '<span class="loading">Thinking</span>' +
                '</div>' +
                '<div class="message-content" id="currentResponse"></div>';
            messagesDiv.appendChild(assistantDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        messages: messageHistory,
                        stream: true
                    })
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                
                                if (data.type === 'thinking') {
                                    const thinkingDiv = assistantDiv.querySelector('.thinking-indicator');
                                    if (thinkingDiv) {
                                        thinkingDiv.textContent = data.content;
                                    }
                                } else if (data.type === 'content') {
                                    // Remove thinking indicator
                                    const thinkingDiv = assistantDiv.querySelector('.thinking-indicator');
                                    if (thinkingDiv) {
                                        thinkingDiv.remove();
                                    }
                                    
                                    fullResponse += data.content;
                                    const responseDiv = document.getElementById('currentResponse');
                                    responseDiv.innerHTML = formatMessage(fullResponse);
                                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                                } else if (data.type === 'done') {
                                    messageHistory.push({role: 'assistant', content: fullResponse});
                                } else if (data.type === 'error') {
                                    const responseDiv = document.getElementById('currentResponse');
                                    responseDiv.innerHTML = `<span style="color: #ff4444;">${data.content}</span>`;
                                }
                            } catch (e) {
                                console.error('Parse error:', e);
                            }
                        }
                    }
                }
            } catch (error) {
                console.error('Error:', error);
                const responseDiv = document.getElementById('currentResponse');
                responseDiv.innerHTML = `<span style="color: #ff4444;">Error: ${error.message}</span>`;
            } finally {
                isProcessing = false;
                sendButton.disabled = false;
                input.focus();
            }
        }
        
        function addMessage(role, content) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}-message`;
            
            const roleLabel = role === 'user' ? 'You' : 'Project-0';
            const roleClass = role === 'user' ? 'user-role' : 'assistant-role';
            
            messageDiv.innerHTML = 
                '<div class="message-header">' +
                    '<span class="message-role ' + roleClass + '">' + roleLabel + '</span>' +
                '</div>' +
                '<div class="message-content">' + formatMessage(content) + '</div>';
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function formatMessage(content) {
            // Format code blocks
            content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, lang, code) {
                lang = lang || '';
                return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
            });
            
            // Format inline code
            content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // Format bold
            content = content.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
            
            // Format line breaks
            content = content.replace(/\n/g, '<br>');
            
            return content;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Focus input on load
        window.addEventListener('load', () => {
            messageInput.focus();
        });
    </script>
</body>
</html>
"""

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
