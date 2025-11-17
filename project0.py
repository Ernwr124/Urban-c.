"""
Project-0: Professional AI MVP Platform
Complete Full-Stack Application Generator with Authentication & Dashboard
Powered by Ollama GLM-4.6:cloud
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import AsyncGenerator, List, Dict, Optional
import time
from datetime import datetime
import re
import sqlite3
import hashlib
import secrets
import io
import zipfile
import os

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
DB_FILE = "project0.db"

# Initialize Database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Projects table
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        context TEXT,
        files TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    # Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    conn.commit()
    conn.close()

init_db()

# Models
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ProjectCreate(BaseModel):
    name: str
    description: str

class ChatRequest(BaseModel):
    project_id: int
    message: str

# Helper functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[int]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# Enhanced System Prompt for Project Context
def get_system_prompt(project_context: str = "") -> str:
    base_prompt = """You are Project-0 AI, a professional full-stack development assistant.

Your capabilities:
- Generate production-ready Node.js backends with Express
- Create modern frontends with HTML, Tailwind CSS, and JavaScript/React
- Design and implement databases (SQLite/MongoDB)
- Write clean, documented, and tested code
- Follow best practices and security standards
- Provide complete project files ready for deployment

Architecture Standards:
**Backend (Node.js + Express):**
- RESTful API design
- Proper error handling and validation
- CORS and security middleware
- Environment variable configuration
- Database models and migrations

**Database:**
- Normalized schema design
- Proper indexing
- Connection pooling
- CRUD operations

**Frontend:**
- Responsive design (mobile-first)
- Modern UI with Tailwind CSS
- API integration
- Form validation
- Loading states and error handling

**Code Quality:**
- Clear variable/function names
- Comprehensive comments
- Error boundaries
- Input sanitization
- Security best practices

Color Schemes (choose appropriate):
- Professional Blue: #2563eb, #3b82f6, #60a5fa
- Success Green: #10b981, #34d399, #6ee7b7
- Modern Purple: #8b5cf6, #a78bfa, #c4b5fd
- Warm Orange: #f59e0b, #fbbf24, #fcd34d

Response Format:
Generate ALL files with proper structure:

## 📋 Project Overview
[Brief description]

## 🏗️ Architecture
- Backend: Node.js + Express
- Database: [SQLite/MongoDB]
- Frontend: HTML + Tailwind + JS

## 📁 Files

### backend/package.json
```json
[Complete package.json]
```

### backend/server.js
```javascript
[Complete Express server]
```

### backend/database.js
```javascript
[Database setup]
```

### backend/.env.example
```
[Environment variables]
```

### frontend/index.html
```html
[Complete frontend]
```

### README.md
```markdown
[Setup instructions]
```

### start.sh
```bash
#!/bin/bash
cd backend && npm install && npm start
```

IMPORTANT:
- Generate COMPLETE, WORKING code
- No placeholders or TODOs
- Production-ready quality
- All files must work together
- Include error handling
- Add security measures"""

    if project_context:
        base_prompt += f"\n\nPROJECT CONTEXT:\n{project_context}\n\nIMPORTANT: Remember this context for all subsequent requests about this project. Build upon previous work."
    
    return base_prompt

# API Endpoints

@app.post("/api/register")
async def register(req: RegisterRequest):
    """Register new user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    try:
        password_hash = hash_password(req.password)
        c.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                 (req.name, req.email, password_hash))
        conn.commit()
        user_id = c.lastrowid
        token = create_session(user_id)
        
        return {"success": True, "token": token, "user": {"id": user_id, "name": req.name, "email": req.email}}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@app.post("/api/login")
async def login(req: LoginRequest):
    """Login user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    password_hash = hash_password(req.password)
    c.execute("SELECT id, name, email FROM users WHERE email = ? AND password_hash = ?",
             (req.email, password_hash))
    user = c.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_session(user[0])
    return {"success": True, "token": token, "user": {"id": user[0], "name": user[1], "email": user[2]}}

@app.get("/api/projects")
async def get_projects(token: str):
    """Get user projects"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, description, created_at, updated_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
             (user_id,))
    projects = [{"id": row[0], "name": row[1], "description": row[2], "created_at": row[3], "updated_at": row[4]} 
                for row in c.fetchall()]
    conn.close()
    
    return {"projects": projects}

