"""
Project-0: Professional AI MVP Platform
Premium SaaS UI - All-in-One File
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import json
import asyncio
from typing import AsyncGenerator, Dict, Optional
from datetime import datetime
import re
import sqlite3
import hashlib
import secrets
import io
import zipfile
import urllib.parse

app = FastAPI(title="Project-0", description="Professional AI MVP Platform")

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
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
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
    salt = "project0_secure_salt_2024"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    expires = datetime.now().timestamp() + (7 * 24 * 60 * 60)
    c.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", 
              (token, user_id, expires))
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str) -> Optional[int]:
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
        return None
    return user_id

def delete_session(token: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def get_system_prompt(project_context: str = "") -> str:
    base_prompt = """You are Project-0 AI, a professional full-stack development assistant.

Generate production-ready applications with:
- Node.js + Express backend
- SQLite/MongoDB database
- HTML + Tailwind CSS + JavaScript frontend
- Complete, working code
- Security best practices

Response Format:
## 📋 Project Overview
[Brief description]

## 📁 Files

### backend/package.json
```json
[Complete package.json]
```

### backend/server.js
```javascript
[Complete Express server]
```

### frontend/index.html
```html
[Complete frontend]
```

### start.sh
```bash
#!/bin/bash
cd backend && npm install && npm start
```"""

    if project_context:
        base_prompt += f"\n\nPROJECT CONTEXT:\n{project_context}"
    
    return base_prompt

# API Endpoints

@app.post("/api/register")
async def register(req: RegisterRequest):
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
    delete_session(token)
    return {"success": True}

@app.get("/api/projects")
async def get_projects(token: str):
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
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
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
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
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
async def chat_api(req: ChatRequest, token: str):
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT context, description, chat_history FROM projects WHERE id = ? AND user_id = ?",
             (req.project_id, user_id))
    project = c.fetchone()
    conn.close()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project_context = f"Project Description: {project[1]}\\n\\nPrevious Context: {project[0]}"
    return StreamingResponse(
        generate_mvp_stream(req.message, req.project_id, user_id, project_context),
        media_type="text/event-stream"
    )

async def generate_mvp_stream(message: str, project_id: int, user_id: int, context: str) -> AsyncGenerator[str, None]:
    system_prompt = get_system_prompt(context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing request...'})}\n\n"
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'status', 'content': 'Designing architecture...'})}\n\n"
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'status', 'content': 'Generating code...'})}\n\n"
            await asyncio.sleep(0.3)
            
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
                                files = extract_project_files(full_response)
                                conn = sqlite3.connect(DB_FILE)
                                c = conn.cursor()
                                c.execute("SELECT chat_history FROM projects WHERE id = ?", (project_id,))
                                history_json = c.fetchone()[0]
                                history = json.loads(history_json) if history_json else []
                                history.append({"role": "user", "content": message, "timestamp": datetime.now().isoformat()})
                                history.append({"role": "assistant", "content": full_response, "timestamp": datetime.now().isoformat()})
                                new_context = context + f"\\n\\nUser: {message}\\nAI: Generated files successfully."
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
    files = {}
    pattern = r'###\s+([^\n]+)\s*\n```(?:\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    for filename, code in matches:
        filename = filename.strip()
        files[filename] = code.strip()
    files["start.sh"] = "#!/bin/bash\\ncd backend\\nnpm install\\nnpm start"
    files["start.bat"] = "@echo off\\ncd backend\\nnpm install\\nnpm start"
    return files

@app.get("/api/download/{project_id}")
async def download_project(project_id: int, token: str):
    user_id = get_user_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, files FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    project = c.fetchone()
    conn.close()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    files = json.loads(project[1]) if project[1] else {}
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    zip_buffer.seek(0)
    
    # Properly encode filename for unicode support
    filename = f"{project[0]}.zip"
    encoded_filename = urllib.parse.quote(filename)
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )

@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Route handler
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_page(full_path: str):
    if full_path == "" or full_path == "/":
        return LANDING_PAGE
    elif full_path == "auth":
        return AUTH_PAGE
    elif full_path == "dashboard":
        return DASHBOARD_PAGE
    elif full_path == "chat":
        return CHAT_PAGE
    return HTMLResponse(content="<h1>404 Not Found</h1>", status_code=404)

# HTML Templates - Premium SaaS UI

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Professional AI MVP Platform</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #09090B;
            --bg-secondary: #18181B;
            --bg-tertiary: #27272A;
            --bg-hover: #3F3F46;
            --border-color: #27272A;
            --border-hover: #3F3F46;
            --text-primary: #FAFAFA;
            --text-secondary: #A1A1AA;
            --text-tertiary: #71717A;
            --accent: #3B82F6;
            --accent-hover: #2563EB;
            --gradient-1: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
            --gradient-2: linear-gradient(135deg, #8B5CF6 0%, #EC4899 100%);
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
            --shadow-lg: 0 20px 25px -5px rgb(0 0 0 / 0.5), 0 8px 10px -6px rgb(0 0 0 / 0.5);
        }
        
        body {
            font-family: 'Inter', -apple-system, system-ui, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
        }
        
        .nav {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 50;
            background: rgba(9, 9, 11, 0.8);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-color);
        }
        
        .nav-inner {
            max-width: 1280px;
            margin: 0 auto;
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-primary);
        }
        
        .logo-icon {
            width: 32px;
            height: 32px;
            background: var(--gradient-1);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .btn {
            padding: 0.625rem 1.25rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            outline: none;
        }
        
        .btn-primary {
            background: var(--gradient-1);
            color: white;
            box-shadow: var(--shadow);
        }
        
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-lg);
        }
        
        .hero {
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 6rem 1.5rem 4rem;
            text-align: center;
            position: relative;
        }
        
        .hero::before {
            content: '';
            position: absolute;
            top: 0;
            left: 50%;
            transform: translateX(-50%);
            width: 800px;
            height: 800px;
            background: radial-gradient(circle, rgba(59, 130, 246, 0.1) 0%, transparent 70%);
            pointer-events: none;
        }
        
        .hero-content {
            max-width: 56rem;
            z-index: 1;
        }
        
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.375rem 0.875rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 9999px;
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 1.5rem;
        }
        
        .hero-title {
            font-size: 4rem;
            font-weight: 800;
            line-height: 1.1;
            letter-spacing: -0.02em;
            margin-bottom: 1.5rem;
            background: linear-gradient(to bottom right, var(--text-primary), var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .hero-subtitle {
            font-size: 1.25rem;
            color: var(--text-secondary);
            margin-bottom: 2.5rem;
            max-width: 42rem;
            margin-left: auto;
            margin-right: auto;
        }
        
        .hero-cta {
            padding: 0.875rem 2rem;
            font-size: 1rem;
        }
        
        .features {
            max-width: 1280px;
            margin: 0 auto;
            padding: 4rem 1.5rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }
        
        .feature-card {
            padding: 2rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            transition: all 0.3s;
        }
        
        .feature-card:hover {
            transform: translateY(-4px);
            border-color: var(--border-hover);
            box-shadow: var(--shadow-lg);
        }
        
        .feature-icon {
            width: 48px;
            height: 48px;
            background: var(--bg-tertiary);
            border-radius: 0.75rem;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 1rem;
        }
        
        .feature-title {
            font-size: 1.125rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        
        .feature-desc {
            color: var(--text-secondary);
            font-size: 0.875rem;
            line-height: 1.6;
        }
        
        @media (max-width: 768px) {
            .hero-title { font-size: 2.5rem; }
            .hero-subtitle { font-size: 1rem; }
        }
    </style>
</head>
<body>
    <nav class="nav">
        <div class="nav-inner">
            <div class="logo">
                <div class="logo-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                    </svg>
                </div>
                <span>Project-0</span>
            </div>
            <button class="btn btn-primary" onclick="window.location.href='/auth'">Get Started</button>
        </div>
    </nav>
    
    <main>
        <section class="hero">
            <div class="hero-content">
                <div class="hero-badge">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                    </svg>
                    <span>AI-Powered MVP Generator</span>
                </div>
                
                <h1 class="hero-title">Build Production-Ready MVPs in Minutes</h1>
                
                <p class="hero-subtitle">
                    Transform your ideas into full-stack applications with intelligent code generation. 
                    Complete backend, frontend, and database — ready to deploy.
                </p>
                
                <button class="btn btn-primary hero-cta" onclick="window.location.href='/auth'">
                    Start Building Free
                </button>
            </div>
        </section>
        
        <section class="features" id="features">
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                    </svg>
                </div>
                <h3 class="feature-title">Lightning Fast</h3>
                <p class="feature-desc">Generate complete MVPs in minutes with advanced AI technology</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
                        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
                    </svg>
                </div>
                <h3 class="feature-title">Full-Stack Ready</h3>
                <p class="feature-desc">Backend, frontend, and database automatically configured</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                        <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
                    </svg>
                </div>
                <h3 class="feature-title">Production Ready</h3>
                <p class="feature-desc">Security, error handling, and best practices included</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                </div>
                <h3 class="feature-title">Real-time Preview</h3>
                <p class="feature-desc">See your application come to life as code is generated</p>
            </div>
        </section>
    </main>
    
    <script>
        document.querySelector('.hero-badge').style.animation = 'fadeIn 0.5s ease-out';
        
        const style = document.createElement('style');
        style.textContent = '@keyframes fadeIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }';
        document.head.appendChild(style);
    </script>
</body>
</html>"""

