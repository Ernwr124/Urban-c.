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
        chat_history TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    # Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
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
    """Secure password hashing with salt"""
    salt = "project0_secure_salt_2024"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def create_session(user_id: int) -> str:
    """Create secure session token"""
    token = secrets.token_urlsafe(48)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    expires = datetime.now().timestamp() + (7 * 24 * 60 * 60)  # 7 days
    c.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", 
              (token, user_id, expires))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[int]:
    """Validate session token"""
    if not token:
        return None
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return None
    
    user_id, expires_at = result
    if expires_at and datetime.now().timestamp() > float(expires_at):
        # Token expired
        return None
    
    return user_id

def delete_session(token: str):
    """Delete session on logout"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

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
- Professional Blue: #0066FF, #0052CC, #0047B3
- Success Green: #00C853, #00E676, #69F0AE
- Modern Purple: #6200EA, #7C4DFF, #B388FF
- Warm Orange: #FF6D00, #FF9100, #FFAB40

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

@app.post("/api/logout")
async def logout(token: str):
    """Logout user"""
    delete_session(token)
    return {"success": True}

@app.get("/api/projects")
async def get_projects(token: str):
    """Get user projects"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
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
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    chat_history = json.dumps([])
    c.execute("INSERT INTO projects (user_id, name, description, context, chat_history) VALUES (?, ?, ?, ?, ?)",
             (user_id, req.name, req.description, "", chat_history))
    conn.commit()
    project_id = c.lastrowid
    conn.close()
    
    return {"success": True, "project_id": project_id}

