"""
Project-0: Professional AI MVP Platform
Generate full-stack production-ready MVPs with Node.js, Database, and Modern UI
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
import base64

app = FastAPI(title="Project-0", description="Professional AI MVP Platform")

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

# Enhanced System Prompt for Real MVP Generation
SYSTEM_PROMPT = """You are Project-0, a professional AI platform that creates REAL, PRODUCTION-READY MVPs.

Your task: Generate complete, working full-stack applications that can be deployed immediately.

## Architecture Requirements:

**Backend (Node.js):**
- Use Express.js framework
- Include proper routing
- Add middleware (cors, body-parser, etc.)
- Error handling and validation
- Environment variables (.env)
- Database connection and models
- API endpoints (REST)

**Database:**
- Use SQLite for simplicity (or MongoDB for complex apps)
- Include database schema
- Proper models/schemas
- Migration scripts if needed
- Seed data examples

**Frontend:**
- Modern HTML5
- Tailwind CSS for styling
- Vanilla JavaScript or React.js
- Responsive design
- Beautiful UI with proper color scheme
- Interactive components
- Form validation
- API integration

## Color Schemes (Choose one that fits):

**Professional Blue:**
- Primary: #2563eb (blue-600)
- Secondary: #3b82f6 (blue-500)
- Accent: #60a5fa (blue-400)
- Dark: #1e40af (blue-800)

**Success Green:**
- Primary: #10b981 (emerald-500)
- Secondary: #34d399 (emerald-400)
- Accent: #6ee7b7 (emerald-300)
- Dark: #059669 (emerald-600)

**Modern Purple:**
- Primary: #8b5cf6 (violet-500)
- Secondary: #a78bfa (violet-400)
- Accent: #c4b5fd (violet-300)
- Dark: #7c3aed (violet-600)

**Warm Orange:**
- Primary: #f59e0b (amber-500)
- Secondary: #fbbf24 (amber-400)
- Accent: #fcd34d (amber-300)
- Dark: #d97706 (amber-600)

## Response Format (STRICT):

Use markdown with code blocks for each file:

## 📋 Project Overview
[Brief description of the MVP and its purpose]

## 🎨 Color Scheme
**[Scheme Name]**
- Primary: [color] - [usage]
- Secondary: [color] - [usage]
- Accent: [color] - [usage]

## 🏗️ Architecture
- Backend: Node.js + Express.js
- Database: [SQLite/MongoDB]
- Frontend: [HTML + Tailwind + JS/React]

## ✨ Features
- [List all implemented features]

## 📁 Project Structure
```
project-name/
├── backend/
│   ├── server.js
│   ├── package.json
│   ├── .env
│   └── ...
├── frontend/
│   └── index.html
└── README.md
```

## 💻 Code

### Backend Files

#### `backend/package.json`
```json
[Complete package.json with all dependencies]
```

#### `backend/server.js`
```javascript
[Complete Express.js server with all routes, middleware, database connection]
```

#### `backend/.env.example`
```
[Environment variables template]
```

#### `backend/database.js` (or models.js)
```javascript
[Database connection and models]
```

### Frontend Files

#### `frontend/index.html`
```html
[Complete HTML with Tailwind CSS, proper structure, beautiful UI]
```

#### `frontend/app.js` (if separate)
```javascript
[Frontend JavaScript logic, API calls]
```

### Documentation

#### `README.md`
```markdown
[Complete setup and deployment instructions]
```

## 🚀 Setup Instructions
[Step-by-step guide to run the project]

## 🎯 API Endpoints
[List all API routes with examples]

## 💾 Database Schema
[Explain database structure]