@app.post("/api/projects")
async def create_project(req: ProjectCreate, token: str):
    """Create new project"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO projects (user_id, name, description, context) VALUES (?, ?, ?, ?)",
             (user_id, req.name, req.description, ""))
    conn.commit()
    project_id = c.lastrowid
    conn.close()
    
    return {"success": True, "project_id": project_id}

@app.get("/api/project/{project_id}")
async def get_project(project_id: int, token: str):
    """Get project details"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, description, context, files FROM projects WHERE id = ? AND user_id = ?",
             (project_id, user_id))
    project = c.fetchone()
    conn.close()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    files = json.loads(project[4]) if project[4] else {}
    return {
        "id": project[0],
        "name": project[1],
        "description": project[2],
        "context": project[3],
        "files": files
    }

@app.post("/api/chat")
async def chat(req: ChatRequest, token: str):
    """Chat with AI about project"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Get project context
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT context, description FROM projects WHERE id = ? AND user_id = ?",
             (req.project_id, user_id))
    project = c.fetchone()
    conn.close()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_context = f"Project Description: {project[1]}\n\nPrevious Context: {project[0]}"
    
    return StreamingResponse(
        generate_mvp_stream(req.message, req.project_id, user_id, project_context),
        media_type="text/event-stream"
    )

async def generate_mvp_stream(message: str, project_id: int, user_id: int, context: str) -> AsyncGenerator[str, None]:
    """Generate MVP with streaming and context"""
    
    system_prompt = get_system_prompt(context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 Analyzing request...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '🏗️ Designing architecture...'})}\n\n"
            await asyncio.sleep(0.5)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '⚡ Generating code...'})}\n\n"
            await asyncio.sleep(0.5)
            
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
                        "num_ctx": 16384,
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
                                # Extract files and update project
                                files = extract_project_files(full_response)
                                
                                # Update project context and files
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                new_context = context + f"\n\nUser: {message}\nAI: Generated files successfully."
                                c.execute("UPDATE projects SET context = ?, files = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                         (new_context, json.dumps(files), project_id))
                                conn.commit()
                                conn.close()
                                
                                yield f"data: {json.dumps({'type': 'done', 'files': files, 'file_count': len(files)})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
    
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

def extract_project_files(markdown_text: str) -> Dict[str, str]:
    """Extract all files from markdown"""
    files = {}
    
    # Pattern: ### filename\n```language\ncode\n```
    pattern = r'###\s+([^\n]+)\s*\n```(?:\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    
    for filename, code in matches:
        filename = filename.strip()
        files[filename] = code.strip()
    
    # Add start script
    files["start.sh"] = "#!/bin/bash\ncd backend\nnpm install\nnpm start"
    files["start.bat"] = "@echo off\ncd backend\nnpm install\nnpm start"
    
    return files

@app.get("/api/download/{project_id}")
async def download_project(project_id: int, token: str):
    """Download project as ZIP"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Get project
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, files FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    project = c.fetchone()
    conn.close()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    files = json.loads(project[1]) if project[1] else {}
    
    # Create ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project[0]}.zip"}
    )

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main application"""
    return HTML_TEMPLATE

@app.get("/api/health")
async def health():
    """Health check"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Main HTML Template with Landing, Auth, Dashboard, and Chat
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Professional AI MVP Platform</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
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
            --accent-primary: #2563eb;
            --accent-secondary: #3b82f6;
            --accent-light: #60a5fa;
            --success: #10b981;
            --warning: #f59e0b;
            --error: #ef4444;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
        }

        /* Hide all pages by default */
        .page {
            display: none;
        }

        .page.active {
            display: block;
        }

        /* Landing Page */
        .landing {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .landing-nav {
            padding: 24px 48px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .logo {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 28px;
            color: white;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.3);
        }

        .logo-text {
            font-size: 28px;
            font-weight: 800;
            background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .nav-actions button {
            padding: 12px 28px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 15px;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }

        .nav-actions button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
        }

        .landing-hero {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 80px 48px;
            text-align: center;
        }

        .hero-title {
            font-size: 72px;
            font-weight: 900;
            margin-bottom: 24px;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--accent-primary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1.1;
        }

        .hero-subtitle {
            font-size: 24px;
            color: var(--text-secondary);
            margin-bottom: 48px;
            max-width: 700px;
            font-weight: 400;
        }

        .hero-cta {
            padding: 18px 48px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4);
        }

        .hero-cta:hover {
            transform: translateY(-3px);
            box-shadow: 0 12px 32px rgba(37, 99, 235, 0.5);
        }

        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 32px;
            max-width: 1200px;
            margin-top: 80px;
        }

        .feature-card {
            padding: 32px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            transition: all 0.3s;
        }

        .feature-card:hover {
            transform: translateY(-4px);
            border-color: var(--accent-primary);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
        }

        .feature-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        .feature-title {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 12px;
        }

        .feature-desc {
            color: var(--text-secondary);
            font-size: 15px;
        }

        /* Auth Page */
        .auth-container {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 48px;
        }

        .auth-box {
            width: 100%;
            max-width: 450px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 48px;
        }

        .auth-title {
            font-size: 32px;
            font-weight: 800;
            margin-bottom: 32px;
            text-align: center;
        }

        .form-group {
            margin-bottom: 24px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            font-size: 14px;
            color: var(--text-secondary);
        }

        .form-input {
            width: 100%;
            padding: 14px 18px;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            border-radius: 10px;
            color: var(--text-primary);
            font-size: 15px;
            font-family: inherit;
            transition: all 0.3s;
        }

        .form-input:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        .auth-button {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 8px;
        }

        .auth-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
        }

        .auth-switch {
            text-align: center;
            margin-top: 24px;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .auth-switch a {
            color: var(--accent-primary);
            text-decoration: none;
            font-weight: 600;
            cursor: pointer;
        }

        /* Dashboard */
        .dashboard {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .dashboard-nav {
            padding: 20px 48px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .user-info {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .user-avatar {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 18px;
        }

        .dashboard-content {
            flex: 1;
            padding: 48px;
        }

        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 48px;
        }

        .dashboard-title {
            font-size: 42px;
            font-weight: 800;
        }

        .create-project-btn {
            padding: 14px 32px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .projects-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 24px;
        }

        .project-card {
            padding: 28px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .project-card:hover {
            transform: translateY(-4px);
            border-color: var(--accent-primary);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
        }

        .project-name {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 12px;
        }

        .project-desc {
            color: var(--text-secondary);
            font-size: 14px;
            margin-bottom: 16px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .project-date {
            font-size: 12px;
            color: var(--text-tertiary);
        }

        /* Chat Interface */
        .chat-container {
            display: flex;
            height: 100vh;
        }

        .chat-sidebar {
            width: 280px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
        }

        .chat-sidebar-header {
            padding: 20px;
            border-bottom: 1px solid var(--border-color);
        }

        .back-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.2s;
        }

        .back-btn:hover {
            background: var(--bg-primary);
        }

        .chat-main {
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .chat-header {
            padding: 20px 32px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 32px;
        }

        .message {
            margin-bottom: 28px;
            animation: slideIn 0.4s ease-out;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(16px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }

        .message-role {
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }

        .user-role { color: var(--text-primary); }
        .ai-role { color: var(--accent-secondary); }

        .message-content {
            padding: 20px;
            border-radius: 14px;
            line-height: 1.7;
            font-size: 15px;
        }

        .user-message .message-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
        }

        .ai-message .message-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
        }

        .chat-input-area {
            padding: 32px;
            border-top: 1px solid var(--border-color);
        }

        .chat-input-wrapper {
            position: relative;
        }

        #chatInput {
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
        }

        #chatInput:focus {
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
        }

        #sendBtn {
            position: absolute;
            right: 14px;
            bottom: 14px;
            width: 46px;
            height: 46px;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            color: white;
            border: none;
            border-radius: 11px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s;
        }

        .chat-preview {
            width: 45%;
            background: var(--bg-secondary);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
        }

        .preview-header {
            padding: 20px 28px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .preview-content {
            flex: 1;
            overflow: auto;
            padding: 28px;
        }

        .preview-frame {
            width: 100%;
            height: 100%;
            border: none;
            border-radius: 12px;
            background: white;
        }

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
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }

        .file-name {
            font-weight: 600;
            font-size: 14px;
            font-family: 'Monaco', monospace;
        }

        .file-content {
            padding: 0;
            max-height: 400px;
            overflow: auto;
            display: none;
        }

        .file-content.expanded {
            display: block;
        }

        .file-content pre {
            margin: 0;
            padding: 18px;
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-size: 13px;
            line-height: 1.6;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 90%;
        }

        .modal-title {
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 24px;
        }

        .btn-secondary {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            padding: 12px 24px;
            border-radius: 10px;
            color: var(--text-primary);
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-secondary:hover {
            background: var(--bg-primary);
        }

        .download-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: linear-gradient(135deg, var(--success), #34d399);
            color: white;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }

        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
        }

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
    <!-- Landing Page -->
    <div id="landingPage" class="page active landing">
        <nav class="landing-nav">
            <div class="logo-container">
                <div class="logo">P</div>
                <div class="logo-text">Project-0</div>
            </div>
            <div class="nav-actions">
                <button onclick="showPage('authPage')">Try It Now</button>
            </div>
        </nav>
        <div class="landing-hero">
            <h1 class="hero-title">Build MVPs in Minutes</h1>
            <p class="hero-subtitle">
                Transform your ideas into production-ready applications with intelligent code generation.
                Full-stack, database-integrated, deployment-ready.
            </p>
            <button class="hero-cta" onclick="showPage('authPage')">Get Started</button>
            
            <div class="features">
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <div class="feature-title">Lightning Fast</div>
                    <div class="feature-desc">Generate complete MVPs in minutes, not days</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🏗️</div>
                    <div class="feature-title">Full-Stack Ready</div>
                    <div class="feature-desc">Backend, frontend, and database included</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🎨</div>
                    <div class="feature-title">Beautiful UI</div>
                    <div class="feature-desc">Modern, responsive designs that look professional</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🔐</div>
                    <div class="feature-title">Production Ready</div>
                    <div class="feature-desc">Security, error handling, and best practices built-in</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Auth Page -->
    <div id="authPage" class="page">
        <div class="auth-container">
            <div class="auth-box">
                <div class="logo-container" style="justify-content: center; margin-bottom: 32px;">
                    <div class="logo">P</div>
                    <div class="logo-text">Project-0</div>
                </div>
                
                <!-- Login Form -->
                <div id="loginForm">
                    <h2 class="auth-title">Welcome Back</h2>
                    <form onsubmit="handleLogin(event)">
                        <div class="form-group">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-input" required id="loginEmail">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Password</label>
                            <input type="password" class="form-input" required id="loginPassword">
                        </div>
                        <button type="submit" class="auth-button">Sign In</button>
                    </form>
                    <div class="auth-switch">
                        Don't have an account? <a onclick="toggleAuth()">Sign up</a>
                    </div>
                </div>

                <!-- Register Form -->
                <div id="registerForm" style="display:none;">
                    <h2 class="auth-title">Create Account</h2>
                    <form onsubmit="handleRegister(event)">
                        <div class="form-group">
                            <label class="form-label">Name</label>
                            <input type="text" class="form-input" required id="registerName">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Email</label>
                            <input type="email" class="form-input" required id="registerEmail">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Password</label>
                            <input type="password" class="form-input" required id="registerPassword">
                        </div>
                        <button type="submit" class="auth-button">Create Account</button>
                    </form>
                    <div class="auth-switch">
                        Already have an account? <a onclick="toggleAuth()">Sign in</a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Dashboard Page -->
    <div id="dashboardPage" class="page dashboard">
        <nav class="dashboard-nav">
            <div class="logo-container">
                <div class="logo">P</div>
                <div class="logo-text">Project-0</div>
            </div>
            <div class="user-info">
                <span id="userName"></span>
                <div class="user-avatar" id="userAvatar"></div>
                <button class="btn-secondary" onclick="logout()">Logout</button>
            </div>
        </nav>
        <div class="dashboard-content">
            <div class="dashboard-header">
                <h1 class="dashboard-title">Your Projects</h1>
                <button class="create-project-btn" onclick="showCreateModal()">
                    <span>+</span> New Project
                </button>
            </div>
            <div class="projects-grid" id="projectsGrid"></div>
        </div>
    </div>

    <!-- Chat Page -->
    <div id="chatPage" class="page">
        <div class="chat-container">
            <div class="chat-sidebar">
                <div class="chat-sidebar-header">
                    <button class="back-btn" onclick="showPage('dashboardPage'); loadProjects();">
                        ← Back to Projects
                    </button>
                </div>
            </div>
            <div class="chat-main">
                <div class="chat-header">
                    <h2 id="chatProjectName"></h2>
                    <button class="download-btn" id="downloadBtn" onclick="downloadProject()" style="display:none;">
                        ↓ Download ZIP
                    </button>
                </div>
                <div class="chat-messages" id="chatMessages"></div>
                <div class="chat-input-area">
                    <div class="chat-input-wrapper">
                        <textarea id="chatInput" placeholder="Describe what you want to build or modify..."></textarea>
                        <button id="sendBtn" onclick="sendMessage()">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
            <div class="chat-preview">
                <div class="preview-header">
                    <h3>Live Preview</h3>
                </div>
                <div class="preview-content" id="previewContent">
                    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);">
                        <div style="font-size:48px;margin-bottom:16px;">✨</div>
                        <div style="font-size:18px;font-weight:600;">Ready to Build</div>
                        <div style="font-size:14px;margin-top:8px;">Your preview will appear here</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Create Project Modal -->
    <div id="createModal" class="modal">
        <div class="modal-content">
            <h2 class="modal-title">Create New Project</h2>
            <form onsubmit="createProject(event)">
                <div class="form-group">
                    <label class="form-label">Project Name</label>
                    <input type="text" class="form-input" required id="projectName">
                </div>
                <div class="form-group">
                    <label class="form-label">Description / Requirements</label>
                    <textarea class="form-input" required id="projectDesc" style="min-height:120px;resize:vertical;"></textarea>
                </div>
                <div style="display:flex;gap:12px;margin-top:24px;">
                    <button type="submit" class="auth-button">Create Project</button>
                    <button type="button" class="btn-secondary" onclick="closeModal()">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        // Global state
        let currentUser = null;
        let currentToken = null;
        let currentProject = null;
        let projectFiles = {};

        // Load state from localStorage
        function loadState() {
            const token = localStorage.getItem('token');
            const user = localStorage.getItem('user');
            if (token && user) {
                currentToken = token;
                currentUser = JSON.parse(user);
                showPage('dashboardPage');
                loadProjects();
            }
        }

        // Page navigation
        function showPage(pageId) {
            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.getElementById(pageId).classList.add('active');
            
            if (pageId === 'dashboardPage' && currentUser) {
                document.getElementById('userName').textContent = currentUser.name;
                document.getElementById('userAvatar').textContent = currentUser.name[0].toUpperCase();
            }
        }

        // Auth functions
        function toggleAuth() {
            const login = document.getElementById('loginForm');
            const register = document.getElementById('registerForm');
            if (login.style.display === 'none') {
                login.style.display = 'block';
                register.style.display = 'none';
            } else {
                login.style.display = 'none';
                register.style.display = 'block';
            }
        }

        async function handleLogin(e) {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, password})
                });
                
                const data = await response.json();
                if (data.success) {
                    currentToken = data.token;
                    currentUser = data.user;
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    showPage('dashboardPage');
                    loadProjects();
                } else {
                    alert('Invalid credentials');
                }
            } catch (error) {
                alert('Login failed: ' + error.message);
            }
        }

        async function handleRegister(e) {
            e.preventDefault();
            const name = document.getElementById('registerName').value;
            const email = document.getElementById('registerEmail').value;
            const password = document.getElementById('registerPassword').value;
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, email, password})
                });
                
                const data = await response.json();
                if (data.success) {
                    currentToken = data.token;
                    currentUser = data.user;
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    showPage('dashboardPage');
                    loadProjects();
                } else {
                    alert('Registration failed');
                }
            } catch (error) {
                alert('Registration failed: ' + error.message);
            }
        }

        function logout() {
            currentToken = null;
            currentUser = null;
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            showPage('landingPage');
        }

        // Projects
        async function loadProjects() {
            try {
                const response = await fetch('/api/projects?token=' + currentToken);
                const data = await response.json();
                
                const grid = document.getElementById('projectsGrid');
                grid.innerHTML = data.projects.map(p => `
                    <div class="project-card" onclick="openProject(${p.id}, '${p.name}')">
                        <div class="project-name">${p.name}</div>
                        <div class="project-desc">${p.description}</div>
                        <div class="project-date">Created ${new Date(p.created_at).toLocaleDateString()}</div>
                    </div>
                `).join('');
            } catch (error) {
                console.error('Failed to load projects:', error);
            }
        }

        function showCreateModal() {
            document.getElementById('createModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('createModal').classList.remove('active');
        }

        async function createProject(e) {
            e.preventDefault();
            const name = document.getElementById('projectName').value;
            const description = document.getElementById('projectDesc').value;
            
            try {
                const response = await fetch('/api/projects?token=' + currentToken, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, description})
                });
                
                const data = await response.json();
                if (data.success) {
                    closeModal();
                    openProject(data.project_id, name);
                }
            } catch (error) {
                alert('Failed to create project: ' + error.message);
            }
        }

        async function openProject(projectId, projectName) {
            currentProject = projectId;
            document.getElementById('chatProjectName').textContent = projectName;
            showPage('chatPage');
            
            // Load project details
            try {
                const response = await fetch('/api/project/' + projectId + '?token=' + currentToken);
                const data = await response.json();
                projectFiles = data.files || {};
                
                if (Object.keys(projectFiles).length > 0) {
                    showFiles(projectFiles);
                    document.getElementById('downloadBtn').style.display = 'flex';
                }
            } catch (error) {
                console.error('Failed to load project:', error);
            }
        }

        // Chat
        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            // Add user message
            addMessage('user', message);
            input.value = '';
            
            // Add AI message container
            const messagesDiv = document.getElementById('chatMessages');
            const aiDiv = document.createElement('div');
            aiDiv.className = 'message ai-message';
            aiDiv.innerHTML = '<div class="message-header"><span class="message-role ai-role">Project-0 AI</span></div><div class="message-content" id="currentResponse"></div>';
            messagesDiv.appendChild(aiDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            try {
                const response = await fetch('/api/chat?token=' + currentToken, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({project_id: currentProject, message: message})
                });
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.type === 'content') {
                                fullResponse += data.content;
                                document.getElementById('currentResponse').innerHTML = marked.parse(fullResponse);
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                            } else if (data.type === 'done') {
                                projectFiles = data.files;
                                showFiles(data.files);
                                document.getElementById('downloadBtn').style.display = 'flex';
                            }
                        }
                    }
                }
            } catch (error) {
                console.error('Chat error:', error);
            }
        }

        function addMessage(role, content) {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role + '-message';
            messageDiv.innerHTML = `
                <div class="message-header">
                    <span class="message-role ${role}-role">${role === 'user' ? 'You' : 'Project-0 AI'}</span>
                </div>
                <div class="message-content">${escapeHtml(content)}</div>
            `;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function showFiles(files) {
            const preview = document.getElementById('previewContent');
            
            // Check if there's an index.html to show
            if (files['frontend/index.html']) {
                const iframe = document.createElement('iframe');
                iframe.className = 'preview-frame';
                iframe.srcdoc = files['frontend/index.html'];
                preview.innerHTML = '';
                preview.appendChild(iframe);
            } else {
                // Show file list
                let html = '<div class="file-list">';
                for (const [filename, content] of Object.entries(files)) {
                    html += `
                        <div class="file-item">
                            <div class="file-header" onclick="toggleFile(this)">
                                <span class="file-name">${filename}</span>
                                <span>▼</span>
                            </div>
                            <div class="file-content">
                                <pre><code>${escapeHtml(content)}</code></pre>
                            </div>
                        </div>
                    `;
                }
                html += '</div>';
                preview.innerHTML = html;
            }
        }

        function toggleFile(header) {
            const content = header.nextElementSibling;
            content.classList.toggle('expanded');
            header.querySelector('span:last-child').textContent = content.classList.contains('expanded') ? '▲' : '▼';
        }

        async function downloadProject() {
            window.location.href = '/api/download/' + currentProject + '?token=' + currentToken;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Initialize
        loadState();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║      🚀 PROJECT-0 PROFESSIONAL PLATFORM 🚀           ║
    ║                                                       ║
    ║   Complete Full-Stack MVP Generator                  ║
    ║   • Landing Page                                     ║
    ║   • Authentication (Register/Login)                  ║
    ║   • Dashboard with Projects                          ║
    ║   • AI Chat with Context                             ║
    ║   • Live Preview                                     ║
    ║   • ZIP Download                                     ║
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