AUTH_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In - Project-0</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #09090B;
            --bg-secondary: #18181B;
            --bg-tertiary: #27272A;
            --bg-hover: #3F3F46;
            --border-color: #27272A;
            --text-primary: #FAFAFA;
            --text-secondary: #A1A1AA;
            --accent: #3B82F6;
            --gradient: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
            --shadow-lg: 0 20px 25px -5px rgb(0 0 0 / 0.5);
        }
        
        body {
            font-family: 'Inter', -apple-system, system-ui, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
            -webkit-font-smoothing: antialiased;
        }
        
        body::before {
            content: '';
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 600px;
            height: 600px;
            background: radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%);
            pointer-events: none;
        }
        
        .auth-container {
            width: 100%;
            max-width: 420px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 2.5rem;
            box-shadow: var(--shadow-lg);
            position: relative;
            z-index: 1;
        }
        
        .logo {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            margin-bottom: 2rem;
            font-size: 1.5rem;
            font-weight: 700;
        }
        
        .logo-icon {
            width: 40px;
            height: 40px;
            background: var(--gradient);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .auth-title {
            font-size: 1.875rem;
            font-weight: 800;
            text-align: center;
            margin-bottom: 2rem;
        }
        
        .form-group {
            margin-bottom: 1.25rem;
        }
        
        .form-label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .form-input {
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: var(--text-primary);
            font-size: 0.9375rem;
            font-family: inherit;
            transition: all 0.2s;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .btn {
            width: 100%;
            padding: 0.875rem;
            background: var(--gradient);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-weight: 700;
            font-size: 0.9375rem;
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 0.5rem;
        }
        
        .btn:hover {
            transform: translateY(-1px);
            box-shadow: var(--shadow-lg);
        }
        
        .auth-switch {
            text-align: center;
            margin-top: 1.5rem;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }
        
        .auth-switch a {
            color: var(--accent);
            text-decoration: none;
            font-weight: 600;
            cursor: pointer;
        }
        
        .form-hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="auth-container">
        <div class="logo">
            <div class="logo-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                </svg>
            </div>
            <span>Project-0</span>
        </div>
        
        <form id="loginForm" onsubmit="handleLogin(event)">
            <h2 class="auth-title">Welcome Back</h2>
            <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" class="form-input" required id="loginEmail" placeholder="you@example.com">
            </div>
            <div class="form-group">
                <label class="form-label">Password</label>
                <input type="password" class="form-input" required id="loginPassword" placeholder="••••••••">
            </div>
            <button type="submit" class="btn">Sign In</button>
            <div class="auth-switch">
                Don't have an account? <a onclick="toggleAuth()">Sign up</a>
            </div>
        </form>

        <form id="registerForm" class="form-hidden" onsubmit="handleRegister(event)">
            <h2 class="auth-title">Create Account</h2>
            <div class="form-group">
                <label class="form-label">Full Name</label>
                <input type="text" class="form-input" required id="registerName" placeholder="John Doe">
            </div>
            <div class="form-group">
                <label class="form-label">Email Address</label>
                <input type="email" class="form-input" required id="registerEmail" placeholder="you@example.com">
            </div>
            <div class="form-group">
                <label class="form-label">Password</label>
                <input type="password" class="form-input" required id="registerPassword" minlength="6" placeholder="••••••••">
            </div>
            <button type="submit" class="btn">Create Account</button>
            <div class="auth-switch">
                Already have an account? <a onclick="toggleAuth()">Sign in</a>
            </div>
        </form>
    </div>

    <script>
        const token = localStorage.getItem('token');
        if (token) window.location.href = '/dashboard';

        function toggleAuth() {
            document.getElementById('loginForm').classList.toggle('form-hidden');
            document.getElementById('registerForm').classList.toggle('form-hidden');
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
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = '/dashboard';
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
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = '/dashboard';
                } else {
                    alert('Registration failed');
                }
            } catch (error) {
                alert('Registration failed: ' + error.message);
            }
        }
    </script>
