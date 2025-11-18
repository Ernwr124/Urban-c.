"""
Project-0 (Production SaaS) - AI MVP Generator
Simple session-based authentication with beautiful landing page
"""

from fastapi import FastAPI, Request, Depends, HTTPException, Cookie, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
import hashlib
import secrets
from contextlib import contextmanager

app = FastAPI(title="Project-0", description="AI-Powered MVP Generator")

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
DATABASE_NAME = "project_zero.db"

# System prompt for MVP generation
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

# ==================== DATABASE ====================

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize database with users table"""
    with get_db() as conn:
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      email TEXT UNIQUE NOT NULL,
                      password_hash TEXT NOT NULL,
                      session_token TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      last_login TIMESTAMP)''')
        
        # MVPs table
        c.execute('''CREATE TABLE IF NOT EXISTS mvps
                     (id TEXT PRIMARY KEY,
                      user_id INTEGER NOT NULL,
                      idea TEXT NOT NULL,
                      code TEXT NOT NULL,
                      markdown TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users (id))''')
        
        conn.commit()

init_database()

# ==================== SECURITY ====================

def hash_password(password: str) -> str:
    """Hash password with SHA256 and salt"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{pwd_hash}"

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    try:
        salt, pwd_hash = password_hash.split(':')
        return hashlib.sha256((password + salt).encode()).hexdigest() == pwd_hash
    except:
        return False

def create_session_token() -> str:
    """Create simple session token"""
    return secrets.token_urlsafe(32)

# ==================== MODELS ====================

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GenerateRequest(BaseModel):
    idea: str

# ==================== AUTH ====================

async def get_current_user(session_token: Optional[str] = Cookie(None)):
    """Get current user from session token"""
    if not session_token:
        return None
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE session_token = ?", (session_token,))
        user = c.fetchone()
        return dict(user) if user else None

@app.post("/api/auth/register")
async def register(data: RegisterRequest, response: Response):
    """Register new user"""
    try:
        with get_db() as conn:
            c = conn.cursor()
            
            # Check if user exists
            c.execute("SELECT id FROM users WHERE email = ? OR username = ?", 
                     (data.email, data.username))
            if c.fetchone():
                return JSONResponse({"error": "User already exists"}, status_code=400)
            
            # Create user
            password_hash = hash_password(data.password)
            session_token = create_session_token()
            
            c.execute("""INSERT INTO users (username, email, password_hash, session_token, last_login) 
                        VALUES (?, ?, ?, ?, ?)""",
                     (data.username, data.email, password_hash, session_token, datetime.now()))
            conn.commit()
            
            user_id = c.lastrowid
            
            # Set cookie
            response = JSONResponse({
                "success": True,
                "user": {
                    "id": user_id,
                    "username": data.username,
                    "email": data.email
                }
            })
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                max_age=30*24*60*60,
                samesite="lax"
            )
            return response
            
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response):
    """Login user"""
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE email = ?", (data.email,))
            user = c.fetchone()
            
            if not user or not verify_password(data.password, user["password_hash"]):
                return JSONResponse({"error": "Invalid credentials"}, status_code=401)
            
            # Create new session token
            session_token = create_session_token()
            c.execute("UPDATE users SET session_token = ?, last_login = ? WHERE id = ?", 
                     (session_token, datetime.now(), user["id"]))
            conn.commit()
            
            response = JSONResponse({
                "success": True,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"]
                }
            })
            response.set_cookie(
                key="session_token",
                value=session_token,
                httponly=True,
                max_age=30*24*60*60,
                samesite="lax"
            )
            return response
            
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/auth/logout")
async def logout(user = Depends(get_current_user)):
    """Logout user"""
    if user:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET session_token = NULL WHERE id = ?", (user["id"],))
            conn.commit()
    
    response = JSONResponse({"success": True})
    response.delete_cookie("session_token")
    return response

@app.get("/api/auth/me")
async def get_me(user = Depends(get_current_user)):
    """Get current user info"""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    return JSONResponse({
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "created_at": user["created_at"],
        "last_login": user["last_login"]
    })

# ==================== MVP GENERATION ====================

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
                                
                                with get_db() as conn:
                                    c = conn.cursor()
                                    c.execute("""INSERT INTO mvps (id, user_id, idea, code, markdown) 
                                                VALUES (?, ?, ?, ?, ?)""",
                                            (mvp_id, user_id, idea, html_code, full_response))
                                    conn.commit()
                                
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

