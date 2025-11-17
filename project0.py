"""
Project-0: AI-Powered MVP Generator
Transform ideas into working prototypes with HTML, Tailwind CSS, and React.js
Powered by Ollama GLM-4.6:cloud
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict
import time
from datetime import datetime
import re

app = FastAPI(title="Project-0", description="AI-Powered MVP Generator")

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

# System prompt for MVP generation
SYSTEM_PROMPT = """You are Project-0, an AI MVP generator that transforms ideas into working prototypes.

Your task:
1. Listen to the user's idea (even if incomplete)
2. Fill in missing details creatively and logically
3. Generate a complete, beautiful MVP using HTML, Tailwind CSS, and React.js
4. Create production-ready, responsive, modern UI

Rules:
- ALWAYS use Tailwind CSS for styling (CDN link included)
- ALWAYS use React (from CDN)
- Create COMPLETE, WORKING code that runs immediately
- Make it beautiful, modern, and professional
- Add animations, transitions, hover effects
- Make it fully responsive
- Use modern color schemes (gradients, shadows)
- Include all necessary functionality
- Add placeholder data if needed
- Make it interactive and engaging

If the idea is incomplete:
- Imagine the best possible implementation
- Add features that make sense
- Create a compelling user experience
- Fill in all gaps with creative solutions

Response Format:
Use markdown with clear sections:

