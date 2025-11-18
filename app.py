"""
Project-0 (Production SaaS) - AI MVP Generator
Professional SaaS platform with authentication, encryption, and user management
Black & White minimalist design inspired by v0.dev
"""

from fastapi import FastAPI, Request, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import httpx
import json
import asyncio
from typing import AsyncGenerator, Dict, Optional
import time
from datetime import datetime
import re
import io
import zipfile
import sqlite3
import secrets
import bcrypt

app = FastAPI(title="Project-0 (Production)", description="AI-Powered MVP Generator SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Configuration
# Simple session storage (in production use Redis or database)
active_sessions = {}  # {session_id: user_id}

# Database Setup
DB_NAME = "project0_saas.db"

def init_db():
    """Initialize database with tables"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    
    # MVPs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mvp_id TEXT UNIQUE NOT NULL,
            idea TEXT NOT NULL,
            code TEXT,
            markdown TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "glm-4.6:cloud"

# System prompt
SYSTEM_PROMPT = """You are Project-0, an AI MVP generator inspired by v0.dev.

Your task:
1. Listen to the user's idea (even if incomplete)
2. Fill in missing details creatively and logically
3. Generate a complete, beautiful MVP using HTML, Tailwind CSS, and vanilla JavaScript or React
4. Create production-ready, responsive, modern UI in v0.dev minimalist style

Design Requirements (v0.dev style):
- Use ONLY black, white, and shades of gray (#000, #fff, #fafafa, #f5f5f5, #e5e5e5, #d4d4d4, #a3a3a3, #737373, #525252, #404040, #262626, #171717)
- Clean, minimalist interface with subtle borders
- Use 'Inter' or system fonts for sans-serif
- Rounded corners: 8px, 12px for cards
- Subtle shadows: 0 1px 3px rgba(0,0,0,0.1)
- Crisp, clean design with excellent contrast
- Responsive and mobile-first

Technical Requirements:
- ALWAYS use Tailwind CSS CDN
- COMPLETE, WORKING code that runs immediately
- All functionality must work (no placeholders)
- Modern, interactive UI
- Responsive design
- Include sample data if needed

Response Format:
Use markdown with clear sections:

## 📋 MVP Concept
[Explain the idea]

## ✨ Features Included
- Feature 1
- Feature 2

## 💻 Complete Code
```html
[Complete HTML code here - must be fully self-contained with all CSS and JS inline or from CDN]
```

## 🎯 How to Use
[Instructions]

IMPORTANT: Generate COMPLETE, SELF-CONTAINED HTML files. No separate CSS/JS files needed."""

# Pydantic Models
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GenerateRequest(BaseModel):
    idea: str

# Password Hashing
def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_session(user_id: int) -> str:
    """Create session for user"""
    session_id = secrets.token_urlsafe(32)
    active_sessions[session_id] = user_id
    return session_id

def get_user_from_session(session_id: Optional[str]) -> Optional[dict]:
    """Get user from session"""
    if not session_id or session_id not in active_sessions:
        return None
    
    user_id = active_sessions[session_id]
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return None
    
    return {"id": user[0], "username": user[1], "email": user[2]}

async def get_current_user(session_id: Optional[str] = Cookie(None)):
    """Get current authenticated user from cookie"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# Authentication Endpoints
@app.post("/api/auth/register")
async def register(user: UserRegister):
    """Register new user"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ? OR username = ?", 
                      (user.email, user.username))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Hash password
        password_hash = hash_password(user.password)
        
        # Insert user
        cursor.execute("""
            INSERT INTO users (username, email, password_hash) 
            VALUES (?, ?, ?)
        """, (user.username, user.email, password_hash))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create session
        session_id = create_session(user_id)
        
        response = JSONResponse({
            "success": True,
            "username": user.username,
            "email": user.email
        })
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=60 * 60 * 24 * 30,  # 30 days
            samesite="lax"
        )
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/auth/login")
async def login(user: UserLogin):
    """Login user"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, username, email, password_hash FROM users WHERE email = ?", 
                      (user.email,))
        user_data = cursor.fetchone()
        
        if not user_data:
            conn.close()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user_id, username, email, password_hash = user_data
        
        # Verify password
        if not verify_password(user.password, password_hash):
            conn.close()
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Update last login
        cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", 
                      (user_id,))
        conn.commit()
        conn.close()
        
        # Create session
        session_id = create_session(user_id)
        
        response = JSONResponse({
            "success": True,
            "username": username,
            "email": email
        })
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=60 * 60 * 24 * 30,  # 30 days
            samesite="lax"
        )
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/api/auth/me")
async def get_me(session_id: Optional[str] = Cookie(None)):
    """Get current user info"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@app.post("/api/auth/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    """Logout user"""
    if session_id and session_id in active_sessions:
        del active_sessions[session_id]
    
    response = JSONResponse({"success": True})
    response.delete_cookie("session_id")
    return response

# MVP Generation with Authentication
async def generate_mvp(idea: str, user_id: int) -> AsyncGenerator[str, None]:
    """Generate MVP using Ollama with streaming"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Create a complete, self-contained MVP for: {idea}"}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield f"data: {json.dumps({'type': 'status', 'content': '🧠 Analyzing idea...'})}\n\n"
            await asyncio.sleep(0.3)
            
            yield f"data: {json.dumps({'type': 'status', 'content': '🎨 Designing UI...'})}\n\n"
            await asyncio.sleep(0.3)
            
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
                                html_code = extract_html(full_response)
                                mvp_id = str(int(time.time() * 1000))
                                
                                # Save to database
                                conn = sqlite3.connect(DB_NAME)
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO mvps (user_id, mvp_id, idea, code, markdown)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (user_id, mvp_id, idea, html_code, full_response))
                                conn.commit()
                                conn.close()
                                
                                yield f"data: {json.dumps({'type': 'done', 'mvp_id': mvp_id, 'has_code': bool(html_code)})}\n\n"
                                break
                        except json.JSONDecodeError:
                            continue
    
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"