@app.post("/api/generate")
async def generate(request: GenerateRequest, user = Depends(get_current_user)):
    """Generate MVP from idea with streaming"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return StreamingResponse(
        generate_mvp(request.idea, user["id"]),
        media_type="text/event-stream"
    )

@app.get("/api/mvp/{mvp_id}")
async def get_mvp(mvp_id: str, user = Depends(get_current_user)):
    """Get MVP data"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM mvps WHERE id = ? AND user_id = ?", 
                 (mvp_id, user["id"]))
        mvp = c.fetchone()
        
        if not mvp:
            return JSONResponse({"error": "MVP not found"}, status_code=404)
        
        return JSONResponse({
            "code": mvp["code"],
            "markdown": mvp["markdown"],
            "idea": mvp["idea"]
        })

@app.get("/preview/{mvp_id}", response_class=HTMLResponse)
async def preview_page(mvp_id: str, user = Depends(get_current_user)):
    """Render preview page"""
    if not user:
        return "<h1>Not authenticated</h1>"
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM mvps WHERE id = ? AND user_id = ?", 
                 (mvp_id, user["id"]))
        mvp = c.fetchone()
        
        if not mvp:
            return "<h1>MVP not found</h1>"
        
        return mvp["code"] if mvp["code"] else "<h1>No code generated</h1>"

@app.get("/api/download/{mvp_id}")
async def download_project(mvp_id: str, user = Depends(get_current_user)):
    """Download project as ZIP file"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM mvps WHERE id = ? AND user_id = ?", 
                 (mvp_id, user["id"]))
        mvp = c.fetchone()
        
        if not mvp:
            return JSONResponse({"error": "MVP not found"}, status_code=404)
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('index.html', mvp["code"])
            
            readme_content = f"""# {mvp["idea"]}

Generated by Project-0
Date: {mvp["created_at"]}

## How to Use

1. Open `index.html` in your web browser
2. All styles and scripts are included in the HTML file
3. No server or build process required

## Features

{mvp["markdown"]}

---