@app.get("/api/project/{project_id}")
async def get_project(project_id: int, token: str):
    """Get project details with chat history"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, description, context, files, chat_history FROM projects WHERE id = ? AND user_id = ?",
             (project_id, user_id))
    project = c.fetchone()
    conn.close()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    files = json.loads(project[4]) if project[4] else {}
    chat_history = json.loads(project[5]) if project[5] else []
    
    return {
        "id": project[0],
        "name": project[1],
        "description": project[2],
        "context": project[3],
        "files": files,
        "chat_history": chat_history
    }

@app.post("/api/chat")
async def chat(req: ChatRequest, token: str):
    """Chat with AI about project"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get project context
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT context, description, chat_history FROM projects WHERE id = ? AND user_id = ?",
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
                                
                                # Save chat history
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("SELECT chat_history FROM projects WHERE id = ?", (project_id,))
                                history_json = c.fetchone()[0]
                                history = json.loads(history_json) if history_json else []
                                
                                history.append({
                                    "role": "user",
                                    "content": message,
                                    "timestamp": datetime.now().isoformat()
                                })
                                history.append({
                                    "role": "assistant",
                                    "content": full_response,
                                    "timestamp": datetime.now().isoformat()
                                })
                                
                                # Update project context and files
                                new_context = context + f"\n\nUser: {message}\nAI: Generated files successfully."
                                c.execute("UPDATE projects SET context = ?, files = ?, chat_history = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                         (new_context, json.dumps(files), json.dumps(history), project_id))
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
    
    # Add start scripts
    files["start.sh"] = "#!/bin/bash\ncd backend\nnpm install\nnpm start"
    files["start.bat"] = "@echo off\ncd backend\nnpm install\nnpm start"
    
    return files

@app.get("/api/download/{project_id}")
async def download_project(project_id: int, token: str):
    """Download project as ZIP"""
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
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

# Main HTML Template with Resizable Panels, History, and Modern Design
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
            --bg-primary: #0A0A0F;
            --bg-secondary: #13131A;
            --bg-tertiary: #1A1A24;
            --bg-hover: #20202C;
            --border-color: #2A2A38;
            --border-hover: #3A3A48;
            --text-primary: #FFFFFF;
            --text-secondary: #B4B4C8;
            --text-tertiary: #7878A0;
            --accent-primary: #0066FF;
            --accent-secondary: #0052CC;
            --accent-light: #3385FF;
            --accent-glow: rgba(0, 102, 255, 0.2);
            --success: #00C853;
            --warning: #FF9100;
            --error: #FF1744;
            --gradient-blue: linear-gradient(135deg, #0066FF 0%, #0052CC 100%);
            --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.5);
            --shadow-accent: 0 4px 20px var(--accent-glow);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            overflow-x: hidden;
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
            padding: 20px 48px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-primary);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .logo {
            width: 44px;
            height: 44px;
            background: var(--gradient-blue);
            border-radius: 11px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 24px;
            color: white;
            box-shadow: var(--shadow-accent);
        }

        .logo-text {
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, var(--text-primary), var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .nav-actions button {
            padding: 11px 26px;
            background: var(--gradient-blue);
            color: white;
            border: none;
            border-radius: 9px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--shadow-accent);
        }

        .nav-actions button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px var(--accent-glow);
        }

        .landing-hero {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 100px 48px;
            text-align: center;
            background: radial-gradient(ellipse at top, rgba(0, 102, 255, 0.1) 0%, transparent 50%);
        }

        .hero-title {
            font-size: 68px;
            font-weight: 900;
            margin-bottom: 20px;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--accent-primary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1.1;
            letter-spacing: -0.02em;
        }

        .hero-subtitle {
            font-size: 22px;
            color: var(--text-secondary);
            margin-bottom: 44px;
            max-width: 680px;
            font-weight: 400;
            line-height: 1.5;
        }

        .hero-cta {
            padding: 16px 44px;
            background: var(--gradient-blue);
            color: white;
            border: none;
            border-radius: 11px;
            font-weight: 700;
            font-size: 17px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--shadow-accent);
        }

        .hero-cta:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 32px var(--accent-glow);
        }

        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 28px;
            max-width: 1100px;
            margin-top: 80px;
        }

        .feature-card {
            padding: 30px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .feature-card:hover {
            transform: translateY(-4px);
            border-color: var(--accent-primary);
            box-shadow: var(--shadow-lg);
        }

        .feature-icon {
            font-size: 44px;
            margin-bottom: 14px;
        }

        .feature-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 10px;
            color: var(--text-primary);
        }

        .feature-desc {
            color: var(--text-secondary);
            font-size: 14px;
            line-height: 1.6;
        }

        /* Auth Page */
        .auth-container {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 48px;
            background: radial-gradient(ellipse at center, rgba(0, 102, 255, 0.08) 0%, transparent 60%);
        }

        .auth-box {
            width: 100%;
            max-width: 440px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 18px;
            padding: 44px;
            box-shadow: var(--shadow-lg);
        }

        .auth-title {
            font-size: 30px;
            font-weight: 800;
            margin-bottom: 30px;
            text-align: center;
            color: var(--text-primary);
        }

        .form-group {
            margin-bottom: 22px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            font-size: 13px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .form-input {
            width: 100%;
            padding: 13px 16px;
            background: var(--bg-secondary);
            border: 2px solid var(--border-color);
            border-radius: 9px;
            color: var(--text-primary);
            font-size: 15px;
            font-family: inherit;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .form-input:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px var(--accent-glow);
            background: var(--bg-primary);
        }

        .auth-button {
            width: 100%;
            padding: 15px;
            background: var(--gradient-blue);
            color: white;
            border: none;
            border-radius: 9px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin-top: 8px;
            box-shadow: var(--shadow-accent);
        }

        .auth-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px var(--accent-glow);
        }

        .auth-switch {
            text-align: center;
            margin-top: 22px;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .auth-switch a {
            color: var(--accent-primary);
            text-decoration: none;
            font-weight: 600;
            cursor: pointer;
            transition: color 0.2s;
        }

        .auth-switch a:hover {
            color: var(--accent-light);
        }

        /* Dashboard */
        .dashboard {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .dashboard-nav {
            padding: 18px 48px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-primary);
            backdrop-filter: blur(10px);
        }

        .user-info {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .user-avatar {
            width: 38px;
            height: 38px;
            background: var(--gradient-blue);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            box-shadow: var(--shadow-accent);
        }

        .dashboard-content {
            flex: 1;
            padding: 48px;
            background: var(--bg-primary);
        }

        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 44px;
        }

        .dashboard-title {
            font-size: 38px;
            font-weight: 800;
            color: var(--text-primary);
        }

        .create-project-btn {
            padding: 13px 30px;
            background: var(--gradient-blue);
            color: white;
            border: none;
            border-radius: 9px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: var(--shadow-accent);
        }

        .create-project-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px var(--accent-glow);
        }

        .projects-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 22px;
        }

        .project-card {
            padding: 26px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .project-card:hover {
            transform: translateY(-4px);
            border-color: var(--accent-primary);
            box-shadow: var(--shadow-lg);
            background: var(--bg-hover);
        }

        .project-name {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 10px;
            color: var(--text-primary);
        }

        .project-desc {
            color: var(--text-secondary);
            font-size: 14px;
            margin-bottom: 14px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            line-height: 1.5;
        }

        .project-date {
            font-size: 12px;
            color: var(--text-tertiary);
        }

        /* Chat Interface with Resizable */
        .chat-container {
            display: flex;
            height: 100vh;
        }

        .chat-sidebar {
            width: 260px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
        }

        .chat-sidebar-header {
            padding: 18px;
            border-bottom: 1px solid var(--border-color);
        }

        .back-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 14px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
        }

        .back-btn:hover {
            background: var(--bg-hover);
            border-color: var(--border-hover);
        }

        .chat-main {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .chat-header {
            padding: 18px 30px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-secondary);
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 30px;
            background: var(--bg-primary);
        }

        .message {
            margin-bottom: 26px;
            animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 9px;
        }

        .message-role {
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
        }

        .user-role { color: var(--text-primary); }
        .ai-role { color: var(--accent-light); }

        .message-content {
            padding: 18px;
            border-radius: 12px;
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

        .chat-input-area {
            padding: 30px;
            border-top: 1px solid var(--border-color);
            background: var(--bg-secondary);
        }

        .chat-input-wrapper {
            position: relative;
        }

        #chatInput {
            width: 100%;
            padding: 16px 70px 16px 18px;
            background: var(--bg-tertiary);
            border: 2px solid var(--border-color);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 14px;
            font-family: inherit;
            resize: none;
            outline: none;
            min-height: 80px;
            max-height: 200px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        #chatInput:focus {
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px var(--accent-glow);
            background: var(--bg-primary);
        }

        #sendBtn {
            position: absolute;
            right: 12px;
            bottom: 12px;
            width: 44px;
            height: 44px;
            background: var(--gradient-blue);
            color: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: var(--shadow-accent);
        }

        #sendBtn:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 16px var(--accent-glow);
        }

        /* Resizable Preview Panel */
        .chat-preview {
            width: 45%;
            background: var(--bg-secondary);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            position: relative;
            min-width: 300px;
            max-width: 70%;
        }

        .resize-handle {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            cursor: col-resize;
            background: transparent;
            transition: background 0.2s;
        }

        .resize-handle:hover {
            background: var(--accent-primary);
        }

        .resize-handle.dragging {
            background: var(--accent-primary);
        }

        .preview-header {
            padding: 18px 26px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-secondary);
        }

        .preview-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .preview-content {
            flex: 1;
            overflow: auto;
            padding: 26px;
            background: var(--bg-primary);
        }

        .preview-frame {
            width: 100%;
            height: 100%;
            border: none;
            border-radius: 10px;
            background: white;
            box-shadow: var(--shadow-md);
        }

        .file-list {
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .file-item {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow: hidden;
            transition: all 0.2s;
        }

        .file-item:hover {
            border-color: var(--border-hover);
        }

        .file-header {
            padding: 13px 16px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .file-header:hover {
            background: var(--bg-hover);
        }

        .file-name {
            font-weight: 600;
            font-size: 13px;
            font-family: 'Monaco', 'Courier New', monospace;
            color: var(--text-primary);
        }

        .file-content {
            padding: 0;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }

        .file-content.expanded {
            max-height: 500px;
            overflow: auto;
        }

        .file-content pre {
            margin: 0;
            padding: 16px;
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-size: 12px;
            line-height: 1.6;
            font-family: 'Monaco', 'Courier New', monospace;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(8px);
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
            border-radius: 18px;
            padding: 38px;
            max-width: 480px;
            width: 90%;
            box-shadow: var(--shadow-lg);
        }

        .modal-title {
            font-size: 26px;
            font-weight: 800;
            margin-bottom: 22px;
            color: var(--text-primary);
        }

        .btn-secondary {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            padding: 11px 22px;
            border-radius: 9px;
            color: var(--text-primary);
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-secondary:hover {
            background: var(--bg-hover);
            border-color: var(--border-hover);
        }

        .download-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 11px 22px;
            background: linear-gradient(135deg, var(--success), #00E676);
            color: white;
            border: none;
            border-radius: 9px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 16px rgba(0, 200, 83, 0.3);
        }

        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(0, 200, 83, 0.4);
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
            background: var(--border-hover);
        }

        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-tertiary);
            text-align: center;
            padding: 40px;
        }

        .empty-icon {
            font-size: 56px;
            margin-bottom: 16px;
            opacity: 0.7;
        }

        .empty-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-secondary);
        }

        .empty-desc {
            font-size: 14px;
        }
    </style>