</body>
</html>"""

DASHBOARD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Project-0</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #09090B;
            --bg-secondary: #18181B;
            --bg-tertiary: #27272A;
            --bg-hover: #3F3F46;
            --border-color: #27272A;
            --text-primary: #FAFAFA;
            --text-secondary: #A1A1AA;
            --accent: #3B82F6;
            --gradient: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
            --shadow-lg: 0 20px 25px -5px rgb(0 0 0 / 0.5);
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .nav {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 1.25rem;
            font-weight: 700;
        }
        
        .logo-icon {
            width: 32px;
            height: 32px;
            background: var(--gradient);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .user-info {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .user-avatar {
            width: 36px;
            height: 36px;
            background: var(--gradient);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.875rem;
        }
        
        .btn {
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid var(--border-color);
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }
        
        .btn:hover {
            background: var(--bg-hover);
        }
        
        .btn-primary {
            background: var(--gradient);
            border: none;
            color: white;
        }
        
        .container {
            max-width: 1280px;
            margin: 0 auto;
            padding: 3rem 2rem;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
        }
        
        .title {
            font-size: 2.25rem;
            font-weight: 800;
        }
        
        .projects-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 1.5rem;
        }
        
        .project-card {
            padding: 1.5rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .project-card:hover {
            transform: translateY(-2px);
            border-color: var(--accent);
            box-shadow: var(--shadow-lg);
        }
        
        .project-name {
            font-size: 1.125rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        
        .project-desc {
            color: var(--text-secondary);
            font-size: 0.875rem;
            margin-bottom: 1rem;
            line-height: 1.5;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .project-date {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        
        .modal {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(4px);
            align-items: center;
            justify-content: center;
            z-index: 50;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 2rem;
            max-width: 500px;
            width: 90%;
        }
        
        .modal-title {
            font-size: 1.5rem;
            font-weight: 800;
            margin-bottom: 1.5rem;
        }
        
        .form-group {
            margin-bottom: 1.25rem;
        }
        
        .form-label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .form-input {
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: var(--text-primary);
            font-size: 0.9375rem;
            font-family: inherit;
            transition: all 0.2s;
        }
        
        .form-input:focus {
            outline: none;
            border-color: var(--accent);
        }
        
        textarea.form-input {
            min-height: 120px;
            resize: vertical;
        }
        
        .modal-actions {
            display: flex;
            gap: 0.75rem;
            margin-top: 1.5rem;
        }
        
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-secondary);
        }
        
        .empty-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 1rem;
            background: var(--bg-tertiary);
            border-radius: 1rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }
    </style>
</head>
<body>
    <nav class="nav">
        <div class="logo">
            <div class="logo-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                </svg>
            </div>
            <span>Project-0</span>
        </div>
        <div class="user-info">
            <span id="userName" style="color: var(--text-secondary); font-size: 0.875rem;"></span>
            <div class="user-avatar" id="userAvatar"></div>
            <button class="btn" onclick="logout()">Sign Out</button>
        </div>
    </nav>

    <div class="container">
        <div class="header">
            <h1 class="title">Your Projects</h1>
            <button class="btn btn-primary" onclick="showCreateModal()">
                <span style="font-size: 1.25rem; margin-right: 0.25rem;">+</span> New Project
            </button>
        </div>
        <div class="projects-grid" id="projectsGrid">
            <div class="empty-state">
                <div class="empty-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                </div>
                <div>Loading projects...</div>
            </div>
        </div>
    </div>

    <div id="createModal" class="modal">
        <div class="modal-content">
            <h2 class="modal-title">Create New Project</h2>
            <form onsubmit="createProject(event)">
                <div class="form-group">
                    <label class="form-label">Project Name</label>
                    <input type="text" class="form-input" required id="projectName" placeholder="My Awesome Project">
                </div>
                <div class="form-group">
                    <label class="form-label">Description</label>
                    <textarea class="form-input" required id="projectDesc" placeholder="Describe your MVP in detail..."></textarea>
                </div>
                <div class="modal-actions">
                    <button type="submit" class="btn btn-primary" style="flex: 1;">Create Project</button>
                    <button type="button" class="btn" onclick="closeModal()">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('token');
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (!token) window.location.href = '/auth';

        document.getElementById('userName').textContent = user.name || '';
        document.getElementById('userAvatar').textContent = (user.name || '?')[0].toUpperCase();

        async function loadProjects() {
            try {
                const response = await fetch('/api/projects?token=' + token);
                const data = await response.json();
                const grid = document.getElementById('projectsGrid');
                
                if (data.projects.length === 0) {
                    grid.innerHTML = '<div class="empty-state" style="grid-column: 1/-1;"><div class="empty-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div>No projects yet</div><div style="font-size: 0.875rem; margin-top: 0.5rem;">Create your first project to get started</div></div>';
                    return;
                }
                
                grid.innerHTML = data.projects.map(p => 
                    '<div class="project-card" onclick="openProject(' + p.id + ')">' +
                    '<div class="project-name">' + escapeHtml(p.name) + '</div>' +
                    '<div class="project-desc">' + escapeHtml(p.description) + '</div>' +
                    '<div class="project-date">Created ' + new Date(p.created_at).toLocaleDateString() + '</div>' +
                    '</div>'
                ).join('');
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
                const response = await fetch('/api/projects?token=' + token, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, description})
                });
                
                const data = await response.json();
                if (data.success) {
                    closeModal();
                    window.location.href = '/chat?project=' + data.project_id;
                }
            } catch (error) {
                alert('Failed to create project');
            }
        }

        function openProject(projectId) {
            window.location.href = '/chat?project=' + projectId;
        }

        async function logout() {
            try {
                await fetch('/api/logout?token=' + token, {method: 'POST'});
            } catch(e) {}
            localStorage.clear();
            window.location.href = '/';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        loadProjects();
    </script>
</body>
</html>"""