Generated with ❤️ by Project-0
"""
            zip_file.writestr('README.md', readme_content)
        
        zip_buffer.seek(0)
        
        safe_idea = re.sub(r'[^a-zA-Z0-9]+', '-', mvp["idea"][:30]).strip('-').lower()
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
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as count FROM mvps")
        mvp_count = c.fetchone()["count"]
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "total_mvps": mvp_count
    }

# ==================== FRONTEND ====================

@app.get("/", response_class=HTMLResponse)
async def root(session_token: Optional[str] = Cookie(None)):
    """Serve landing page or app based on auth status"""
    user = None
    if session_token:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE session_token = ?", (session_token,))
            user_row = c.fetchone()
            if user_row:
                user = dict(user_row)
    
    if user:
        return APP_TEMPLATE
    else:
        return LANDING_TEMPLATE

# ==================== LANDING PAGE ====================

LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - Transform Ideas Into Reality</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --black: #000000;
            --white: #ffffff;
            --gray-50: #fafafa;
            --gray-100: #f5f5f5;
            --gray-200: #e5e5e5;
            --gray-300: #d4d4d4;
            --gray-400: #a3a3a3;
            --gray-500: #737373;
            --gray-600: #525252;
            --gray-700: #404040;
            --gray-800: #262626;
            --gray-900: #171717;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--black);
            color: var(--white);
            overflow-x: hidden;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* Animated Background */
        .bg-animated {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            overflow: hidden;
        }

        .bg-gradient {
            position: absolute;
            width: 800px;
            height: 800px;
            border-radius: 50%;
            filter: blur(100px);
            opacity: 0.15;
            animation: float 20s ease-in-out infinite;
        }

        .bg-gradient-1 {
            background: radial-gradient(circle, var(--white) 0%, transparent 70%);
            top: -200px;
            left: -200px;
            animation-delay: 0s;
        }

        .bg-gradient-2 {
            background: radial-gradient(circle, var(--white) 0%, transparent 70%);
            bottom: -200px;
            right: -200px;
            animation-delay: 10s;
        }

        @keyframes float {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(100px, -100px) scale(1.1); }
            66% { transform: translate(-100px, 100px) scale(0.9); }
        }

        /* Header */
        .header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 100;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            animation: slideDown 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-100%);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: var(--white);
            transition: transform 0.3s ease;
        }

        .logo:hover {
            transform: translateX(5px);
        }

        .logo-icon {
            width: 40px;
            height: 40px;
            background: var(--white);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 22px;
            color: var(--black);
            letter-spacing: -2px;
        }

        .logo-text {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -1px;
        }

        .header-btn {
            padding: 12px 28px;
            background: var(--white);
            color: var(--black);
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-family: 'Inter', sans-serif;
        }

        .header-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 20px 60px rgba(255, 255, 255, 0.3);
        }

        /* Hero Section */
        .hero {
            position: relative;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 120px 40px 80px;
        }

        .hero-content {
            max-width: 1000px;
            position: relative;
            z-index: 1;
        }

        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 20px;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 100px;
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 32px;
            animation: fadeInUp 0.8s ease-out 0.2s backwards;
        }

        .hero-title {
            font-size: 80px;
            font-weight: 900;
            letter-spacing: -3px;
            line-height: 1.1;
            margin-bottom: 24px;
            background: linear-gradient(to bottom, var(--white), var(--gray-400));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: fadeInUp 0.8s ease-out 0.3s backwards;
        }

        .hero-subtitle {
            font-size: 22px;
            color: var(--gray-400);
            max-width: 700px;
            margin: 0 auto 48px;
            line-height: 1.6;
            font-weight: 400;
            animation: fadeInUp 0.8s ease-out 0.4s backwards;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(40px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .cta-buttons {
            display: flex;
            gap: 16px;
            justify-content: center;
            flex-wrap: wrap;
            animation: fadeInUp 0.8s ease-out 0.5s backwards;
        }

        .cta-primary {
            padding: 18px 48px;
            background: var(--white);
            color: var(--black);
            border: none;
            border-radius: 12px;
            font-weight: 800;
            font-size: 17px;
            cursor: pointer;
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            font-family: 'Inter', sans-serif;
            box-shadow: 0 10px 40px rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        }

        .cta-primary:before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            background: var(--gray-200);
            border-radius: 50%;
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }

        .cta-primary:hover:before {
            width: 300px;
            height: 300px;
        }

        .cta-primary:hover {
            transform: translateY(-4px);
            box-shadow: 0 30px 80px rgba(255, 255, 255, 0.4);
        }

        .cta-primary span {
            position: relative;
            z-index: 1;
        }

        .cta-secondary {
            padding: 18px 48px;
            background: transparent;
            color: var(--white);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px;
            font-weight: 700;
            font-size: 17px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }

        .cta-secondary:hover {
            border-color: var(--white);
            background: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
        }

        /* Features Section */
        .features {
            position: relative;
            padding: 120px 40px;
            background: linear-gradient(180deg, var(--black) 0%, var(--gray-900) 100%);
        }

        .features-container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .section-title {
            text-align: center;
            font-size: 48px;
            font-weight: 900;
            letter-spacing: -2px;
            margin-bottom: 16px;
            background: linear-gradient(to bottom, var(--white), var(--gray-500));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .section-subtitle {
            text-align: center;
            font-size: 18px;
            color: var(--gray-400);
            margin-bottom: 80px;
        }

        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 32px;
        }

        .feature-card {
            padding: 40px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }

        .feature-card:before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--white), transparent);
            opacity: 0;
            transition: opacity 0.5s;
        }

        .feature-card:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.3);
            transform: translateY(-8px);
        }

        .feature-card:hover:before {
            opacity: 0.5;
        }

        .feature-icon {
            width: 60px;
            height: 60px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin-bottom: 24px;
            transition: all 0.5s;
        }

        .feature-card:hover .feature-icon {
            background: var(--white);
            transform: scale(1.1) rotate(5deg);
        }

        .feature-title {
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 12px;
            letter-spacing: -0.5px;
        }

        .feature-desc {
            color: var(--gray-400);
            font-size: 15px;
            line-height: 1.7;
        }

        /* Stats Section */
        .stats {
            padding: 100px 40px;
            background: var(--black);
        }

        .stats-grid {
            max-width: 1000px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 60px;
            text-align: center;
        }

        .stat-item {
            animation: fadeInUp 1s ease-out backwards;
        }

        .stat-number {
            font-size: 56px;
            font-weight: 900;
            letter-spacing: -2px;
            background: linear-gradient(135deg, var(--white), var(--gray-500));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }

        .stat-label {
            color: var(--gray-400);
            font-size: 16px;
            font-weight: 600;
        }

        /* CTA Section */
        .cta-section {
            padding: 120px 40px;
            background: linear-gradient(180deg, var(--black) 0%, var(--gray-900) 100%);
            text-align: center;
        }

        .cta-box {
            max-width: 800px;
            margin: 0 auto;
            padding: 80px 60px;
            background: var(--white);
            color: var(--black);
            border-radius: 30px;
            position: relative;
            overflow: hidden;
        }

        .cta-box:before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: linear-gradient(45deg, transparent, rgba(0,0,0,0.05), transparent);
            animation: shine 3s infinite;
        }

        @keyframes shine {
            0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
            100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
        }

        .cta-box-title {
            font-size: 42px;
            font-weight: 900;
            letter-spacing: -2px;
            margin-bottom: 16px;
            position: relative;
        }

        .cta-box-subtitle {
            font-size: 18px;
            color: var(--gray-600);
            margin-bottom: 40px;
            position: relative;
        }

        .cta-box-btn {
            padding: 20px 60px;
            background: var(--black);
            color: var(--white);
            border: none;
            border-radius: 14px;
            font-weight: 800;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
            position: relative;
        }

        .cta-box-btn:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
        }

        /* Footer */
        .footer {
            padding: 60px 40px;
            background: var(--black);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
        }

        .footer-text {
            color: var(--gray-500);
            font-size: 14px;
        }

        /* Auth Modal */
        .auth-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.9);
            backdrop-filter: blur(20px);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .auth-modal.active {
            display: flex;
        }

        .auth-panel {
            background: var(--white);
            color: var(--black);
            padding: 60px;
            border-radius: 30px;
            max-width: 480px;
            width: 90%;
            box-shadow: 0 50px 100px rgba(0, 0, 0, 0.8);
            animation: modalSlide 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            position: relative;
        }

        @keyframes modalSlide {
            from {
                opacity: 0;
                transform: translateY(60px) scale(0.9);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }

        .close-modal {
            position: absolute;
            top: 24px;
            right: 24px;
            width: 40px;
            height: 40px;
            background: var(--gray-100);
            border: none;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            font-size: 20px;
        }

        .close-modal:hover {
            background: var(--gray-200);
            transform: rotate(90deg);
        }

        .auth-header {
            text-align: center;
            margin-bottom: 40px;
        }

        .auth-logo {
            width: 70px;
            height: 70px;
            background: var(--black);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 36px;
            color: var(--white);
            margin: 0 auto 24px;
            letter-spacing: -2px;
        }

        .auth-title {
            font-size: 32px;
            font-weight: 900;
            margin-bottom: 8px;
            letter-spacing: -1px;
        }

        .auth-subtitle {
            color: var(--gray-600);
            font-size: 15px;
        }

        .auth-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 32px;
            background: var(--gray-100);
            padding: 6px;
            border-radius: 14px;
        }

        .auth-tab {
            flex: 1;
            padding: 12px;
            background: transparent;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 15px;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Inter', sans-serif;
            color: var(--gray-600);
        }

        .auth-tab.active {
            background: var(--white);
            color: var(--black);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }

        .auth-form {
            display: none;
        }

        .auth-form.active {
            display: block;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 8px;
            color: var(--gray-900);
        }

        .form-input {
            width: 100%;
            padding: 14px 16px;
            background: var(--gray-50);
            border: 2px solid var(--gray-200);
            border-radius: 12px;
            font-size: 15px;
            font-family: 'Inter', sans-serif;
            transition: all 0.3s;
            font-weight: 500;
        }

        .form-input:focus {
            outline: none;
            background: var(--white);
            border-color: var(--black);
        }

        .form-submit {
            width: 100%;
            padding: 16px;
            background: var(--black);
            color: var(--white);
            border: none;
            border-radius: 12px;
            font-weight: 800;
            font-size: 16px;
            cursor: pointer;
            transition: all 0.3s;
            font-family: 'Inter', sans-serif;
            margin-top: 8px;
        }

        .form-submit:hover {
            background: var(--gray-900);
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }

        .form-submit:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .error-msg {
            padding: 14px;
            background: #fee;
            border: 2px solid #fcc;
            border-radius: 12px;
            color: #c00;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 20px;
            display: none;
        }

        .error-msg.active {
            display: block;
            animation: shake 0.5s;
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-10px); }
            75% { transform: translateX(10px); }
        }

        /* Scroll Animation */
        .scroll-reveal {
            opacity: 0;
            transform: translateY(60px);
            transition: all 0.8s ease-out;
        }

        .scroll-reveal.active {
            opacity: 1;
            transform: translateY(0);
        }

        @media (max-width: 768px) {
            .hero-title {
                font-size: 48px;
            }

            .hero-subtitle {
                font-size: 18px;
            }

            .features-grid {
                grid-template-columns: 1fr;
            }

            .cta-box {
                padding: 60px 40px;
            }

            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 40px;
            }
        }
    </style>
</head>
<body>
    <div class="bg-animated">
        <div class="bg-gradient bg-gradient-1"></div>
        <div class="bg-gradient bg-gradient-2"></div>
    </div>

    <!-- Header -->
    <header class="header">
        <div class="header-content">
            <a href="#" class="logo">
                <div class="logo-icon">0</div>
                <div class="logo-text">Project-0</div>
            </a>
            <button class="header-btn" onclick="showAuth('login')">Sign In</button>
        </div>
    </header>

    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-content">
            <div class="hero-badge">
                ✨ Powered by AI
            </div>
            <h1 class="hero-title">Transform Ideas<br>Into Reality</h1>
            <p class="hero-subtitle">
                Generate production-ready MVPs in seconds using AI. 
                Beautiful, modern, and ready to ship. No coding required.
            </p>
            <div class="cta-buttons">
                <button class="cta-primary" onclick="showAuth('register')">
                    <span>Try it Now →</span>
                </button>
                <button class="cta-secondary" onclick="scrollToFeatures()">
                    See How It Works
                </button>
            </div>
        </div>
    </section>

    <!-- Features Section -->
    <section class="features" id="features">
        <div class="features-container">
            <h2 class="section-title scroll-reveal">Everything You Need</h2>
            <p class="section-subtitle scroll-reveal">Powerful features for rapid MVP development</p>
            
            <div class="features-grid">
                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">⚡</div>
                    <h3 class="feature-title">Lightning Fast</h3>
                    <p class="feature-desc">Generate complete MVPs in seconds, not days. AI-powered efficiency that transforms your workflow.</p>
                </div>

                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">🎨</div>
                    <h3 class="feature-title">Beautiful Design</h3>
                    <p class="feature-desc">Modern, minimalist interfaces inspired by v0.dev. Every pixel perfect, every interaction smooth.</p>
                </div>

                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">💼</div>
                    <h3 class="feature-title">Export Ready</h3>
                    <p class="feature-desc">Download complete projects as ZIP files. All code, styles, and assets included. Ready to deploy.</p>
                </div>

                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">🔒</div>
                    <h3 class="feature-title">Secure & Private</h3>
                    <p class="feature-desc">Your data is encrypted and protected. Industry-standard security for peace of mind.</p>
                </div>

                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">🚀</div>
                    <h3 class="feature-title">Production Ready</h3>
                    <p class="feature-desc">Clean, maintainable code. Responsive design. SEO optimized. Ready for real users.</p>
                </div>

                <div class="feature-card scroll-reveal">
                    <div class="feature-icon">✨</div>
                    <h3 class="feature-title">AI Powered</h3>
                    <p class="feature-desc">Advanced language models understand your vision. Just describe what you want, we handle the rest.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Stats Section -->
    <section class="stats">
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-number">10x</div>
                <div class="stat-label">Faster Development</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">100%</div>
                <div class="stat-label">Production Ready</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">∞</div>
                <div class="stat-label">Possibilities</div>
            </div>
        </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
        <div class="cta-box scroll-reveal">
            <h2 class="cta-box-title">Start Building Today</h2>
            <p class="cta-box-subtitle">Join developers and entrepreneurs creating the future</p>
            <button class="cta-box-btn" onclick="showAuth('register')">
                Get Started Free
            </button>
        </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
        <p class="footer-text">© 2024 Project-0. Built with ❤️ for creators and innovators.</p>
    </footer>

    <!-- Auth Modal -->
    <div class="auth-modal" id="authModal">
        <div class="auth-panel">
            <button class="close-modal" onclick="closeAuth()">×</button>

            <div class="auth-header">
                <div class="auth-logo">0</div>
                <h2 class="auth-title">Welcome</h2>
                <p class="auth-subtitle">Sign in to start creating</p>
            </div>

            <div class="auth-tabs">
                <button class="auth-tab active" onclick="switchTab('login')">Sign In</button>
                <button class="auth-tab" onclick="switchTab('register')">Sign Up</button>
            </div>

            <div class="error-msg" id="errorMsg"></div>

            <!-- Login Form -->
            <form class="auth-form active" id="loginForm" onsubmit="handleLogin(event)">
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" class="form-input" name="email" required placeholder="you@example.com">
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" class="form-input" name="password" required placeholder="••••••••">
                </div>
                <button type="submit" class="form-submit">Sign In</button>
            </form>

            <!-- Register Form -->
            <form class="auth-form" id="registerForm" onsubmit="handleRegister(event)">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" class="form-input" name="username" required placeholder="johndoe">
                </div>
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" class="form-input" name="email" required placeholder="you@example.com">
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" class="form-input" name="password" required placeholder="••••••••">
                </div>
                <button type="submit" class="form-submit">Create Account</button>
            </form>
        </div>
    </div>

    <script>
        // Scroll reveal animation
        const revealElements = document.querySelectorAll('.scroll-reveal');
        
        const revealOnScroll = () => {
            revealElements.forEach(el => {
                const elementTop = el.getBoundingClientRect().top;
                const elementVisible = 150;
                
                if (elementTop < window.innerHeight - elementVisible) {
                    el.classList.add('active');
                }
            });
        };

        window.addEventListener('scroll', revealOnScroll);
        revealOnScroll();

        function scrollToFeatures() {
            document.getElementById('features').scrollIntoView({ behavior: 'smooth' });
        }

        function showAuth(tab = 'login') {
            document.getElementById('authModal').classList.add('active');
            switchTab(tab);
        }

        function closeAuth() {
            document.getElementById('authModal').classList.remove('active');
            hideError();
        }

        function switchTab(tab) {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
            
            if (tab === 'login') {
                document.getElementById('loginForm').classList.add('active');
                document.querySelectorAll('.auth-tab')[0].classList.add('active');
            } else {
                document.getElementById('registerForm').classList.add('active');
                document.querySelectorAll('.auth-tab')[1].classList.add('active');
            }
            hideError();
        }

        function showError(message) {
            const errorMsg = document.getElementById('errorMsg');
            errorMsg.textContent = message;
            errorMsg.classList.add('active');
        }

        function hideError() {
            document.getElementById('errorMsg').classList.remove('active');
        }

        async function handleLogin(e) {
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: formData.get('email'),
                        password: formData.get('password')
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    window.location.href = '/';
                } else {
                    showError(data.error || 'Login failed');
                }
            } catch (error) {
                showError('Network error. Please try again.');
            }
        }

        async function handleRegister(e) {
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);
            
            try {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username: formData.get('username'),
                        email: formData.get('email'),
                        password: formData.get('password')
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    window.location.href = '/';
                } else {
                    showError(data.error || 'Registration failed');
                }
            } catch (error) {
                showError('Network error. Please try again.');
            }
        }

        document.getElementById('authModal').addEventListener('click', (e) => {
            if (e.target.id === 'authModal') {
                closeAuth();
            }
        });
    </script>
</body>
</html>"""