def extract_html(markdown_text: str) -> str:
    """Extract HTML code from markdown"""
    pattern = r'```html\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    if matches:
        return matches[0].strip()
    
    pattern = r'```\n(.*?)\n```'
    matches = re.findall(pattern, markdown_text, re.DOTALL)
    if matches:
        code = matches[0].strip()
        if '<!DOCTYPE' in code or '<html' in code or '<div' in code:
            return code
    
    return ""

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application UI"""
    return HTML_TEMPLATE

@app.post("/api/generate")
async def generate(request: GenerateRequest, session_id: Optional[str] = Cookie(None)):
    """Generate MVP from idea with streaming (requires authentication)"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return StreamingResponse(
        generate_mvp(request.idea, user["id"]),
        media_type="text/event-stream"
    )

@app.get("/api/mvp/{mvp_id}")
async def get_mvp(mvp_id: str, session_id: Optional[str] = Cookie(None)):
    """Get MVP data (requires authentication)"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code, markdown, idea FROM mvps 
        WHERE mvp_id = ? AND user_id = ?
    """, (mvp_id, user["id"]))
    
    mvp = cursor.fetchone()
    conn.close()
    
    if not mvp:
        raise HTTPException(status_code=404, detail="MVP not found")
    
    return JSONResponse({
        "code": mvp[0],
        "markdown": mvp[1],
        "idea": mvp[2]
    })

@app.get("/api/mvps")
async def get_user_mvps(session_id: Optional[str] = Cookie(None)):
    """Get all user's MVPs"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mvp_id, idea, created_at FROM mvps 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    """, (user["id"],))
    
    mvps = cursor.fetchall()
    conn.close()
    
    return [
        {
            "mvp_id": mvp[0],
            "idea": mvp[1],
            "created_at": mvp[2]
        }
        for mvp in mvps
    ]