IMPORTANT RULES:
1. Generate COMPLETE, WORKING code - no placeholders
2. Use modern best practices
3. Include proper error handling
4. Make it production-ready
5. Use consistent color scheme throughout
6. Add beautiful UI with gradients, shadows, animations
7. Make it fully responsive
8. Include all necessary dependencies
9. Add helpful comments
10. Provide complete setup instructions"""

class ChatMessage(BaseModel):
    role: str
    content: str

class GenerateRequest(BaseModel):
    idea: str

# Store generated MVPs
generated_mvps: Dict[str, Dict] = {}

async def generate_mvp(idea: str) -> AsyncGenerator[str, None]:
    """Generate real MVP with backend and frontend"""
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a complete, production-ready MVP for: {idea}\n\nGenerate ALL files including backend (Node.js + Express), database setup, and frontend. Make it beautiful and fully functional."}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 Analyzing your idea...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '🏗️ Designing architecture...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '⚡ Generating backend (Node.js + Express)...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '🎨 Creating beautiful UI...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '💾 Setting up database...'})}\n\n"
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
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_ctx": 16384,  # Larger context for more files
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
                                # Extract files from response
                                files = extract_project_files(full_response)
                                mvp_id = str(int(time.time()))
                                
                                generated_mvps[mvp_id] = {
                                    "idea": idea,
                                    "files": files,
                                    "markdown": full_response,
                                    "timestamp": datetime.now().isoformat()
                                }
                                
                                yield f"data: {json.dumps({'type': 'done', 'mvp_id': mvp_id, 'file_count': len(files)})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

def extract_project_files(markdown_text: str) -> Dict[str, str]:
    """Extract all project files from markdown response"""
    files = {}
    
    # Pattern to match code blocks with filenames
    # Matches: #### `filename.ext` followed by ```language\ncode\n```
    pattern = r'####\s+`([^`]+)`\s*\n```(\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    
    for filename, language, code in matches:
        files[filename] = code.strip()
    
    # Also try simpler pattern
    if not files:
        pattern = r'```(\w+):([^\n]+)\n(.*?)\n```'
        matches = re.findall(pattern, markdown_text, re.DOTALL)
        for language, filename, code in matches:
            files[filename.strip()] = code.strip()
    
    return files

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application UI"""
    return HTML_TEMPLATE

@app.post("/api/generate")
async def generate(request: GenerateRequest):
    """Generate MVP from idea with streaming"""
    return StreamingResponse(
        generate_mvp(request.idea),
        media_type="text/event-stream"
    )

@app.get("/api/mvp/{mvp_id}")
async def get_mvp(mvp_id: str):
    """Get MVP details"""
    if mvp_id not in generated_mvps:
        return JSONResponse({"error": "MVP not found"}, status_code=404)
    
    mvp = generated_mvps[mvp_id]
    return JSONResponse({
        "files": mvp["files"],
        "markdown": mvp["markdown"],
        "idea": mvp["idea"],
        "timestamp": mvp["timestamp"]
    })

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "generated_mvps": len(generated_mvps)
    }