## 📋 MVP Concept
[Explain the idea and what you're building]

## ✨ Features Included
- Feature 1
- Feature 2
...

## 💻 Implementation
```html
[Complete HTML+Tailwind+React code here]
```

## 🎯 How to Use
[Brief instructions]

Always generate COMPLETE, WORKING code. No placeholders, no TODOs."""

class ChatMessage(BaseModel):
    role: str
    content: str

class GenerateRequest(BaseModel):
    idea: str

# Store generated MVPs
generated_mvps: Dict[str, Dict] = {}

async def generate_mvp(idea: str) -> AsyncGenerator[str, None]:
    """
    Generate MVP using Ollama with streaming
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a complete MVP for this idea: {idea}"}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 Analyzing your idea...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '✨ Designing MVP architecture...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '🎨 Creating beautiful UI...'})}\n\n"
            await asyncio.sleep(0.5)
            
            # Stream response from Ollama
            async with client.stream(
                "POST",
                OLLAMA_API_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.8,
                        "top_p": 0.95,
                        "num_ctx": 8192,
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
                                # Extract HTML code from response
                                html_code = extract_html(full_response)
                                mvp_id = str(int(time.time()))
                                generated_mvps[mvp_id] = {
                                    "idea": idea,
                                    "code": html_code,
                                    "markdown": full_response,
                                    "timestamp": datetime.now().isoformat()
                                }
                                
                                yield f"data: {json.dumps({'type': 'done', 'mvp_id': mvp_id, 'has_code': bool(html_code)})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

def extract_html(markdown_text: str) -> str:
    """Extract HTML code from markdown"""
    # Find HTML code block
    pattern = r'```html\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    if matches:
        return matches[0].strip()
    
    # Try without language specifier
    pattern = r'```\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    if matches:
        # Check if it looks like HTML
        code = matches[0].strip()
        if '<!DOCTYPE' in code or '<html' in code or '<div' in code:
            return code
    
    return ""

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application UI"""
    return HTML_TEMPLATE

@app.post("/api/generate")
async def generate(request: GenerateRequest):
    """
    Generate MVP from idea with streaming
    """
    return StreamingResponse(
        generate_mvp(request.idea),
        media_type="text/event-stream"
    )

@app.get("/api/preview/{mvp_id}")
async def get_preview(mvp_id: str):
    """Get preview HTML for generated MVP"""
    if mvp_id not in generated_mvps:
        return JSONResponse({"error": "MVP not found"}, status_code=404)
    
    mvp = generated_mvps[mvp_id]
    return JSONResponse({
        "code": mvp["code"],
        "markdown": mvp["markdown"],
        "idea": mvp["idea"]
    })

@app.get("/preview/{mvp_id}", response_class=HTMLResponse)
async def preview_page(mvp_id: str):
    """Render preview page"""
    if mvp_id not in generated_mvps:
        return "<h1>MVP not found</h1>"
    
    mvp = generated_mvps[mvp_id]
    return mvp["code"] if mvp["code"] else "<h1>No HTML code generated</h1>"

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "generated_mvps": len(generated_mvps)
    }

# Main HTML Template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - AI MVP Generator</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
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
            height: 100vh;
        }

        /* Left Panel - Chat */
        .chat-panel {
            width: 45%;
            display: flex;
            flex-direction: column;
            border-right: 1px solid #333;
        }

        /* Right Panel - Preview */
        .preview-panel {
            width: 55%;
            display: flex;
            flex-direction: column;
            background: #0a0a0a;
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

        .status-badge {
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

        /* Messages Area */
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
        }

        .message {
            margin-bottom: 24px;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
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

        .user-role { color: #ffffff; }
        .ai-role { color: #888888; }

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

        .ai-message .message-content {
            background: #0a0a0a;
            border: 1px solid #222;
        }

        .status-indicator {
            display: inline-block;
            padding: 8px 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            font-size: 13px;
            color: #888;
            margin-bottom: 12px;
        }

        /* Markdown Styles */
        .markdown-content h2 {
            font-size: 18px;
            font-weight: 700;
            margin: 20px 0 12px 0;
            color: #fff;
        }

        .markdown-content h3 {
            font-size: 16px;
            font-weight: 600;
            margin: 16px 0 8px 0;
            color: #ccc;
        }

        .markdown-content ul {
            margin: 8px 0 8px 20px;
        }

        .markdown-content li {
            margin: 4px 0;
            color: #aaa;
        }

        .markdown-content code {
            background: #1a1a1a;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Monaco', monospace;
            font-size: 13px;
            color: #00ff88;
        }

        .markdown-content pre {
            background: #0d0d0d;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            overflow-x: auto;
            margin: 12px 0;
        }

        .markdown-content pre code {
            background: none;
            padding: 0;
            color: #e0e0e0;
        }

        .markdown-content strong {
            color: #fff;
            font-weight: 600;
        }

        /* Preview Button */
        .preview-button {
            display: inline-block;
            margin-top: 12px;
            padding: 10px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }

        .preview-button:hover {
            transform: translateY(-2px);
        }

        /* Input Area */
        .input-area {
            padding: 24px;
            background: #000000;
            border-top: 1px solid #333;
        }

        .input-wrapper {
            position: relative;
        }

        #ideaInput {
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
            min-height: 80px;
            max-height: 200px;
        }

        #ideaInput:focus {
            border-color: #667eea;
        }

        #ideaInput::placeholder {
            color: #666;
        }

        #generateBtn {
            position: absolute;
            right: 12px;
            bottom: 12px;
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s;
        }

        #generateBtn:hover:not(:disabled) {
            transform: translateY(-2px);
        }

        #generateBtn:disabled {
            background: #333;
            cursor: not-allowed;
        }

        /* Preview Panel */
        .preview-header {
            padding: 16px 24px;
            background: #0a0a0a;
            border-bottom: 1px solid #222;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .preview-title {
            font-size: 16px;
            font-weight: 600;
            color: #888;
        }

        .preview-actions {
            display: flex;
            gap: 8px;
        }

        .preview-btn {
            padding: 8px 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 6px;
            color: #fff;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .preview-btn:hover {
            background: #222;
            border-color: #555;
        }

        .preview-frame {
            flex: 1;
            background: white;
        }

        iframe {
            width: 100%;
            height: 100%;
            border: none;
        }

        .preview-placeholder {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #555;
            text-align: center;
            padding: 40px;
        }

        .placeholder-icon {
            width: 80px;
            height: 80px;
            background: #1a1a1a;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            margin-bottom: 16px;
        }

        .placeholder-text {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .placeholder-hint {
            font-size: 14px;
            color: #666;
        }

        /* Welcome Screen */
        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            padding: 40px;
            text-align: center;
        }

        .welcome-logo {
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 36px;
            color: #fff;
            margin-bottom: 24px;
        }

        .welcome-title {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 12px;
        }

        .welcome-subtitle {
            font-size: 16px;
            color: #888;
            margin-bottom: 32px;
            max-width: 400px;
        }

        .example-ideas {
            display: grid;
            gap: 12px;
            max-width: 500px;
            width: 100%;
        }

        .example-idea {
            padding: 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }

        .example-idea:hover {
            background: #222;
            border-color: #555;
            transform: translateY(-2px);
        }

        .example-title {
            font-weight: 600;
            margin-bottom: 4px;
            font-size: 14px;
        }

        .example-desc {
            font-size: 12px;
            color: #888;
        }

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
    </style>
</head>
<body>
    <div class="container">
        <!-- Left Panel: Chat -->
        <div class="chat-panel">
            <div class="header">
                <div class="logo">
                    <div class="logo-icon">0</div>
                    <div class="logo-text">Project-0</div>
                </div>
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span>AI Ready</span>
                </div>
            </div>

            <div class="messages" id="messages">
                <div class="welcome">
                    <div class="welcome-logo">0</div>
                    <div class="welcome-title">AI MVP Generator</div>
                    <div class="welcome-subtitle">
                        Describe your idea and watch AI build a working prototype with HTML, Tailwind CSS, and React.js
                    </div>
                    <div class="example-ideas">
                        <div class="example-idea" data-idea="Create a modern landing page for a SaaS product with pricing section, features, and testimonials">
                            <div class="example-title">🚀 SaaS Landing Page</div>
                            <div class="example-desc">Professional marketing page</div>
                        </div>
                        <div class="example-idea" data-idea="Build a todo app with categories, due dates, and dark mode">
                            <div class="example-title">✅ Todo Application</div>
                            <div class="example-desc">Task management tool</div>
                        </div>
                        <div class="example-idea" data-idea="Design a modern dashboard for analytics with charts and stats">
                            <div class="example-title">📊 Analytics Dashboard</div>
                            <div class="example-desc">Data visualization interface</div>
                        </div>
                        <div class="example-idea" data-idea="Create an e-commerce product page with gallery, reviews, and cart">
                            <div class="example-title">🛍️ E-commerce Page</div>
                            <div class="example-desc">Online shopping interface</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="input-area">
                <div class="input-wrapper">
                    <textarea 
                        id="ideaInput" 
                        placeholder="Describe your MVP idea... AI will fill in the gaps and create a complete prototype!"
                    ></textarea>
                    <button id="generateBtn">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- Right Panel: Preview -->
        <div class="preview-panel">
            <div class="preview-header">
                <div class="preview-title">Live Preview</div>
                <div class="preview-actions">
                    <button class="preview-btn" id="refreshBtn" style="display:none;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:middle;margin-right:4px;">
                            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="preview-btn" id="newWindowBtn" style="display:none;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:middle;margin-right:4px;">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                        </svg>
                        New Window
                    </button>
                </div>
            </div>
            <div class="preview-frame" id="previewFrame">
                <div class="preview-placeholder">
                    <div class="placeholder-icon">✨</div>
                    <div class="placeholder-text">Ready to Build</div>
                    <div class="placeholder-hint">Describe your idea to see it come to life</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        var isGenerating = false;
        var currentMvpId = null;
        var ideaInput = document.getElementById('ideaInput');
        var generateBtn = document.getElementById('generateBtn');
        var messagesDiv = document.getElementById('messages');
        var previewFrame = document.getElementById('previewFrame');
        var refreshBtn = document.getElementById('refreshBtn');
        var newWindowBtn = document.getElementById('newWindowBtn');

        // Example ideas click handler
        document.addEventListener('DOMContentLoaded', function() {
            var exampleIdeas = document.querySelectorAll('.example-idea');
            exampleIdeas.forEach(function(idea) {
                idea.addEventListener('click', function() {
                    var text = this.getAttribute('data-idea');
                    ideaInput.value = text;
                    ideaInput.focus();
                });
            });
        });

        // Auto-resize textarea
        ideaInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });

        // Generate button click
        generateBtn.addEventListener('click', generate);

        // Enter to generate (Ctrl+Enter for new line)
        ideaInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                e.preventDefault();
                generate();
            }
        });

        function generate() {
            var idea = ideaInput.value.trim();
            if (!idea || isGenerating) return;

            isGenerating = true;
            generateBtn.disabled = true;

            // Remove welcome
            var welcome = document.querySelector('.welcome');
            if (welcome) welcome.remove();

            // Add user message
            addMessage('user', idea);

            // Clear input
            ideaInput.value = '';
            ideaInput.style.height = 'auto';

            // Create AI message container
            var aiDiv = document.createElement('div');
            aiDiv.className = 'message ai-message';
            aiDiv.innerHTML = 
                '<div class="message-header"><span class="message-role ai-role">Project-0</span></div>' +
                '<div class="status-indicator" id="statusIndicator">Initializing...</div>' +
                '<div class="message-content markdown-content" id="currentResponse"></div>';
            messagesDiv.appendChild(aiDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Fetch generation
            fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({idea: idea})
            })
            .then(function(response) {
                var reader = response.body.getReader();
                var decoder = new TextDecoder();
                var fullResponse = '';

                function readStream() {
                    reader.read().then(function(result) {
                        if (result.done) {
                            isGenerating = false;
                            generateBtn.disabled = false;
                            ideaInput.focus();
                            return;
                        }

                        var chunk = decoder.decode(result.value);
                        var lines = chunk.split('\\n');

                        for (var i = 0; i < lines.length; i++) {
                            var line = lines[i];
                            if (line.startsWith('data: ')) {
                                try {
                                    var data = JSON.parse(line.slice(6));

                                    if (data.type === 'status') {
                                        var statusDiv = document.getElementById('statusIndicator');
                                        if (statusDiv) statusDiv.textContent = data.content;
                                    } 
                                    else if (data.type === 'content') {
                                        var statusDiv = document.getElementById('statusIndicator');
                                        if (statusDiv) statusDiv.remove();

                                        fullResponse += data.content;
                                        var responseDiv = document.getElementById('currentResponse');
                                        if (responseDiv) {
                                            responseDiv.innerHTML = marked.parse(fullResponse);
                                        }
                                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                                    } 
                                    else if (data.type === 'done') {
                                        currentMvpId = data.mvp_id;
                                        if (data.has_code) {
                                            showPreview(data.mvp_id);
                                            
                                            // Add preview button
                                            var responseDiv = document.getElementById('currentResponse');
                                            var previewBtn = document.createElement('button');
                                            previewBtn.className = 'preview-button';
                                            previewBtn.textContent = '👁️ View Live Preview';
                                            previewBtn.onclick = function() {
                                                showPreview(data.mvp_id);
                                            };
                                            responseDiv.appendChild(previewBtn);
                                        }
                                    } 
                                    else if (data.type === 'error') {
                                        var responseDiv = document.getElementById('currentResponse');
                                        responseDiv.innerHTML = '<span style="color: #ff4444;">' + data.content + '</span>';
                                    }
                                } catch (e) {
                                    console.error('Parse error:', e);
                                }
                            }
                        }

                        readStream();
                    });
                }

                readStream();
            })
            .catch(function(error) {
                console.error('Error:', error);
                isGenerating = false;
                generateBtn.disabled = false;
            });
        }

        function showPreview(mvpId) {
            var iframe = document.createElement('iframe');
            iframe.src = '/preview/' + mvpId;
            previewFrame.innerHTML = '';
            previewFrame.appendChild(iframe);
            
            refreshBtn.style.display = 'block';
            newWindowBtn.style.display = 'block';
        }

        function addMessage(role, content) {
            var messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role + '-message';
            
            var roleLabel = role === 'user' ? 'You' : 'Project-0';
            var roleClass = role === 'user' ? 'user-role' : 'ai-role';
            
            messageDiv.innerHTML = 
                '<div class="message-header"><span class="message-role ' + roleClass + '">' + roleLabel + '</span></div>' +
                '<div class="message-content">' + escapeHtml(content) + '</div>';
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Refresh preview
        refreshBtn.addEventListener('click', function() {
            if (currentMvpId) {
                showPreview(currentMvpId);
            }
        });

        // Open in new window
        newWindowBtn.addEventListener('click', function() {
            if (currentMvpId) {
                window.open('/preview/' + currentMvpId, '_blank');
            }
        });

        // Focus input on load
        window.addEventListener('load', function() {
            ideaInput.focus();
        });
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║         🚀 PROJECT-0 - AI MVP GENERATOR 🚀           ║
    ║                                                       ║
    ║   Transform Ideas → Working Prototypes               ║
    ║   HTML + Tailwind CSS + React.js                     ║
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
