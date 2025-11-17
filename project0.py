"""
Project-0: Professional AI MVP Platform
Separate Pages Architecture
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
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

app = FastAPI(title="Project-0", description="Professional AI MVP Platform")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

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
- Error handling

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

### backend/database.js
```javascript
[Database setup]
```

### frontend/index.html
```html
[Complete frontend with Tailwind]
```

### start.sh
```bash
#!/bin/bash
cd backend && npm install && npm start
```

Color palette: #0066FF (blue), #00C853 (green), #FF6D00 (orange)"""

    if project_context:
        base_prompt += f"\n\nPROJECT CONTEXT:\n{project_context}\n\nRemember this context for all requests."
    
    return base_prompt

# Routes

@app.get("/", response_class=HTMLResponse)
async def landing():
    return FileResponse("static/landing.html")

@app.get("/auth", response_class=HTMLResponse)
async def auth():
    return FileResponse("static/auth.html")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return FileResponse("static/dashboard.html")

@app.get("/chat", response_class=HTMLResponse)
async def chat():
    return FileResponse("static/chat.html")

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
    project_context = f"Project Description: {project[1]}\n\nPrevious Context: {project[0]}"
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
            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 Analyzing...'})}\n\n"
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'status', 'content': '🏗️ Designing...'})}\n\n"
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'status', 'content': '⚡ Generating...'})}\n\n"
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
    files = {}
    pattern = r'###\s+([^\n]+)\s*\n```(?:\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    for filename, code in matches:
        filename = filename.strip()
        files[filename] = code.strip()
    files["start.sh"] = "#!/bin/bash\ncd backend\nnpm install\nnpm start"
    files["start.bat"] = "@echo off\ncd backend\nnpm install\nnpm start"
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
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project[0]}.zip"}
    )

@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║      🚀 PROJECT-0 PROFESSIONAL PLATFORM 🚀           ║
    ║                                                       ║
    ║   Separate Pages Architecture                        ║
    ║   • Landing Page                                     ║
    ║   • Authentication                                   ║
    ║   • Dashboard                                        ║
    ║   • Chat with AI                                     ║
    ║                                                       ║
    ║   Open: http://localhost:8000                        ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=8000)