# Enhanced HTML Template with Professional UI
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Professional AI MVP Platform</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #000000;
            --bg-secondary: #0a0a0a;
            --bg-tertiary: #1a1a1a;
            --border-color: #2a2a2a;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --text-tertiary: #666666;
            
            /* Professional Blue Theme */
            --accent-primary: #2563eb;
            --accent-secondary: #3b82f6;
            --accent-light: #60a5fa;
            --accent-dark: #1e40af;
            
            /* Success colors */
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            line-height: 1.6;
        }

        .container {
            display: flex;
            height: 100vh;
        }

        /* Chat Panel */
        .chat-panel {
            width: 50%;
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-color);
            background: var(--bg-primary);
        }

        /* Preview Panel */
        .preview-panel {
            width: 50%;
            display: flex;
            flex-direction: column;
            background: var(--bg-secondary);
        }

        /* Header */
        .header {
            background: var(--bg-primary);
            border-bottom: 1px solid var(--border-color);
            padding: 20px 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 20px;
            color: white;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .logo-text {
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
            box-shadow: 0 0 8px var(--success);
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.6; transform: scale(0.9); }
        }

        /* Messages Area */
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 28px;
        }

        .message {
            margin-bottom: 28px;
            animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(16px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }

        .message-role {
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }

        .user-role { color: var(--text-primary); }
        .ai-role { color: var(--accent-secondary); }

        .message-content {
            padding: 18px 20px;
            border-radius: 14px;
            line-height: 1.7;
            font-size: 14px;
        }

        .user-message .message-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
        }

        .ai-message .message-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            font-size: 13px;
            color: var(--text-secondary);
            margin-bottom: 14px;
            font-weight: 500;
        }

        /* Enhanced Markdown Styles */
        .markdown-content {
            color: var(--text-primary);
        }

        .markdown-content h2 {
            font-size: 20px;
            font-weight: 700;
            margin: 24px 0 14px 0;
            color: var(--text-primary);
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border-color);
        }

        .markdown-content h3 {
            font-size: 17px;
            font-weight: 600;
            margin: 20px 0 10px 0;
            color: var(--text-secondary);
        }

        .markdown-content h4 {
            font-size: 15px;
            font-weight: 600;
            margin: 16px 0 8px 0;
            color: var(--accent-secondary);
        }

        .markdown-content p {
            margin: 10px 0;
            color: var(--text-secondary);
        }

        .markdown-content ul, .markdown-content ol {
            margin: 12px 0 12px 24px;
        }

        .markdown-content li {
            margin: 6px 0;
            color: var(--text-secondary);
        }

        .markdown-content code {
            background: var(--bg-tertiary);
            padding: 3px 8px;
            border-radius: 5px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            color: var(--accent-light);
            border: 1px solid var(--border-color);
        }

        .markdown-content pre {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 18px;
            overflow-x: auto;
            margin: 16px 0;
        }

        .markdown-content pre code {
            background: none;
            padding: 0;
            border: none;
            color: var(--text-secondary);
            font-size: 13px;
            line-height: 1.6;
        }

        .markdown-content strong {
            color: var(--text-primary);
            font-weight: 600;
        }

        .markdown-content blockquote {
            border-left: 3px solid var(--accent-primary);
            padding-left: 16px;
            margin: 16px 0;
            color: var(--text-secondary);
            font-style: italic;
        }

        /* Action Buttons */
        .action-button {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-top: 14px;
            padding: 12px 20px;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .action-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
        }

        /* Input Area */
        .input-area {
            padding: 28px;
            background: var(--bg-primary);
            border-top: 1px solid var(--border-color);
        }

        .input-wrapper {
            position: relative;
        }

        #ideaInput {
            width: 100%;
            padding: 18px 70px 18px 20px;
            background: var(--bg-tertiary);
            border: 2px solid var(--border-color);
            border-radius: 14px;
            color: var(--text-primary);
            font-size: 15px;
            font-family: inherit;
            resize: none;
            outline: none;
            min-height: 90px;
            max-height: 220px;
            transition: all 0.3s;
            font-weight: 400;
        }

        #ideaInput:focus {
            border-color: var(--accent-primary);
            background: var(--bg-secondary);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        #ideaInput::placeholder {
            color: var(--text-tertiary);
        }

        #generateBtn {
            position: absolute;
            right: 14px;
            bottom: 14px;
            width: 46px;
            height: 46px;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            color: white;
            border: none;
            border-radius: 11px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        #generateBtn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
        }

        #generateBtn:disabled {
            background: var(--bg-tertiary);
            cursor: not-allowed;
            box-shadow: none;
        }

        /* Preview Panel */
        .preview-header {
            padding: 20px 28px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .preview-title {
            font-size: 17px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .preview-actions {
            display: flex;
            gap: 10px;
        }

        .preview-btn {
            padding: 10px 18px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .preview-btn:hover {
            background: var(--bg-primary);
            border-color: var(--accent-primary);
        }

        .preview-content {
            flex: 1;
            overflow-y: auto;
            padding: 28px;
        }

        .preview-placeholder {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-tertiary);
            text-align: center;
            padding: 48px;
        }

        .placeholder-icon {
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 48px;
            margin-bottom: 24px;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
        }

        .placeholder-text {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 10px;
            color: var(--text-primary);
        }

        .placeholder-hint {
            font-size: 15px;
            color: var(--text-secondary);
        }

        /* Welcome Screen */
        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            padding: 48px;
            text-align: center;
        }

        .welcome-logo {
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
            border-radius: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 48px;
            color: white;
            margin-bottom: 28px;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
        }

        .welcome-title {
            font-size: 32px;
            font-weight: 800;
            margin-bottom: 14px;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .welcome-subtitle {
            font-size: 17px;
            color: var(--text-secondary);
            margin-bottom: 40px;
            max-width: 480px;
            line-height: 1.7;
        }

        .example-ideas {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 14px;
            max-width: 600px;
            width: 100%;
        }

        .example-idea {
            padding: 18px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            text-align: left;
        }

        .example-idea:hover {
            background: var(--bg-secondary);
            border-color: var(--accent-primary);
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
        }

        .example-title {
            font-weight: 600;
            margin-bottom: 6px;
            font-size: 14px;
            color: var(--text-primary);
        }

        .example-desc {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* File View */
        .file-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .file-item {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
        }

        .file-header {
            padding: 14px 18px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
        }

        .file-name {
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
            font-family: 'Monaco', monospace;
        }

        .file-toggle {
            color: var(--text-tertiary);
            font-size: 18px;
        }

        .file-content {
            padding: 0;
            max-height: 400px;
            overflow: auto;
        }

        .file-content pre {
            margin: 0;
            border-radius: 0;
            border: none;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 5px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-tertiary);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Chat Panel -->
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
                    <div class="welcome-title">Professional AI MVP Platform</div>
                    <div class="welcome-subtitle">
                        Generate production-ready full-stack applications with Node.js backend, database, and beautiful UI
                    </div>
                    <div class="example-ideas">
                        <div class="example-idea" data-idea="Create a task management platform with user authentication, SQLite database, and real-time updates">
                            <div class="example-title">📋 Task Manager</div>
                            <div class="example-desc">Full CRUD with auth</div>
                        </div>
                        <div class="example-idea" data-idea="Build a blog platform with user accounts, post creation, comments, and categories using MongoDB">
                            <div class="example-title">📝 Blog Platform</div>
                            <div class="example-desc">Multi-user blogging</div>
                        </div>
                        <div class="example-idea" data-idea="Design an e-commerce product catalog with shopping cart, checkout, and order management">
                            <div class="example-title">🛍️ E-commerce</div>
                            <div class="example-desc">Shop with cart</div>
                        </div>
                        <div class="example-idea" data-idea="Create a real-time chat application with WebSocket support and message history">
                            <div class="example-title">💬 Chat App</div>
                            <div class="example-desc">Real-time messaging</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="input-area">
                <div class="input-wrapper">
                    <textarea 
                        id="ideaInput" 
                        placeholder="Describe your MVP idea in detail... AI will generate complete backend + frontend + database!"
                    ></textarea>
                    <button id="generateBtn">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- Preview Panel -->
        <div class="preview-panel">
            <div class="preview-header">
                <div class="preview-title">Project Files</div>
                <div class="preview-actions">
                    <button class="preview-btn" id="downloadBtn" style="display:none;">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                        </svg>
                        Download All
                    </button>
                </div>
            </div>
            <div class="preview-content" id="previewContent">
                <div class="preview-placeholder">
                    <div class="placeholder-icon">✨</div>
                    <div class="placeholder-text">Ready to Build</div>
                    <div class="placeholder-hint">Describe your idea to generate a complete MVP</div>
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
        var previewContent = document.getElementById('previewContent');
        var downloadBtn = document.getElementById('downloadBtn');

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
            this.style.height = Math.min(this.scrollHeight, 220) + 'px';
        });

        // Generate button click
        generateBtn.addEventListener('click', generate);

        // Enter to generate
        ideaInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
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
                                        if (data.file_count > 0) {
                                            showFiles(data.mvp_id);
                                            downloadBtn.style.display = 'flex';
                                        }
                                    } 
                                    else if (data.type === 'error') {
                                        var responseDiv = document.getElementById('currentResponse');
                                        responseDiv.innerHTML = '<span style="color: var(--error);">' + data.content + '</span>';
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

        function showFiles(mvpId) {
            fetch('/api/mvp/' + mvpId)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                var files = data.files;
                var html = '<div class="file-list">';
                
                for (var filename in files) {
                    var content = files[filename];
                    html += '<div class="file-item">' +
                        '<div class="file-header" onclick="toggleFile(this)">' +
                            '<span class="file-name">' + filename + '</span>' +
                            '<span class="file-toggle">▼</span>' +
                        '</div>' +
                        '<div class="file-content" style="display:none;">' +
                            '<pre><code>' + escapeHtml(content) + '</code></pre>' +
                        '</div>' +
                    '</div>';
                }
                
                html += '</div>';
                previewContent.innerHTML = html;
            });
        }

        function toggleFile(header) {
            var content = header.nextElementSibling;
            var toggle = header.querySelector('.file-toggle');
            
            if (content.style.display === 'none') {
                content.style.display = 'block';
                toggle.textContent = '▲';
            } else {
                content.style.display = 'none';
                toggle.textContent = '▼';
            }
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

        // Download all files
        downloadBtn.addEventListener('click', function() {
            if (currentMvpId) {
                fetch('/api/mvp/' + currentMvpId)
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    // Create a simple text file with all code
                    var content = '# Project Files\\n\\n';
                    for (var filename in data.files) {
                        content += '## ' + filename + '\\n```\\n' + data.files[filename] + '\\n```\\n\\n';
                    }
                    
                    var blob = new Blob([content], {type: 'text/plain'});
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = 'project-files.txt';
                    a.click();
                });
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
    ║      🚀 PROJECT-0 PROFESSIONAL MVP PLATFORM 🚀       ║
    ║                                                       ║
    ║   Generate Real MVPs with:                           ║
    ║   • Node.js + Express Backend                        ║
    ║   • SQLite/MongoDB Database                          ║
    ║   • Modern UI with Official Colors                   ║
    ║   • Production-Ready Code                            ║
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