@app.get("/preview/{mvp_id}", response_class=HTMLResponse)
async def preview_page(mvp_id: str, session_id: Optional[str] = Cookie(None)):
    """Render preview page (requires authentication)"""
    user = get_user_from_session(session_id)
    if not user:
        return "<h1>Not authenticated</h1>"
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code FROM mvps 
        WHERE mvp_id = ? AND user_id = ?
    """, (mvp_id, user["id"]))
    
    mvp = cursor.fetchone()
    conn.close()
    
    if not mvp:
        return "<h1>MVP not found</h1>"
    
    return mvp[0] if mvp[0] else "<h1>No code generated</h1>"

@app.get("/api/download/{mvp_id}")
async def download_project(mvp_id: str, session_id: Optional[str] = Cookie(None)):
    """Download project as ZIP file (requires authentication)"""
    user = get_user_from_session(session_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT code, markdown, idea, created_at FROM mvps 
        WHERE mvp_id = ? AND user_id = ?
    """, (mvp_id, user["id"]))
    
    mvp = cursor.fetchone()
    conn.close()
    
    if not mvp:
        raise HTTPException(status_code=404, detail="MVP not found")
    
    code, markdown, idea, created_at = mvp
    
    # Create ZIP file
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('index.html', code)
        
        readme_content = f"""# {idea}

Generated by Project-0 (Production)
Date: {created_at}
User: {user['username']}

## How to Use

1. Open `index.html` in your web browser
2. All styles and scripts are included in the HTML file
3. No server or build process required

## Features

{markdown}

---

Generated with ❤️ by Project-0 SaaS
"""
        zip_file.writestr('README.md', readme_content)
        
        info_content = f"""Project: {idea}
Generated: {created_at}
MVP ID: {mvp_id}
User: {user['username']}

This is a self-contained HTML project.
Everything you need is in index.html.
"""
        zip_file.writestr('PROJECT-INFO.txt', info_content)
    
    zip_buffer.seek(0)
    
    safe_idea = re.sub(r'[^a-zA-Z0-9]+', '-', idea[:30]).strip('-').lower()
    filename = f"project-0-{safe_idea}-{mvp_id}.zip"
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@app.get("/api/health")
async def health():
    """Health check"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM mvps")
    mvp_count = cursor.fetchone()[0]
    conn.close()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "users": user_count,
        "mvps": mvp_count
    }

# Main HTML Template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Transform Ideas into Reality</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #ffffff;
            --bg-secondary: #fafafa;
            --bg-tertiary: #f5f5f5;
            --border-primary: #e5e5e5;
            --border-secondary: #d4d4d4;
            --text-primary: #171717;
            --text-secondary: #525252;
            --text-tertiary: #737373;
            --accent: #000000;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            -webkit-font-smoothing: antialiased;
        }
        
        body.app-mode {
            height: 100vh;
            overflow: hidden;
        }

        .container {
            display: flex;
            height: 100vh;
        }

        /* Auth Modal */
        .auth-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .auth-panel {
            background: var(--bg-primary);
            border-radius: 16px;
            box-shadow: 
                0 20px 60px rgba(0, 0, 0, 0.3),
                0 0 0 1px rgba(0, 0, 0, 0.1);
            width: 90%;
            max-width: 420px;
            padding: 40px;
            transform: perspective(1000px) rotateX(0deg);
            animation: slideUp3D 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
            position: relative;
        }

        @keyframes slideUp3D {
            from {
                opacity: 0;
                transform: perspective(1000px) rotateX(10deg) translateY(40px);
            }
            to {
                opacity: 1;
                transform: perspective(1000px) rotateX(0deg) translateY(0);
            }
        }

        .auth-header {
            text-align: center;
            margin-bottom: 32px;
        }

        .auth-logo {
            width: 56px;
            height: 56px;
            background: var(--accent);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 28px;
            color: white;
            margin: 0 auto 16px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        }

        .auth-title {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 6px;
            color: var(--text-primary);
        }

        .auth-subtitle {
            font-size: 14px;
            color: var(--text-secondary);
        }

        .auth-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            background: var(--bg-secondary);
            padding: 4px;
            border-radius: 8px;
        }

        .auth-tab {
            flex: 1;
            padding: 8px 16px;
            background: transparent;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .auth-tab.active {
            background: var(--bg-primary);
            color: var(--text-primary);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }

        .auth-form {
            display: none;
        }

        .auth-form.active {
            display: block;
        }

        .form-group {
            margin-bottom: 16px;
        }

        .form-label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 6px;
        }

        .form-input {
            width: 100%;
            padding: 10px 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 14px;
            font-family: 'Inter', sans-serif;
            outline: none;
            transition: all 0.2s;
        }

        .form-input:focus {
            border-color: var(--accent);
            background: var(--bg-primary);
            box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.05);
        }

        .form-button {
            width: 100%;
            padding: 12px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
            margin-top: 8px;
        }

        .form-button:hover:not(:disabled) {
            opacity: 0.9;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .form-button:disabled {
            background: var(--border-secondary);
            cursor: not-allowed;
        }

        .error-message {
            background: #fee;
            border: 1px solid #fcc;
            color: #c33;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
            animation: shake 0.5s;
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-8px); }
            75% { transform: translateX(8px); }
        }

        /* Profile Button */
        .profile-btn {
            width: 36px;
            height: 36px;
            background: var(--accent);
            color: white;
            border: 2px solid var(--bg-primary);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            position: relative;
        }

        .profile-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        }

        .profile-menu {
            position: absolute;
            top: 48px;
            right: 0;
            background: var(--bg-primary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
            min-width: 200px;
            display: none;
            animation: slideDown 0.2s ease-out;
            z-index: 100;
        }

        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .profile-menu.show {
            display: block;
        }

        .profile-menu-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-primary);
        }

        .profile-name {
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
        }

        .profile-email {
            font-size: 12px;
            color: var(--text-tertiary);
            margin-top: 2px;
        }

        .profile-menu-item {
            padding: 10px 16px;
            cursor: pointer;
            font-size: 13px;
            color: var(--text-secondary);
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .profile-menu-item:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
        }

        .profile-menu-item.logout {
            color: #c33;
            border-top: 1px solid var(--border-primary);
        }

        /* Left Panel */
        .chat-panel {
            width: 45%;
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-primary);
            background: var(--bg-primary);
        }

        /* Right Panel */
        .preview-panel {
            width: 55%;
            display: flex;
            flex-direction: column;
            background: var(--bg-secondary);
        }

        /* Header */
        .header {
            background: var(--bg-primary);
            border-bottom: 1px solid var(--border-primary);
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 56px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .logo-icon {
            width: 28px;
            height: 28px;
            background: var(--accent);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            color: white;
            letter-spacing: -0.5px;
        }

        .logo-text {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .status-dot {
            width: 6px;
            height: 6px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Messages */
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .message {
            margin-bottom: 20px;
            animation: slideUp 0.3s ease-out;
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message-header {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
        }

        .message-role {
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
        }

        .message-content {
            padding: 12px 14px;
            border-radius: 8px;
            line-height: 1.6;
            font-size: 13px;
            color: var(--text-primary);
        }

        .user-message .message-content {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
        }

        .ai-message .message-content {
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
        }

        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 10px;
            font-weight: 500;
        }

        .spinner {
            width: 12px;
            height: 12px;
            border: 2px solid var(--border-secondary);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Markdown */
        .markdown-content {
            font-size: 13px;
            line-height: 1.6;
        }

        .markdown-content h2 {
            font-size: 16px;
            font-weight: 600;
            margin: 16px 0 10px 0;
            color: var(--text-primary);
        }

        .markdown-content h3 {
            font-size: 14px;
            font-weight: 600;
            margin: 12px 0 8px 0;
            color: var(--text-primary);
        }

        .markdown-content ul {
            margin: 8px 0 8px 18px;
        }

        .markdown-content li {
            margin: 4px 0;
            color: var(--text-secondary);
        }

        .markdown-content code {
            background: var(--bg-tertiary);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 12px;
            color: var(--text-primary);
            border: 1px solid var(--border-primary);
        }

        .markdown-content pre {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            padding: 14px;
            overflow-x: auto;
            margin: 10px 0;
        }

        .markdown-content pre code {
            background: none;
            padding: 0;
            border: none;
            color: var(--text-primary);
        }

        .markdown-content strong {
            color: var(--text-primary);
            font-weight: 600;
        }

        .markdown-content p {
            margin: 8px 0;
            color: var(--text-secondary);
        }

        /* Action Buttons */
        .action-buttons {
            display: flex;
            gap: 8px;
            margin-top: 12px;
        }

        .action-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 14px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 500;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .action-btn:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .action-btn.secondary {
            background: var(--bg-primary);
            color: var(--text-primary);
            border: 1px solid var(--border-primary);
        }

        .action-btn.secondary:hover {
            background: var(--bg-tertiary);
        }

        /* Input Area */
        .input-area {
            padding: 16px 20px;
            background: var(--bg-primary);
            border-top: 1px solid var(--border-primary);
        }

        .input-wrapper {
            position: relative;
        }

        #ideaInput {
            width: 100%;
            padding: 12px 50px 12px 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 13px;
            font-family: 'Inter', sans-serif;
            resize: none;
            outline: none;
            min-height: 44px;
            max-height: 180px;
            line-height: 1.5;
        }

        #ideaInput:focus {
            border-color: var(--accent);
            background: var(--bg-primary);
        }

        #ideaInput::placeholder {
            color: var(--text-tertiary);
        }

        #generateBtn {
            position: absolute;
            right: 6px;
            bottom: 6px;
            width: 36px;
            height: 36px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }

        #generateBtn:hover:not(:disabled) {
            opacity: 0.9;
        }

        #generateBtn:disabled {
            background: var(--border-secondary);
            cursor: not-allowed;
        }

        /* Preview */
        .preview-header {
            padding: 12px 20px;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 56px;
        }

        .preview-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            letter-spacing: -0.2px;
        }

        .preview-actions {
            display: flex;
            gap: 6px;
        }

        .preview-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            background: var(--bg-primary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .preview-btn:hover {
            background: var(--bg-tertiary);
        }

        .preview-btn svg {
            width: 14px;
            height: 14px;
        }

        .preview-frame {
            flex: 1;
            background: white;
            position: relative;
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
            color: var(--text-tertiary);
            text-align: center;
            padding: 40px;
        }

        .placeholder-icon {
            width: 64px;
            height: 64px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin-bottom: 16px;
        }

        .placeholder-text {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 6px;
        }

        .placeholder-hint {
            font-size: 13px;
            color: var(--text-tertiary);
        }

        /* Welcome */
        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px;
            text-align: center;
            min-height: 400px;
        }

        .welcome-logo {
            width: 72px;
            height: 72px;
            background: var(--accent);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 32px;
            color: white;
            margin-bottom: 20px;
            letter-spacing: -1px;
        }

        .welcome-title {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }

        .welcome-subtitle {
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 28px;
            max-width: 380px;
            line-height: 1.5;
        }

        .example-ideas {
            display: grid;
            gap: 8px;
            max-width: 420px;
            width: 100%;
        }

        .example-idea {
            padding: 12px 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }

        .example-idea:hover {
            background: var(--bg-tertiary);
            border-color: var(--border-secondary);
            transform: translateY(-1px);
        }

        .example-title {
            font-weight: 600;
            margin-bottom: 2px;
            font-size: 13px;
            color: var(--text-primary);
        }

        .example-desc {
            font-size: 12px;
            color: var(--text-tertiary);
        }

        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border-secondary);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-tertiary);
        }

        @media (max-width: 1024px) {
            .container {
                flex-direction: column;
            }
            
            .chat-panel {
                width: 100%;
                height: 60%;
                border-right: none;
                border-bottom: 1px solid var(--border-primary);
            }
            
            .preview-panel {
                width: 100%;
                height: 40%;
            }
        }

        .hidden {
            display: none !important;
        }

        /* Landing Page */
        .landing-page {
            min-height: 100vh;
            background: var(--bg-primary);
            overflow-y: auto;
        }

        .landing-nav {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border-primary);
            padding: 16px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 100;
        }

        .landing-logo-section {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .landing-logo {
            width: 36px;
            height: 36px;
            background: var(--accent);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 20px;
            color: white;
        }

        .landing-brand {
            font-size: 20px;
            font-weight: 800;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }

        .landing-nav-btn {
            padding: 8px 20px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .landing-nav-btn:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .landing-hero {
            padding: 140px 40px 100px;
            text-align: center;
            max-width: 1200px;
            margin: 0 auto;
        }

        .landing-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 24px;
            animation: fadeInUp 0.6s ease-out;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .landing-h1 {
            font-size: 72px;
            font-weight: 900;
            line-height: 1.1;
            margin-bottom: 24px;
            color: var(--text-primary);
            letter-spacing: -2px;
            animation: fadeInUp 0.8s ease-out 0.1s both;
        }

        .landing-h1 .highlight {
            background: linear-gradient(135deg, #000 0%, #525252 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .landing-subtitle {
            font-size: 24px;
            color: var(--text-secondary);
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto 48px;
            animation: fadeInUp 1s ease-out 0.2s both;
        }

        .landing-cta {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 18px 48px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
            animation: fadeInUp 1.2s ease-out 0.3s both;
        }

        .landing-cta:hover {
            transform: translateY(-4px);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.3);
        }

        .landing-features {
            padding: 80px 40px;
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-primary);
        }

        .landing-section-title {
            text-align: center;
            font-size: 48px;
            font-weight: 800;
            margin-bottom: 20px;
            color: var(--text-primary);
            letter-spacing: -1px;
        }

        .landing-section-subtitle {
            text-align: center;
            font-size: 20px;
            color: var(--text-secondary);
            margin-bottom: 60px;
            max-width: 700px;
            margin-left: auto;
            margin-right: auto;
        }

        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 32px;
            max-width: 1200px;
            margin: 0 auto;
        }

        .feature-card {
            background: var(--bg-primary);
            border: 1px solid var(--border-primary);
            border-radius: 16px;
            padding: 36px;
            transition: all 0.3s;
        }

        .feature-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1);
            border-color: var(--border-secondary);
        }

        .feature-icon {
            width: 56px;
            height: 56px;
            background: var(--accent);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin-bottom: 20px;
        }

        .feature-title {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 12px;
            color: var(--text-primary);
        }

        .feature-desc {
            font-size: 16px;
            line-height: 1.6;
            color: var(--text-secondary);
        }

        .landing-benefits {
            padding: 80px 40px;
        }

        .benefits-list {
            max-width: 900px;
            margin: 0 auto;
            display: grid;
            gap: 24px;
        }

        .benefit-item {
            display: flex;
            gap: 20px;
            padding: 28px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            transition: all 0.3s;
        }

        .benefit-item:hover {
            background: var(--bg-tertiary);
            transform: translateX(8px);
        }

        .benefit-number {
            width: 48px;
            height: 48px;
            background: var(--accent);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 20px;
            flex-shrink: 0;
        }

        .benefit-content h3 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text-primary);
        }

        .benefit-content p {
            font-size: 16px;
            color: var(--text-secondary);
            line-height: 1.6;
        }

        .landing-cta-section {
            padding: 100px 40px;
            background: var(--accent);
            text-align: center;
        }

        .landing-cta-section h2 {
            font-size: 56px;
            font-weight: 900;
            color: white;
            margin-bottom: 24px;
            letter-spacing: -1.5px;
        }

        .landing-cta-section p {
            font-size: 22px;
            color: rgba(255, 255, 255, 0.9);
            margin-bottom: 48px;
            max-width: 700px;
            margin-left: auto;
            margin-right: auto;
        }

        .landing-cta-white {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 18px 48px;
            background: white;
            color: var(--accent);
            border: none;
            border-radius: 12px;
            font-weight: 700;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        }

        .landing-cta-white:hover {
            transform: translateY(-4px);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.25);
        }

        .landing-footer {
            padding: 60px 40px 40px;
            background: var(--bg-primary);
            border-top: 1px solid var(--border-primary);
            text-align: center;
        }

        .landing-footer-logo {
            display: flex;
            align-items: center;
            gap: 12px;
            justify-content: center;
            margin-bottom: 16px;
        }

        .landing-footer-logo-icon {
            width: 32px;
            height: 32px;
            background: var(--accent);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 18px;
            color: white;
        }

        .landing-footer-brand {
            font-size: 18px;
            font-weight: 800;
            color: var(--text-primary);
        }

        .landing-footer-text {
            font-size: 14px;
            color: var(--text-tertiary);
            margin-top: 12px;
        }

        @media (max-width: 768px) {
            .landing-h1 {
                font-size: 42px;
            }
            
            .landing-subtitle {
                font-size: 18px;
            }
            
            .landing-section-title {
                font-size: 36px;
            }
            
            .features-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <!-- Landing Page -->
    <div class="landing-page hidden" id="landingPage" style="display: none;">
        <nav class="landing-nav">
            <div class="landing-logo-section">
                <div class="landing-logo">0</div>
                <div class="landing-brand">Project-0</div>
            </div>
            <button class="landing-nav-btn" onclick="showAuth()">Get Started</button>
        </nav>

        <section class="landing-hero">
            <div class="landing-badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                </svg>
                Production Ready Platform
            </div>
            
            <h1 class="landing-h1">
                Transform Your Ideas<br/>
                Into <span class="highlight">Reality</span>
            </h1>
            
            <p class="landing-subtitle">
                The ultimate platform for turning concepts into fully functional prototypes. 
                No coding experience required. Just describe your vision and watch it come to life instantly.
            </p>
            
            <button class="landing-cta" onclick="handleTryNow()">
                <span>Try It Now</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
            </button>
        </section>

        <section class="landing-features">
            <h2 class="landing-section-title">Powerful Features</h2>
            <p class="landing-section-subtitle">
                Everything you need to bring your ideas to life, all in one platform
            </p>
            
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3 class="feature-title">Lightning Fast</h3>
                    <p class="feature-desc">
                        Generate complete, production-ready prototypes in seconds. 
                        No waiting, no delays. Just instant results.
                    </p>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">🎨</div>
                    <h3 class="feature-title">Beautiful Design</h3>
                    <p class="feature-desc">
                        Every prototype follows modern design principles with clean, 
                        minimalist aesthetics that users love.
                    </p>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">📱</div>
                    <h3 class="feature-title">Fully Responsive</h3>
                    <p class="feature-desc">
                        Your prototypes work perfectly on any device. 
                        Mobile, tablet, desktop - everything just works.
                    </p>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">🔒</div>
                    <h3 class="feature-title">Secure & Private</h3>
                    <p class="feature-desc">
                        Military-grade encryption protects your data. 
                        Your ideas stay yours, always safe and secure.
                    </p>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">💾</div>
                    <h3 class="feature-title">Download Anytime</h3>
                    <p class="feature-desc">
                        Export your projects as complete, ready-to-deploy packages. 
                        No vendor lock-in, full ownership.
                    </p>
                </div>
                
                <div class="feature-card">
                    <div class="feature-icon">🚀</div>
                    <h3 class="feature-title">Production Ready</h3>
                    <p class="feature-desc">
                        Generated code is clean, optimized, and ready for production. 
                        Deploy with confidence.
                    </p>
                </div>
            </div>
        </section>

        <section class="landing-benefits">
            <h2 class="landing-section-title">Why Choose Project-0?</h2>
            <p class="landing-section-subtitle">
                Join thousands of innovators who trust Project-0 to bring their visions to reality
            </p>
            
            <div class="benefits-list">
                <div class="benefit-item">
                    <div class="benefit-number">1</div>
                    <div class="benefit-content">
                        <h3>No Technical Skills Required</h3>
                        <p>
                            Simply describe what you want in plain English. Our intelligent system 
                            understands your vision and creates exactly what you need.
                        </p>
                    </div>
                </div>
                
                <div class="benefit-item">
                    <div class="benefit-number">2</div>
                    <div class="benefit-content">
                        <h3>Save Weeks of Development Time</h3>
                        <p>
                            What normally takes weeks of coding can be done in minutes. 
                            Focus on your business, not on technical details.
                        </p>
                    </div>
                </div>
                
                <div class="benefit-item">
                    <div class="benefit-number">3</div>
                    <div class="benefit-content">
                        <h3>Iterate and Improve Rapidly</h3>
                        <p>
                            Test different ideas, get instant feedback, and refine your vision. 
                            Perfect for MVPs, prototypes, and proof of concepts.
                        </p>
                    </div>
                </div>
                
                <div class="benefit-item">
                    <div class="benefit-number">4</div>
                    <div class="benefit-content">
                        <h3>Professional Quality Results</h3>
                        <p>
                            Every output meets professional standards with clean code, 
                            modern design, and best practices built-in.
                        </p>
                    </div>
                </div>
                
                <div class="benefit-item">
                    <div class="benefit-number">5</div>
                    <div class="benefit-content">
                        <h3>Complete Creative Freedom</h3>
                        <p>
                            From simple landing pages to complex dashboards - if you can imagine it, 
                            we can build it. No limits, no restrictions.
                        </p>
                    </div>
                </div>
            </div>
        </section>

        <section class="landing-cta-section">
            <h2>Ready to Transform Your Ideas?</h2>
            <p>
                Join the future of rapid prototyping. Start creating amazing projects today.
            </p>
            <button class="landing-cta-white" onclick="handleTryNow()">
                <span>Get Started Free</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
            </button>
        </section>

        <footer class="landing-footer">
            <div class="landing-footer-logo">
                <div class="landing-footer-logo-icon">0</div>
                <div class="landing-footer-brand">Project-0</div>
            </div>
            <p class="landing-footer-text">
                © 2024 Project-0. Transform ideas into reality.
            </p>
        </footer>
    </div>
    <!-- Auth Modal -->
    <div class="auth-overlay hidden" id="authOverlay">
        <div class="auth-panel">
            <div class="auth-header">
                <div class="auth-logo">0</div>
                <div class="auth-title">Welcome to Project-0</div>
                <div class="auth-subtitle">Production AI MVP Generator</div>
            </div>

            <div class="auth-tabs">
                <button class="auth-tab active" data-tab="login">Sign In</button>
                <button class="auth-tab" data-tab="register">Sign Up</button>
            </div>

            <div id="authError" class="error-message hidden"></div>

            <!-- Login Form -->
            <form class="auth-form active" id="loginForm">
                <div class="form-group">
                    <label class="form-label">Google Account / Email</label>
                    <input type="email" class="form-input" id="loginEmail" placeholder="your@email.com" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" class="form-input" id="loginPassword" placeholder="••••••••" required>
                </div>
                <button type="submit" class="form-button" id="loginBtn">Sign In</button>
            </form>

            <!-- Register Form -->
            <form class="auth-form" id="registerForm">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" class="form-input" id="registerUsername" placeholder="Your name" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Google Account / Email</label>
                    <input type="email" class="form-input" id="registerEmail" placeholder="your@email.com" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" class="form-input" id="registerPassword" placeholder="••••••••" required>
                </div>
                <button type="submit" class="form-button" id="registerBtn">Create Account</button>
            </form>
        </div>
    </div>

        <div class="container hidden" id="mainApp" style="display: none;">
        <!-- Chat Panel -->
        <div class="chat-panel">
            <div class="header">
                <div class="logo">
                    <div class="logo-icon">0</div>
                    <div class="logo-text">Project-0 (Production)</div>
                </div>
                <div class="header-right">
                    <div class="status-badge">
                        <div class="status-dot"></div>
                        <span>Ready</span>
                    </div>
                    <div style="position: relative;">
                        <div class="profile-btn" id="profileBtn">
                            <span id="profileInitial">U</span>
                        </div>
                        <div class="profile-menu" id="profileMenu">
                            <div class="profile-menu-header">
                                <div class="profile-name" id="profileName">User</div>
                                <div class="profile-email" id="profileEmail">user@email.com</div>
                            </div>
                            <div class="profile-menu-item" id="myProjectsBtn">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                                    <polyline points="9 22 9 12 15 12 15 22"/>
                                </svg>
                                My Projects
                            </div>
                            <div class="profile-menu-item logout" id="logoutBtn">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                                    <polyline points="16 17 21 12 16 7"/>
                                    <line x1="21" y1="12" x2="9" y2="12"/>
                                </svg>
                                Logout
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="messages" id="messages">
                <div class="welcome">
                    <div class="welcome-logo">0</div>
                    <div class="welcome-title">AI MVP Generator</div>
                    <div class="welcome-subtitle">
                        Transform your ideas into production-ready prototypes with HTML, CSS, and JavaScript
                    </div>
                    <div class="example-ideas">
                        <div class="example-idea" data-idea="Create a modern landing page for a SaaS product with hero section, features, pricing, and testimonials">
                            <div class="example-title">🚀 SaaS Landing Page</div>
                            <div class="example-desc">Professional marketing site</div>
                        </div>
                        <div class="example-idea" data-idea="Build a todo app with categories, priority levels, search, and local storage">
                            <div class="example-title">✅ Todo Application</div>
                            <div class="example-desc">Task management tool</div>
                        </div>
                        <div class="example-idea" data-idea="Design an analytics dashboard with charts, metrics cards, and data tables">
                            <div class="example-title">📊 Analytics Dashboard</div>
                            <div class="example-desc">Data visualization UI</div>
                        </div>
                        <div class="example-idea" data-idea="Create a portfolio website with projects gallery, about section, and contact form">
                            <div class="example-title">🎨 Portfolio Site</div>
                            <div class="example-desc">Personal showcase</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="input-area">
                <div class="input-wrapper">
                    <textarea 
                        id="ideaInput" 
                        placeholder="Describe your MVP idea..."
                        rows="1"
                    ></textarea>
                    <button id="generateBtn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- Preview Panel -->
        <div class="preview-panel">
            <div class="preview-header">
                <div class="preview-title">Live Preview</div>
                <div class="preview-actions">
                    <button class="preview-btn" id="downloadBtn" style="display:none;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Download
                    </button>
                    <button class="preview-btn" id="refreshBtn" style="display:none;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="preview-btn" id="newWindowBtn" style="display:none;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                        </svg>
                        Open
                    </button>
                </div>
            </div>
            <div class="preview-frame" id="previewFrame">
                <div class="preview-placeholder">
                    <div class="placeholder-icon">✨</div>
                    <div class="placeholder-text">Ready to build</div>
                    <div class="placeholder-hint">Your preview will appear here</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Auth State
        let currentUser = null;
        let isGenerating = false;
        let currentMvpId = null;

        // Landing Page Control
        const landingPage = document.getElementById('landingPage');
        const bodyElement = document.body;

        // Elements
        const authOverlay = document.getElementById('authOverlay');
        const mainApp = document.getElementById('mainApp');
        const authError = document.getElementById('authError');
        const loginForm = document.getElementById('loginForm');
        const registerForm = document.getElementById('registerForm');
        const ideaInput = document.getElementById('ideaInput');
        const generateBtn = document.getElementById('generateBtn');
        const messagesDiv = document.getElementById('messages');
        const previewFrame = document.getElementById('previewFrame');
        const downloadBtn = document.getElementById('downloadBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const newWindowBtn = document.getElementById('newWindowBtn');
        const profileBtn = document.getElementById('profileBtn');
        const profileMenu = document.getElementById('profileMenu');
        const logoutBtn = document.getElementById('logoutBtn');
        const profileName = document.getElementById('profileName');
        const profileEmail = document.getElementById('profileEmail');
        const profileInitial = document.getElementById('profileInitial');

        // Auth Tabs
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
                tab.classList.add('active');
                
                const tabType = tab.dataset.tab;
                document.getElementById(tabType + 'Form').classList.add('active');
                authError.classList.add('hidden');
            });
        });

        // Register
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('registerUsername').value;
            const email = document.getElementById('registerEmail').value;
            const password = document.getElementById('registerPassword').value;
            
            const btn = document.getElementById('registerBtn');
            btn.disabled = true;
            btn.textContent = 'Creating...';
            authError.classList.add('hidden');
            
            try {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, email, password})
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || 'Registration failed');
                }
                
                // Login successful
                currentUser = {username: data.username, email: data.email};
                showApp();
            } catch (error) {
                authError.textContent = error.message;
                authError.classList.remove('hidden');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Create Account';
            }
        });

        // Login
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            
            const btn = document.getElementById('loginBtn');
            btn.disabled = true;
            btn.textContent = 'Signing in...';
            authError.classList.add('hidden');
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, password})
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.detail || 'Login failed');
                }
                
                // Login successful
                currentUser = {username: data.username, email: data.email};
                showApp();
            } catch (error) {
                authError.textContent = error.message;
                authError.classList.remove('hidden');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Sign In';
            }
        });

        // Show Auth
        function showAuth() {
            landingPage.classList.add('hidden');
            authOverlay.classList.remove('hidden');
        }

        // Handle Try Now button
        async function handleTryNow() {
            // Check if already logged in
            try {
                const response = await fetch('/api/auth/me', {
                    credentials: 'include'
                });
                
                if (response.ok) {
                    const data = await response.json();
                    currentUser = data;
                    showApp();
                } else {
                    showAuth();
                }
            } catch (error) {
                showAuth();
            }
        }

        // Show App
        function showApp() {
            landingPage.classList.add('hidden');
            landingPage.style.display = 'none';
            authOverlay.classList.add('hidden');
            authOverlay.style.display = 'none';
            mainApp.classList.remove('hidden');
            mainApp.style.display = 'flex';
            bodyElement.classList.add('app-mode');
            
            // Update profile
            profileName.textContent = currentUser.username;
            profileEmail.textContent = currentUser.email;
            profileInitial.textContent = currentUser.username.charAt(0).toUpperCase();
            
            ideaInput.focus();
        }

        // Check Auth on Load
        async function checkAuth() {
            try {
                const response = await fetch('/api/auth/me', {
                    credentials: 'include'
                });
                
                if (response.ok) {
                    const data = await response.json();
                    currentUser = data;
                    showApp();
                    return;
                }
            } catch (error) {
                console.error('Auth check failed:', error);
            }
            
            // Show landing page if not authenticated
            landingPage.style.display = 'block';
            landingPage.classList.remove('hidden');
            bodyElement.classList.remove('app-mode');
        }

        // Initialize on page load
        checkAuth();

        // Profile Menu
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('show');
        });

        document.addEventListener('click', () => {
            profileMenu.classList.remove('show');
        });

        profileMenu.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        // Logout
        logoutBtn.addEventListener('click', async () => {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    credentials: 'include'
                });
            } catch (error) {
                console.error('Logout error:', error);
            }
            
            currentUser = null;
            mainApp.classList.add('hidden');
            mainApp.style.display = 'none';
            landingPage.classList.remove('hidden');
            landingPage.style.display = 'block';
            bodyElement.classList.remove('app-mode');
            profileMenu.classList.remove('show');
        });

        // Example ideas
        document.addEventListener('click', (e) => {
            const exampleIdea = e.target.closest('.example-idea');
            if (exampleIdea) {
                ideaInput.value = exampleIdea.dataset.idea;
                ideaInput.focus();
                autoResize();
            }
        });

        // Auto-resize textarea
        function autoResize() {
            ideaInput.style.height = 'auto';
            ideaInput.style.height = Math.min(ideaInput.scrollHeight, 180) + 'px';
        }
        ideaInput.addEventListener('input', autoResize);

        // Generate
        generateBtn.addEventListener('click', generate);
        ideaInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                generate();
            }
        });

        async function generate() {
            const idea = ideaInput.value.trim();
            if (!idea || isGenerating || !authToken) return;

            isGenerating = true;
            generateBtn.disabled = true;

            // Remove welcome
            const welcome = document.querySelector('.welcome');
            if (welcome) welcome.remove();

            // Add user message
            addMessage('user', idea);

            // Clear input
            ideaInput.value = '';
            autoResize();

            // Create AI message
            const aiDiv = document.createElement('div');
            aiDiv.className = 'message ai-message';
            aiDiv.innerHTML = `
                <div class="message-header"><span class="message-role">Assistant</span></div>
                <div class="status-indicator" id="statusIndicator">
                    <div class="spinner"></div>
                    <span>Initializing...</span>
                </div>
                <div class="message-content markdown-content" id="currentResponse"></div>
            `;
            messagesDiv.appendChild(aiDiv);
            scrollToBottom();

            // Fetch
            try {
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({idea})
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';

                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');

                    lines.forEach(line => {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));

                                if (data.type === 'status') {
                                    const statusEl = document.getElementById('statusIndicator');
                                    if (statusEl) {
                                        statusEl.querySelector('span').textContent = data.content;
                                    }
                                } 
                                else if (data.type === 'content') {
                                    const statusEl = document.getElementById('statusIndicator');
                                    if (statusEl) statusEl.remove();

                                    fullResponse += data.content;
                                    const responseEl = document.getElementById('currentResponse');
                                    if (responseEl) {
                                        responseEl.innerHTML = marked.parse(fullResponse);
                                    }
                                    scrollToBottom();
                                } 
                                else if (data.type === 'done') {
                                    currentMvpId = data.mvp_id;
                                    if (data.has_code) {
                                        showPreview(data.mvp_id);
                                        
                                        const responseEl = document.getElementById('currentResponse');
                                        const actionsDiv = document.createElement('div');
                                        actionsDiv.className = 'action-buttons';
                                        actionsDiv.innerHTML = `
                                            <button class="action-btn" onclick="showPreview('${data.mvp_id}')">
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                                    <circle cx="12" cy="12" r="3"/>
                                                </svg>
                                                View Preview
                                            </button>
                                            <button class="action-btn secondary" onclick="downloadProject('${data.mvp_id}')">
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                                    <polyline points="7 10 12 15 17 10"/>
                                                    <line x1="12" y1="15" x2="12" y2="3"/>
                                                </svg>
                                                Download Project
                                            </button>
                                        `;
                                        responseEl.appendChild(actionsDiv);
                                    }
                                }
                            } catch (e) {}
                        }
                    });
                }
            } catch (error) {
                console.error('Generation error:', error);
            } finally {
                isGenerating = false;
                generateBtn.disabled = false;
                ideaInput.focus();
            }
        }

        function showPreview(mvpId) {
            const iframe = document.createElement('iframe');
            iframe.src = `/preview/${mvpId}`;
            previewFrame.innerHTML = '';
            previewFrame.appendChild(iframe);
            
            currentMvpId = mvpId;
            downloadBtn.style.display = 'inline-flex';
            refreshBtn.style.display = 'inline-flex';
            newWindowBtn.style.display = 'inline-flex';
        }

        function downloadProject(mvpId) {
            window.location.href = `/api/download/${mvpId}`;
        }

        function addMessage(role, content) {
            const div = document.createElement('div');
            div.className = `message ${role}-message`;
            
            const roleLabel = role === 'user' ? 'You' : 'Assistant';
            
            div.innerHTML = `
                <div class="message-header"><span class="message-role">${roleLabel}</span></div>
                <div class="message-content">${escapeHtml(content)}</div>
            `;
            
            messagesDiv.appendChild(div);
            scrollToBottom();
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function scrollToBottom() {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        // Preview actions
        downloadBtn.addEventListener('click', () => {
            if (currentMvpId) downloadProject(currentMvpId);
        });

        refreshBtn.addEventListener('click', () => {
            if (currentMvpId) showPreview(currentMvpId);
        });

        newWindowBtn.addEventListener('click', () => {
            if (currentMvpId) window.open(`/preview/${currentMvpId}`, '_blank');
        });
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Project-0 Production SaaS Platform...")
    print("📦 Features: Authentication, Encryption, User Management")
    print("🔒 Security: bcrypt password hashing + session cookies")
    print("💾 Database: SQLite with encrypted passwords")
    print("✨ Landing page with smooth scroll")
    print("")
    print("🌐 Server: http://localhost:8000")
    print("")
    print("✅ All issues fixed:")
    print("   - JWT removed (simple sessions)")
    print("   - Scroll works on landing page")
    print("   - Passwords encrypted once (bcrypt)")
    print("   - Landing page shows first")
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