# Main App Template (same as before, shortened for brevity)
APP_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 - AI MVP Generator</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
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
            height: 100vh;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }
        .container { display: flex; height: 100vh; }
        .chat-panel { width: 45%; display: flex; flex-direction: column; border-right: 1px solid var(--border-primary); background: var(--bg-primary); }
        .preview-panel { width: 55%; display: flex; flex-direction: column; background: var(--bg-secondary); }
        .header { background: var(--bg-primary); border-bottom: 1px solid var(--border-primary); padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; height: 56px; }
        .logo { display: flex; align-items: center; gap: 10px; }
        .logo-icon { width: 28px; height: 28px; background: var(--accent); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; color: white; letter-spacing: -0.5px; }
        .logo-text { font-size: 15px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.3px; }
        .profile-btn { width: 36px; height: 36px; background: var(--accent); color: white; border: none; border-radius: 50%; font-weight: 600; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; position: relative; }
        .profile-btn:hover { opacity: 0.8; transform: scale(1.05); }
        .profile-menu { display: none; position: absolute; top: 48px; right: 20px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 12px; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1); min-width: 200px; z-index: 1000; animation: slideDown 0.2s ease-out; }
        @keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
        .profile-menu.active { display: block; }
        .profile-menu-header { padding: 16px; border-bottom: 1px solid var(--border-primary); }
        .profile-name { font-weight: 600; font-size: 14px; color: var(--text-primary); margin-bottom: 4px; }
        .profile-email { font-size: 12px; color: var(--text-tertiary); }
        .profile-menu-item { padding: 12px 16px; display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-primary); cursor: pointer; transition: all 0.2s; border: none; background: none; width: 100%; text-align: left; font-family: 'Inter', sans-serif; }
        .profile-menu-item:hover { background: var(--bg-tertiary); }
        .profile-menu-item.danger { color: #dc2626; }
        .profile-menu-item svg { width: 16px; height: 16px; }
        .messages { flex: 1; overflow-y: auto; padding: 20px; }
        .message { margin-bottom: 20px; animation: slideUp 0.3s ease-out; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .message-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
        .message-role { font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); }
        .message-content { padding: 12px 14px; border-radius: 8px; line-height: 1.6; font-size: 13px; color: var(--text-primary); }
        .user-message .message-content { background: var(--bg-tertiary); border: 1px solid var(--border-primary); }
        .ai-message .message-content { background: var(--bg-secondary); border: 1px solid var(--border-primary); }
        .status-indicator { display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 6px; font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; font-weight: 500; }
        .spinner { width: 12px; height: 12px; border: 2px solid var(--border-secondary); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .markdown-content { font-size: 13px; line-height: 1.6; }
        .markdown-content h2 { font-size: 16px; font-weight: 600; margin: 16px 0 10px 0; color: var(--text-primary); }
        .markdown-content h3 { font-size: 14px; font-weight: 600; margin: 12px 0 8px 0; color: var(--text-primary); }
        .markdown-content ul { margin: 8px 0 8px 18px; }
        .markdown-content li { margin: 4px 0; color: var(--text-secondary); }
        .markdown-content code { background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; font-family: 'SF Mono', Monaco, monospace; font-size: 12px; color: var(--text-primary); border: 1px solid var(--border-primary); }
        .markdown-content pre { background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 8px; padding: 14px; overflow-x: auto; margin: 10px 0; }
        .markdown-content pre code { background: none; padding: 0; border: none; color: var(--text-primary); }
        .markdown-content strong { color: var(--text-primary); font-weight: 600; }
        .markdown-content p { margin: 8px 0; color: var(--text-secondary); }
        .action-buttons { display: flex; gap: 8px; margin-top: 12px; }
        .action-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; background: var(--accent); color: white; border: none; border-radius: 6px; font-weight: 500; font-size: 12px; cursor: pointer; transition: all 0.2s; font-family: 'Inter', sans-serif; }
        .action-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .action-btn.secondary { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-primary); }
        .action-btn.secondary:hover { background: var(--bg-tertiary); }
        .input-area { padding: 16px 20px; background: var(--bg-primary); border-top: 1px solid var(--border-primary); }
        .input-wrapper { position: relative; }
        #ideaInput { width: 100%; padding: 12px 50px 12px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; color: var(--text-primary); font-size: 13px; font-family: 'Inter', sans-serif; resize: none; outline: none; min-height: 44px; max-height: 180px; line-height: 1.5; }
        #ideaInput:focus { border-color: var(--accent); background: var(--bg-primary); }
        #ideaInput::placeholder { color: var(--text-tertiary); }
        #generateBtn { position: absolute; right: 6px; bottom: 6px; width: 36px; height: 36px; background: var(--accent); color: white; border: none; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
        #generateBtn:hover:not(:disabled) { opacity: 0.9; }
        #generateBtn:disabled { background: var(--border-secondary); cursor: not-allowed; }
        .preview-header { padding: 12px 20px; background: var(--bg-secondary); border-bottom: 1px solid var(--border-primary); display: flex; align-items: center; justify-content: space-between; height: 56px; }
        .preview-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); letter-spacing: -0.2px; }
        .preview-actions { display: flex; gap: 6px; }
        .preview-btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--bg-primary); border: 1px solid var(--border-primary); border-radius: 6px; color: var(--text-primary); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.2s; font-family: 'Inter', sans-serif; }
        .preview-btn:hover { background: var(--bg-tertiary); }
        .preview-btn svg { width: 14px; height: 14px; }
        .preview-frame { flex: 1; background: white; position: relative; }
        iframe { width: 100%; height: 100%; border: none; }
        .preview-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-tertiary); text-align: center; padding: 40px; }
        .placeholder-icon { width: 64px; height: 64px; background: var(--bg-tertiary); border: 1px solid var(--border-primary); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 28px; margin-bottom: 16px; }
        .placeholder-text { font-size: 15px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; }
        .placeholder-hint { font-size: 13px; color: var(--text-tertiary); }
        .welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; text-align: center; min-height: 400px; }
        .welcome-logo { width: 72px; height: 72px; background: var(--accent); border-radius: 16px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 32px; color: white; margin-bottom: 20px; letter-spacing: -1px; }
        .welcome-title { font-size: 24px; font-weight: 700; margin-bottom: 8px; color: var(--text-primary); letter-spacing: -0.5px; }
        .welcome-subtitle { font-size: 14px; color: var(--text-secondary); margin-bottom: 28px; max-width: 380px; line-height: 1.5; }
        .example-ideas { display: grid; gap: 8px; max-width: 420px; width: 100%; }
        .example-idea { padding: 12px 14px; background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 8px; cursor: pointer; transition: all 0.2s; text-align: left; }
        .example-idea:hover { background: var(--bg-tertiary); border-color: var(--border-secondary); transform: translateY(-1px); }
        .example-title { font-weight: 600; margin-bottom: 2px; font-size: 13px; color: var(--text-primary); }
        .example-desc { font-size: 12px; color: var(--text-tertiary); }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--border-secondary); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }
        @media (max-width: 1024px) {
            .container { flex-direction: column; }
            .chat-panel { width: 100%; height: 60%; border-right: none; border-bottom: 1px solid var(--border-primary); }
            .preview-panel { width: 100%; height: 40%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="chat-panel">
            <div class="header">
                <div class="logo">
                    <div class="logo-icon">0</div>
                    <div class="logo-text">Project-0</div>
                </div>
                <button class="profile-btn" onclick="toggleProfile()" id="profileBtn">
                    <span id="profileInitial">U</span>
                </button>
                <div class="profile-menu" id="profileMenu">
                    <div class="profile-menu-header">
                        <div class="profile-name" id="profileName">Loading...</div>
                        <div class="profile-email" id="profileEmail"></div>
                    </div>
                    <button class="profile-menu-item danger" onclick="logout()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                            <polyline points="16 17 21 12 16 7"/>
                            <line x1="21" y1="12" x2="9" y2="12"/>
                        </svg>
                        Logout
                    </button>
                </div>
            </div>
            <div class="messages" id="messages">
                <div class="welcome">
                    <div class="welcome-logo">0</div>
                    <div class="welcome-title">AI MVP Generator</div>
                    <div class="welcome-subtitle">Transform your ideas into production-ready prototypes</div>
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
                    <textarea id="ideaInput" placeholder="Describe your MVP idea..." rows="1"></textarea>
                    <button id="generateBtn">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
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
        let isGenerating = false;
        let currentMvpId = null;
        let currentUser = null;
        const ideaInput = document.getElementById('ideaInput');
        const generateBtn = document.getElementById('generateBtn');
        const messagesDiv = document.getElementById('messages');
        const previewFrame = document.getElementById('previewFrame');
        const downloadBtn = document.getElementById('downloadBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const newWindowBtn = document.getElementById('newWindowBtn');
        
        async function loadProfile() {
            try {
                const response = await fetch('/api/auth/me');
                if (response.ok) {
                    currentUser = await response.json();
                    document.getElementById('profileName').textContent = currentUser.username;
                    document.getElementById('profileEmail').textContent = currentUser.email;
                    document.getElementById('profileInitial').textContent = currentUser.username[0].toUpperCase();
                } else {
                    window.location.href = '/';
                }
            } catch (error) {
                console.error('Failed to load profile:', error);
            }
        }
        loadProfile();
        
        function toggleProfile() {
            document.getElementById('profileMenu').classList.toggle('active');
        }
        
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.profile-btn') && !e.target.closest('.profile-menu')) {
                document.getElementById('profileMenu').classList.remove('active');
            }
        });
        
        async function logout() {
            try {
                await fetch('/api/auth/logout', { method: 'POST' });
                window.location.href = '/';
            } catch (error) {
                console.error('Logout failed:', error);
            }
        }
        
        document.querySelectorAll('.example-idea').forEach(el => {
            el.addEventListener('click', () => {
                ideaInput.value = el.dataset.idea;
                ideaInput.focus();
                autoResize();
            });
        });
        
        function autoResize() {
            ideaInput.style.height = 'auto';
            ideaInput.style.height = Math.min(ideaInput.scrollHeight, 180) + 'px';
        }
        ideaInput.addEventListener('input', autoResize);
        
        generateBtn.addEventListener('click', generate);
        ideaInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                generate();
            }
        });
        
        function generate() {
            const idea = ideaInput.value.trim();
            if (!idea || isGenerating) return;
            isGenerating = true;
            generateBtn.disabled = true;
            const welcome = document.querySelector('.welcome');
            if (welcome) welcome.remove();
            addMessage('user', idea);
            ideaInput.value = '';
            autoResize();
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
            fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({idea})
            })
            .then(response => {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                function read() {
                    reader.read().then(({done, value}) => {
                        if (done) {
                            isGenerating = false;
                            generateBtn.disabled = false;
                            ideaInput.focus();
                            return;
                        }
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
                        read();
                    });
                }
                read();
            })
            .catch(err => {
                console.error(err);
                isGenerating = false;
                generateBtn.disabled = false;
            });
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
        
        downloadBtn.addEventListener('click', () => {
            if (currentMvpId) downloadProject(currentMvpId);
        });
        refreshBtn.addEventListener('click', () => {
            if (currentMvpId) showPreview(currentMvpId);
        });
        newWindowBtn.addEventListener('click', () => {
            if (currentMvpId) window.open(`/preview/${currentMvpId}`, '_blank');
        });
        ideaInput.focus();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Project-0 Production Server...")
    print("📍 Landing: http://localhost:8000")
    print("🔐 Simple Session Auth")
    print("💾 Database: SQLite")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