CHAT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat - Project-0</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg-primary: #09090B;
            --bg-secondary: #18181B;
            --bg-tertiary: #27272A;
            --bg-hover: #3F3F46;
            --border-color: #27272A;
            --text-primary: #FAFAFA;
            --text-secondary: #A1A1AA;
            --accent: #3B82F6;
            --gradient: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%);
            --success: #10B981;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            overflow: hidden;
        }
        
        .container {
            display: flex;
            height: 100vh;
        }
        
        .sidebar {
            width: 240px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
        }
        
        .sidebar-header {
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
        }
        
        .back-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.625rem 0.875rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: var(--text-primary);
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            width: 100%;
            transition: all 0.2s;
        }
        
        .back-btn:hover {
            background: var(--bg-hover);
        }
        
        .chat-main {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        
        .chat-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-secondary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .project-name {
            font-size: 1.125rem;
            font-weight: 700;
        }
        
        .download-btn {
            display: none;
            align-items: center;
            gap: 0.5rem;
            padding: 0.625rem 1rem;
            background: linear-gradient(135deg, var(--success), #34D399);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .download-btn:hover {
            transform: translateY(-1px);
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
        }
        
        .message {
            margin-bottom: 1.5rem;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        
        .message-role {
            font-weight: 700;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .user-role { color: var(--text-primary); }
        .ai-role { color: var(--accent); }
        
        .message-content {
            padding: 1rem;
            border-radius: 0.75rem;
            line-height: 1.6;
            font-size: 0.9375rem;
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
            padding: 1.5rem;
            border-top: 1px solid var(--border-color);
            background: var(--bg-secondary);
        }
        
        .input-wrapper {
            position: relative;
        }
        
        #chatInput {
            width: 100%;
            padding: 1rem 4rem 1rem 1rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            color: var(--text-primary);
            font-size: 0.9375rem;
            font-family: inherit;
            resize: none;
            outline: none;
            min-height: 80px;
            max-height: 200px;
            transition: all 0.2s;
        }
        
        #chatInput:focus {
            border-color: var(--accent);
        }
        
        #sendBtn {
            position: absolute;
            right: 0.75rem;
            bottom: 0.75rem;
            width: 40px;
            height: 40px;
            background: var(--gradient);
            color: white;
            border: none;
            border-radius: 0.625rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }
        
        #sendBtn:hover {
            transform: scale(1.05);
        }
        
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
            width: 6px;
            cursor: col-resize;
            background: transparent;
            transition: background 0.2s;
            z-index: 10;
        }
        
        .resize-handle:hover,
        .resize-handle.dragging {
            background: var(--accent);
        }
        
        .preview-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-secondary);
        }
        
        .preview-title {
            font-size: 1rem;
            font-weight: 700;
        }
        
        .preview-content {
            flex: 1;
            overflow: auto;
            padding: 1.5rem;
        }
        
        .preview-frame {
            width: 100%;
            height: 100%;
            border: none;
            border-radius: 0.75rem;
            background: white;
        }
        
        .file-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        
        .file-item {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            overflow: hidden;
        }
        
        .file-header {
            padding: 0.75rem 1rem;
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
            font-size: 0.8125rem;
            font-family: 'Monaco', 'Courier New', monospace;
        }
        
        .file-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }
        
        .file-content.expanded {
            max-height: 500px;
            overflow: auto;
        }
        
        .file-content pre {
            margin: 0;
            padding: 1rem;
            background: var(--bg-primary);
            color: var(--text-secondary);
            font-size: 0.8125rem;
            line-height: 1.5;
            font-family: 'Monaco', 'Courier New', monospace;
        }
        
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-secondary);
            text-align: center;
        }
        
        .empty-icon {
            width: 64px;
            height: 64px;
            background: var(--bg-tertiary);
            border-radius: 1rem;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <div class="sidebar-header">
                <button class="back-btn" onclick="window.location.href='/dashboard'">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="15 18 9 12 15 6"/>
                    </svg>
                    <span>Back</span>
                </button>
            </div>
        </div>

        <div class="chat-main">
            <div class="chat-header">
                <div class="project-name" id="projectName">Loading...</div>
                <button class="download-btn" id="downloadBtn" onclick="downloadProject()">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                    <span>Download</span>
                </button>
            </div>

            <div class="chat-messages" id="chatMessages"></div>

            <div class="chat-input-area">
                <div class="input-wrapper">
                    <textarea id="chatInput" placeholder="Describe what you want to build..."></textarea>
                    <button id="sendBtn" onclick="sendMessage()">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
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
                    <div class="empty-icon">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                    </div>
                    <div style="font-weight: 600; margin-bottom: 0.5rem;">Ready to Build</div>
                    <div style="font-size: 0.875rem;">Your preview will appear here</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/auth';

        const urlParams = new URLSearchParams(window.location.search);
        const projectId = urlParams.get('project');
        if (!projectId) window.location.href = '/dashboard';

        let projectFiles = {};

        async function loadProject() {
            try {
                const response = await fetch('/api/project/' + projectId + '?token=' + token);
                const data = await response.json();
                
                document.getElementById('projectName').textContent = data.name;
                projectFiles = data.files || {};
                
                if (data.chat_history && data.chat_history.length > 0) {
                    for (const msg of data.chat_history) {
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

        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;
            
            addMessageToUI('user', message);
            input.value = '';
            
            const messagesDiv = document.getElementById('chatMessages');
            const aiDiv = document.createElement('div');
            aiDiv.className = 'message ai-message';
            aiDiv.innerHTML = '<div class="message-header"><span class="message-role ai-role">Project-0 AI</span></div><div class="message-content" id="currentResponse"></div>';
            messagesDiv.appendChild(aiDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            
            try {
                const response = await fetch('/api/chat?token=' + token, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({project_id: parseInt(projectId), message})
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

        function addMessageToUI(role, content) {
            const messagesDiv = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + role + '-message';
            const roleLabel = role === 'user' ? 'You' : 'Project-0 AI';
            const roleClass = role === 'user' ? 'user-role' : 'ai-role';
            const contentHtml = role === 'user' ? escapeHtml(content) : marked.parse(content);
            messageDiv.innerHTML = '<div class="message-header"><span class="message-role ' + roleClass + '">' + roleLabel + '</span></div><div class="message-content">' + contentHtml + '</div>';
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function showFiles(files) {
            const preview = document.getElementById('previewContent');
            
            if (files['frontend/index.html']) {
                const iframe = document.createElement('iframe');
                iframe.className = 'preview-frame';
                iframe.srcdoc = files['frontend/index.html'];
                preview.innerHTML = '';
                preview.appendChild(iframe);
            } else {
                let html = '<div class="file-list">';
                for (const [filename, content] of Object.entries(files)) {
                    html += '<div class="file-item"><div class="file-header" onclick="toggleFile(this)"><span class="file-name">' + escapeHtml(filename) + '</span><span>▼</span></div><div class="file-content"><pre><code>' + escapeHtml(content) + '</code></pre></div></div>';
                }
                html += '</div>';
                preview.innerHTML = html;
            }
        }

        function toggleFile(header) {
            const content = header.nextElementSibling;
            const arrow = header.querySelector('span:last-child');
            if (content.classList.contains('expanded')) {
                content.classList.remove('expanded');
                arrow.textContent = '▼';
            } else {
                content.classList.add('expanded');
                arrow.textContent = '▲';
            }
        }

        async function downloadProject() {
            window.location.href = '/api/download/' + projectId + '?token=' + token;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Resizable panel
        (function() {
            const resizeHandle = document.getElementById('resizeHandle');
            const chatPreview = document.getElementById('chatPreview');
            let isDragging = false;
            let startX = 0;
            let startWidth = 0;

            resizeHandle.addEventListener('mousedown', function(e) {
                isDragging = true;
                startX = e.clientX;
                startWidth = chatPreview.offsetWidth;
                resizeHandle.classList.add('dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });

            document.addEventListener('mousemove', function(e) {
                if (!isDragging) return;
                const deltaX = startX - e.clientX;
                const newWidth = startWidth + deltaX;
                const minWidth = 300;
                const maxWidth = window.innerWidth * 0.7;
                if (newWidth >= minWidth && newWidth <= maxWidth) {
                    chatPreview.style.width = newWidth + 'px';
                }
            });

            document.addEventListener('mouseup', function() {
                if (isDragging) {
                    isDragging = false;
                    resizeHandle.classList.remove('dragging');
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }
            });
        })();

        loadProject();

        document.getElementById('chatInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║      🚀 PROJECT-0 PREMIUM SAAS PLATFORM 🚀           ║
    ║                                                       ║
    ║   All-in-One File - Production Ready                 ║
    ║   • Modern SaaS UI Design                            ║
    ║   • SVG Icons (No Emojis)                            ║
    ║   • Smooth Animations                                ║
    ║   • Resizable Preview Panel                          ║
    ║   • Professional Typography                          ║
    ║                                                       ║
    ║   Open: http://localhost:8000                        ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