</head>
<body>
    <!-- Landing Page -->
    <div id="landingPage" class="page active landing">
        <nav class="landing-nav">
            <div class="logo-container">
                <div class="logo">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M4 7C4 5.34315 5.34315 4 7 4H12L17 9V17C17 18.6569 15.6569 20 14 20H7C5.34315 20 4 18.6569 4 17V7Z" fill="white"/>
                        <path d="M17 9L12 4V7C12 8.10457 12.8954 9 14 9H17Z" fill="white" fill-opacity="0.7"/>
                        <rect x="6" y="11" width="8" height="2" rx="1" fill="currentColor" fill-opacity="0.3"/>
                        <rect x="6" y="14" width="6" height="2" rx="1" fill="currentColor" fill-opacity="0.3"/>
                    </svg>
                </div>
                <div class="logo-text">Project-0</div>
            </div>
            <div class="nav-actions">
                <button onclick="scrollToFeatures()">Learn More</button>
                <button onclick="showPage('authPage')" style="margin-left: 12px;">Try It Now</button>
            </div>
        </nav>
        <div class="landing-hero">
            <h1 class="hero-title">Build MVPs in Minutes</h1>
            <p class="hero-subtitle">
                Transform your ideas into production-ready applications with intelligent code generation.
                Full-stack, database-integrated, deployment-ready.
            </p>
            <button class="hero-cta" onclick="showPage('authPage')">Get Started</button>
            
            <div class="features" id="featuresSection">
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <div class="feature-title">Lightning Fast</div>
                    <div class="feature-desc">Generate complete MVPs in minutes with advanced AI</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🏗️</div>
                    <div class="feature-title">Full-Stack Ready</div>
                    <div class="feature-desc">Backend, frontend, and database automatically configured</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🎨</div>
                    <div class="feature-title">Beautiful UI</div>
                    <div class="feature-desc">Modern, responsive designs with professional styling</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🔐</div>
                    <div class="feature-title">Production Ready</div>
                    <div class="feature-desc">Security, error handling, and best practices included</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Auth Page -->
    <div id="authPage" class="page">
        <div class="auth-container">
            <div class="auth-box">
                <div class="logo-container" style="justify-content: center; margin-bottom: 30px;">
                    <div class="logo">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M4 7C4 5.34315 5.34315 4 7 4H12L17 9V17C17 18.6569 15.6569 20 14 20H7C5.34315 20 4 18.6569 4 17V7Z" fill="white"/>
                            <path d="M17 9L12 4V7C12 8.10457 12.8954 9 14 9H17Z" fill="white" fill-opacity="0.7"/>
                        </svg>
                    </div>
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
                            <input type="password" class="form-input" required id="registerPassword" minlength="6">
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
                <div class="logo">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M4 7C4 5.34315 5.34315 4 7 4H12L17 9V17C17 18.6569 15.6569 20 14 20H7C5.34315 20 4 18.6569 4 17V7Z" fill="white"/>
                        <path d="M17 9L12 4V7C12 8.10457 12.8954 9 14 9H17Z" fill="white" fill-opacity="0.7"/>
                    </svg>
                </div>
                <div class="logo-text">Project-0</div>
            </div>
            <div class="user-info">
                <span id="userName" style="color: var(--text-secondary); font-size: 14px;"></span>
                <div class="user-avatar" id="userAvatar"></div>
                <button class="btn-secondary" onclick="logout()">Logout</button>
            </div>
        </nav>
        <div class="dashboard-content">
            <div class="dashboard-header">
                <h1 class="dashboard-title">Your Projects</h1>
                <button class="create-project-btn" onclick="showCreateModal()">
                    <span style="font-size: 18px;">+</span> New Project
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
                        ← Projects
                    </button>
                </div>
            </div>
            <div class="chat-main">
                <div class="chat-header">
                    <h2 id="chatProjectName" style="font-size: 18px; font-weight: 700; color: var(--text-primary);"></h2>
                    <button class="download-btn" id="downloadBtn" onclick="downloadProject()" style="display:none;">
                        ↓ Download ZIP
                    </button>
                </div>
                <div class="chat-messages" id="chatMessages"></div>
                <div class="chat-input-area">
                    <div class="chat-input-wrapper">
                        <textarea id="chatInput" placeholder="Describe what you want to build or modify..."></textarea>
                        <button id="sendBtn" onclick="sendMessage()">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
            <div class="chat-preview" id="chatPreview">
                <div class="resize-handle" id="resizeHandle"></div>
                <div class="preview-header">
                    <h3 class="preview-title">Live Preview</h3>
                </div>
                <div class="preview-content" id="previewContent">
                    <div class="empty-state">
                        <div class="empty-icon">✨</div>
                        <div class="empty-title">Ready to Build</div>
                        <div class="empty-desc">Your preview will appear here</div>
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
                    <input type="text" class="form-input" required id="projectName" placeholder="My Awesome Project">
                </div>
                <div class="form-group">
                    <label class="form-label">Description / Requirements</label>
                    <textarea class="form-input" required id="projectDesc" style="min-height:120px;resize:vertical;" placeholder="Describe your MVP in detail..."></textarea>
                </div>
                <div style="display:flex;gap:12px;margin-top:22px;">
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

        // Smooth scroll
        function scrollToFeatures() {
            document.getElementById('featuresSection').scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        // Load state from localStorage
        function loadState() {
            var token = localStorage.getItem('token');
            var user = localStorage.getItem('user');
            if (token && user) {
                currentToken = token;
                currentUser = JSON.parse(user);
                showPage('dashboardPage');
                loadProjects();
            }
        }

        // Page navigation
        function showPage(pageId) {
            var pages = document.querySelectorAll('.page');
            for (var i = 0; i < pages.length; i++) {
                pages[i].classList.remove('active');
            }
            document.getElementById(pageId).classList.add('active');
            
            if (pageId === 'dashboardPage' && currentUser) {
                document.getElementById('userName').textContent = currentUser.name;
                document.getElementById('userAvatar').textContent = currentUser.name[0].toUpperCase();
            }
        }

        // Auth functions
        function toggleAuth() {
            var login = document.getElementById('loginForm');
            var register = document.getElementById('registerForm');
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
            var email = document.getElementById('loginEmail').value;
            var password = document.getElementById('loginPassword').value;
            
            try {
                var response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: email, password: password})
                });
                
                var data = await response.json();
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
            var name = document.getElementById('registerName').value;
            var email = document.getElementById('registerEmail').value;
            var password = document.getElementById('registerPassword').value;
            
            try {
                var response = await fetch('/api/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name, email: email, password: password})
                });
                
                var data = await response.json();
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

        async function logout() {
            try {
                await fetch('/api/logout?token=' + currentToken, {method: 'POST'});
            } catch(e) {}
            
            currentToken = null;
            currentUser = null;
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            showPage('landingPage');
        }

        // Projects
        async function loadProjects() {
            try {
                var response = await fetch('/api/projects?token=' + currentToken);
                var data = await response.json();
                
                var grid = document.getElementById('projectsGrid');
                if (data.projects.length === 0) {
                    grid.innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-icon">📁</div><div class="empty-title">No projects yet</div><div class="empty-desc">Create your first project to get started</div></div>';
                    return;
                }
                
                grid.innerHTML = data.projects.map(function(p) {
                    return '<div class="project-card" onclick="openProject(' + p.id + ', \'' + p.name.replace(/'/g, "\\'") + '\')">' +
                        '<div class="project-name">' + escapeHtml(p.name) + '</div>' +
                        '<div class="project-desc">' + escapeHtml(p.description) + '</div>' +
                        '<div class="project-date">Created ' + new Date(p.created_at).toLocaleDateString() + '</div>' +
                        '</div>';
                }).join('');
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
            var name = document.getElementById('projectName').value;
            var description = document.getElementById('projectDesc').value;
            
            try {
                var response = await fetch('/api/projects?token=' + currentToken, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: name, description: description})
                });
                
                var data = await response.json();
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
            
            // Clear messages
            document.getElementById('chatMessages').innerHTML = '';
            
            // Load project details and history
            try {
                var response = await fetch('/api/project/' + projectId + '?token=' + currentToken);
                var data = await response.json();
                projectFiles = data.files || {};
                
                // Display chat history
                if (data.chat_history && data.chat_history.length > 0) {
                    var messagesDiv = document.getElementById('chatMessages');
                    for (var i = 0; i < data.chat_history.length; i++) {
                        var msg = data.chat_history[i];
                        addMessageToUI(msg.role === 'user' ? 'user' : 'assistant', msg.content);
                    }
                }
                
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
            var input = document.getElementById('chatInput');
            var message = input.value.trim();
            if (!message) return;
            
            // Add user message
            addMessageToUI('user', message);
            input.value = '';
            
            // Add AI message container
            var messagesDiv = document.getElementById('chatMessages');
            var aiDiv = document.createElement('div');
            aiDiv.className = 'message ai-message';
            aiDiv.innerHTML = '<div class="message-header"><span class="message-role ai-role">Project-0 AI</span></div><div class="message-content" id="currentResponse"></div>';
            messagesDiv.appendChild(aiDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            try {
                var response = await fetch('/api/chat?token=' + currentToken, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({project_id: currentProject, message: message})
                });
                
                var reader = response.body.getReader();
                var decoder = new TextDecoder();
                var fullResponse = '';
                
                while (true) {
                    var result = await reader.read();
                    if (result.done) break;
                    
                    var chunk = decoder.decode(result.value);
                    var lines = chunk.split('\\n');
                    
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        if (line.startsWith('data: ')) {
                            var data = JSON.parse(line.slice(6));
                            
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

        function addMessageToUI(role, content) {
            var messagesDiv = document.getElementById('chatMessages');
            var messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role + '-message';
            var roleLabel = role === 'user' ? 'You' : 'Project-0 AI';
            var roleClass = role === 'user' ? 'user-role' : 'ai-role';
            var contentHtml = role === 'user' ? escapeHtml(content) : marked.parse(content);
            messageDiv.innerHTML = '<div class="message-header">' +
                '<span class="message-role ' + roleClass + '">' + roleLabel + '</span>' +
                '</div>' +
                '<div class="message-content">' + contentHtml + '</div>';
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function showFiles(files) {
            var preview = document.getElementById('previewContent');
            
            // Check if there's an index.html to show
            if (files['frontend/index.html']) {
                var iframe = document.createElement('iframe');
                iframe.className = 'preview-frame';
                iframe.srcdoc = files['frontend/index.html'];
                preview.innerHTML = '';
                preview.appendChild(iframe);
            } else {
                // Show file list
                var html = '<div class="file-list">';
                var fileKeys = Object.keys(files);
                for (var i = 0; i < fileKeys.length; i++) {
                    var filename = fileKeys[i];
                    var content = files[filename];
                    html += '<div class="file-item">' +
                        '<div class="file-header" onclick="toggleFile(this)">' +
                        '<span class="file-name">' + escapeHtml(filename) + '</span>' +
                        '<span>▼</span>' +
                        '</div>' +
                        '<div class="file-content">' +
                        '<pre><code>' + escapeHtml(content) + '</code></pre>' +
                        '</div>' +
                        '</div>';
                }
                html += '</div>';
                preview.innerHTML = html;
            }
        }

        function toggleFile(header) {
            var content = header.nextElementSibling;
            var arrow = header.querySelector('span:last-child');
            if (content.classList.contains('expanded')) {
                content.classList.remove('expanded');
                arrow.textContent = '▼';
            } else {
                content.classList.add('expanded');
                arrow.textContent = '▲';
            }
        }

        async function downloadProject() {
            window.location.href = '/api/download/' + currentProject + '?token=' + currentToken;
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Resizable panel
        (function() {
            var resizeHandle = document.getElementById('resizeHandle');
            var chatPreview = document.getElementById('chatPreview');
            var chatMain = document.querySelector('.chat-main');
            var isDragging = false;
            var startX = 0;
            var startWidth = 0;

            resizeHandle.addEventListener('mousedown', function(e) {
                isDragging = true;
                startX = e.clientX;
                startWidth = chatPreview.offsetWidth;
                resizeHandle.classList.add('dragging');
                document.body.style.cursor = 'col-resize';
                e.preventDefault();
            });

            document.addEventListener('mousemove', function(e) {
                if (!isDragging) return;
                
                var deltaX = startX - e.clientX;
                var newWidth = startWidth + deltaX;
                var minWidth = 300;
                var maxWidth = window.innerWidth * 0.7;
                
                if (newWidth >= minWidth && newWidth <= maxWidth) {
                    chatPreview.style.width = newWidth + 'px';
                }
            });

            document.addEventListener('mouseup', function() {
                if (isDragging) {
                    isDragging = false;
                    resizeHandle.classList.remove('dragging');
                    document.body.style.cursor = '';
                }
            });
        })();

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
    ║   • Modern Professional Design                       ║
    ║   • Resizable Preview Panel                          ║
    ║   • Chat History Storage                             ║
    ║   • Secure Authentication                            ║
    ║   • Smooth Scroll & Navigation                       ║
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
