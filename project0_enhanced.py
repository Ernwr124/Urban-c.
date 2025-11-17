"""
Project-0 (web-MVP) - AI MVP Generator
Enhanced version with authentication, credits system, and admin panel
Black & White minimalist interface with theme switcher
"""

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import httpx
import json
import asyncio
from typing import AsyncGenerator, Dict, Optional
import time
import re
import io
import zipfile
import sqlite3
from pathlib import Path

app = FastAPI(title="Project-0 (web-MVP)", description="AI-Powered MVP Generator with Auth")

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
SECRET_KEY = "your-secret-key-change-this-in-production-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database setup
DB_PATH = Path("project0.db")

def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        google_account TEXT,
        password_hash TEXT NOT NULL,
        credits INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        total_requests INTEGER DEFAULT 0
    )''')
    
    # Credit requests table
    c.execute('''CREATE TABLE IF NOT EXISTS credit_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        email TEXT NOT NULL,
        amount INTEGER DEFAULT 5,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    # Admin user
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    
    # Create default admin if not exists
    admin_hash = pwd_context.hash("ernur140707")
    try:
        c.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", 
                 ("Yernur@", admin_hash))
    except sqlite3.IntegrityError:
        pass  # Admin already exists
    
    conn.commit()
    conn.close()

init_db()

# Models
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    google_account: Optional[str] = None
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class GenerateRequest(BaseModel):
    idea: str

class CreditRequest(BaseModel):
    pass

class AdminLogin(BaseModel):
    username: str
    password: str

class CreditRequestAction(BaseModel):
    request_id: int
    action: str  # 'approve' or 'reject'

# Helper functions
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

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

# Store generated MVPs
generated_mvps: Dict[str, Dict] = {}

async def generate_mvp(idea: str, username: str) -> AsyncGenerator[str, None]:
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
                                generated_mvps[mvp_id] = {
                                    "idea": idea,
                                    "code": html_code,
                                    "markdown": full_response,
                                    "timestamp": datetime.now().isoformat(),
                                    "username": username
                                }
                                
                                # Update user stats
                                conn = get_db()
                                conn.execute("UPDATE users SET total_requests = total_requests + 1 WHERE username = ?", 
                                           (username,))
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

# API Endpoints

@app.post("/api/auth/register")
async def register(user: UserRegister):
    """Register new user"""
    conn = get_db()
    
    # Check if user exists
    existing = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", 
                           (user.username, user.email)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    
    # Create user
    password_hash = get_password_hash(user.password)
    try:
        conn.execute("""INSERT INTO users (username, email, google_account, password_hash, credits) 
                       VALUES (?, ?, ?, ?, 3)""",
                    (user.username, user.email, user.google_account, password_hash))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
    
    conn.close()
    
    # Create token
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "credits": 3
    }

@app.post("/api/auth/login")
async def login(user: UserLogin):
    """Login user"""
    conn = get_db()
    
    db_user = conn.execute("SELECT * FROM users WHERE username = ?", (user.username,)).fetchone()
    
    if not db_user or not verify_password(user.password, db_user['password_hash']):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update last login
    conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (user.username,))
    conn.commit()
    conn.close()
    
    access_token = create_access_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username,
        "credits": db_user['credits']
    }

@app.get("/api/auth/me")
async def get_current_user(authorization: Optional[str] = None):
    """Get current user info"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    username = verify_token(token)
    
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = get_db()
    user = conn.execute("SELECT username, email, credits, total_requests FROM users WHERE username = ?", 
                       (username,)).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "username": user['username'],
        "email": user['email'],
        "credits": user['credits'],
        "total_requests": user['total_requests']
    }

@app.post("/api/generate")
async def generate(request: GenerateRequest, authorization: Optional[str] = None):
    """Generate MVP from idea with streaming"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    username = verify_token(token)
    
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Check credits
    conn = get_db()
    user = conn.execute("SELECT credits FROM users WHERE username = ?", (username,)).fetchone()
    
    if not user or user['credits'] <= 0:
        conn.close()
        raise HTTPException(status_code=403, detail="Insufficient credits")
    
    # Deduct credit
    conn.execute("UPDATE users SET credits = credits - 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    
    return StreamingResponse(
        generate_mvp(request.idea, username),
        media_type="text/event-stream"
    )

@app.post("/api/credits/request")
async def request_credits(authorization: Optional[str] = None):
    """Request credit refill"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    username = verify_token(token)
    
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = get_db()
    user = conn.execute("SELECT id, email FROM users WHERE username = ?", (username,)).fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create credit request
    conn.execute("""INSERT INTO credit_requests (user_id, username, email) 
                   VALUES (?, ?, ?)""",
                (user['id'], username, user['email']))
    conn.commit()
    conn.close()
    
    return {"message": "Credit request submitted successfully"}

@app.get("/api/mvp/{mvp_id}")
async def get_mvp(mvp_id: str):
    """Get MVP data"""
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
    return mvp["code"] if mvp["code"] else "<h1>No code generated</h1>"

@app.get("/api/download/{mvp_id}")
async def download_project(mvp_id: str):
    """Download project as ZIP file"""
    if mvp_id not in generated_mvps:
        return JSONResponse({"error": "MVP not found"}, status_code=404)
    
    mvp = generated_mvps[mvp_id]
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('index.html', mvp["code"])
        
        readme_content = f"""# {mvp["idea"]}

Generated by Project-0 (web-MVP)
Date: {mvp["timestamp"]}

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
        
        info_content = f"""Project: {mvp["idea"]}
Generated: {mvp["timestamp"]}
MVP ID: {mvp_id}

This is a self-contained HTML project.
Everything you need is in index.html.
"""
        zip_file.writestr('PROJECT-INFO.txt', info_content)
    
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

# Admin endpoints

@app.post("/api/admin/login")
async def admin_login(admin: AdminLogin):
    """Admin login"""
    conn = get_db()
    db_admin = conn.execute("SELECT * FROM admins WHERE username = ?", (admin.username,)).fetchone()
    conn.close()
    
    if not db_admin or not verify_password(admin.password, db_admin['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    
    access_token = create_access_token(data={"sub": admin.username, "role": "admin"})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": admin.username
    }

@app.get("/api/admin/analytics")
async def get_analytics(authorization: Optional[str] = None):
    """Get platform analytics"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = get_db()
    
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    active_users = conn.execute("SELECT COUNT(*) as count FROM users WHERE total_requests > 0").fetchone()['count']
    total_requests = conn.execute("SELECT SUM(total_requests) as sum FROM users").fetchone()['sum'] or 0
    pending_requests = conn.execute("SELECT COUNT(*) as count FROM credit_requests WHERE status = 'pending'").fetchone()['count']
    
    conn.close()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_ai_requests": total_requests,
        "pending_credit_requests": pending_requests
    }

@app.get("/api/admin/credit-requests")
async def get_credit_requests(authorization: Optional[str] = None):
    """Get all credit requests"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = get_db()
    requests = conn.execute("""SELECT id, username, email, amount, status, created_at 
                              FROM credit_requests 
                              ORDER BY created_at DESC""").fetchall()
    conn.close()
    
    return [dict(r) for r in requests]

@app.post("/api/admin/credit-requests/action")
async def process_credit_request(action: CreditRequestAction, authorization: Optional[str] = None):
    """Approve or reject credit request"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    conn = get_db()
    
    request_data = conn.execute("SELECT * FROM credit_requests WHERE id = ?", 
                               (action.request_id,)).fetchone()
    
    if not request_data:
        conn.close()
        raise HTTPException(status_code=404, detail="Request not found")
    
    if action.action == "approve":
        conn.execute("UPDATE users SET credits = credits + 5 WHERE id = ?", 
                    (request_data['user_id'],))
        conn.execute("UPDATE credit_requests SET status = 'approved', processed_at = CURRENT_TIMESTAMP WHERE id = ?", 
                    (action.request_id,))
    elif action.action == "reject":
        conn.execute("UPDATE credit_requests SET status = 'rejected', processed_at = CURRENT_TIMESTAMP WHERE id = ?", 
                    (action.request_id,))
    
    conn.commit()
    conn.close()
    
    return {"message": f"Request {action.action}ed successfully"}

@app.get("/api/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "generated_mvps": len(generated_mvps)
    }

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application UI"""
    return HTML_TEMPLATE

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    """Serve admin panel"""
    return ADMIN_TEMPLATE

# HTML Templates

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project-0 (web-MVP) - AI MVP Generator</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --bg-primary: #ffffff;
            --bg-secondary: #f8f9fa;
            --bg-tertiary: #f1f3f5;
            --border-primary: #e5e5e5;
            --border-secondary: #d4d4d4;
            --text-primary: #171717;
            --text-secondary: #525252;
            --text-tertiary: #737373;
            --accent: #000000;
            --shadow: 0 2px 8px rgba(0,0,0,0.08);
            --shadow-lg: 0 4px 16px rgba(0,0,0,0.12);
        }

        [data-theme="dark"] {
            --bg-primary: #0a0a0a;
            --bg-secondary: #141414;
            --bg-tertiary: #1a1a1a;
            --border-primary: #2a2a2a;
            --border-secondary: #3a3a3a;
            --text-primary: #ededed;
            --text-secondary: #a3a3a3;
            --text-tertiary: #737373;
            --accent: #ffffff;
            --shadow: 0 2px 8px rgba(0,0,0,0.3);
            --shadow-lg: 0 4px 16px rgba(0,0,0,0.5);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
            transition: background 0.3s, color 0.3s;
        }

        /* Auth Modal */
        .auth-modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.7);
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

        .auth-modal {
            background: var(--bg-primary);
            border: 1px solid var(--border-primary);
            border-radius: 16px;
            width: 90%;
            max-width: 420px;
            box-shadow: var(--shadow-lg), 0 0 0 1px rgba(0,0,0,0.05);
            animation: slideUp 0.3s ease-out;
            position: relative;
        }

        @keyframes slideUp {
            from { 
                opacity: 0; 
                transform: translateY(20px) scale(0.95);
            }
            to { 
                opacity: 1; 
                transform: translateY(0) scale(1);
            }
        }

        .auth-header {
            padding: 28px 28px 20px;
            text-align: center;
            border-bottom: 1px solid var(--border-primary);
        }

        .auth-logo {
            width: 56px;
            height: 56px;
            background: var(--accent);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            font-weight: 700;
            font-size: 28px;
            color: var(--bg-primary);
            box-shadow: var(--shadow);
        }

        .auth-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 6px;
            color: var(--text-primary);
        }

        .auth-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
        }

        .auth-tabs {
            display: flex;
            padding: 16px 28px 0;
            gap: 8px;
        }

        .auth-tab {
            flex: 1;
            padding: 10px;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--text-tertiary);
            font-weight: 500;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .auth-tab.active {
            color: var(--text-primary);
            border-bottom-color: var(--accent);
        }

        .auth-body {
            padding: 28px;
        }

        .auth-form {
            display: none;
        }

        .auth-form.active {
            display: block;
        }

        .form-group {
            margin-bottom: 18px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-primary);
        }

        .form-input {
            width: 100%;
            padding: 11px 14px;
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
            box-shadow: 0 0 0 3px rgba(0,0,0,0.05);
        }

        .form-input::placeholder {
            color: var(--text-tertiary);
        }

        .auth-submit {
            width: 100%;
            padding: 12px;
            background: var(--accent);
            color: var(--bg-primary);
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
            margin-top: 8px;
        }

        .auth-submit:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .auth-submit:active {
            transform: translateY(0);
        }

        .auth-error {
            padding: 10px 14px;
            background: #fee;
            border: 1px solid #fcc;
            border-radius: 6px;
            color: #c33;
            font-size: 12px;
            margin-bottom: 16px;
            display: none;
        }

        /* Credit Request Modal */
        .credit-modal {
            background: var(--bg-primary);
            border: 1px solid var(--border-primary);
            border-radius: 16px;
            width: 90%;
            max-width: 480px;
            box-shadow: var(--shadow-lg);
            animation: slideUp 0.3s ease-out;
        }

        .credit-header {
            padding: 24px;
            border-bottom: 1px solid var(--border-primary);
        }

        .credit-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 6px;
            color: var(--text-primary);
        }

        .credit-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
        }

        .credit-body {
            padding: 24px;
        }

        .payment-info {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .payment-label {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }

        .payment-value {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 16px;
            font-family: 'SF Mono', Monaco, monospace;
        }

        .credit-info {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .credit-icon {
            width: 40px;
            height: 40px;
            background: var(--accent);
            color: var(--bg-primary);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }

        .credit-details {
            flex: 1;
        }

        .credit-details-title {
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
        }

        .credit-details-desc {
            font-size: 12px;
            color: var(--text-secondary);
        }

        .credit-actions {
            display: flex;
            gap: 12px;
        }

        .credit-btn {
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
        }

        .credit-btn.primary {
            background: var(--accent);
            color: var(--bg-primary);
        }

        .credit-btn.secondary {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border: 1px solid var(--border-primary);
        }

        .credit-btn:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }

        .container {
            display: flex;
            height: 100vh;
        }

        .chat-panel {
            width: 45%;
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-primary);
            background: var(--bg-primary);
        }

        .preview-panel {
            width: 55%;
            display: flex;
            flex-direction: column;
            background: var(--bg-secondary);
        }

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
            color: var(--bg-primary);
            letter-spacing: -0.5px;
        }

        .logo-text {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.3px;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .credits-badge {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .credits-icon {
            font-size: 16px;
        }

        .theme-toggle {
            width: 36px;
            height: 36px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 16px;
        }

        .theme-toggle:hover {
            background: var(--bg-secondary);
        }

        .user-menu {
            position: relative;
        }

        .user-button {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-primary);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-primary);
        }

        .user-button:hover {
            background: var(--bg-secondary);
        }

        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .message {
            margin-bottom: 20px;
            animation: slideUp 0.3s ease-out;
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
            color: var(--bg-primary);
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
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-primary);
        }

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
            color: var(--bg-primary);
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
            color: var(--bg-primary);
            margin-bottom: 20px;
        }

        .welcome-title {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text-primary);
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
    </style>
</head>
<body>
    <!-- Auth Modal -->
    <div class="auth-modal-overlay" id="authModal">
        <div class="auth-modal">
            <div class="auth-header">
                <div class="auth-logo">0</div>
                <div class="auth-title">Welcome to Project-0</div>
                <div class="auth-subtitle">Sign in to start creating MVPs</div>
            </div>
            
            <div class="auth-tabs">
                <button class="auth-tab active" data-tab="login">Login</button>
                <button class="auth-tab" data-tab="register">Register</button>
            </div>
            
            <div class="auth-body">
                <div class="auth-error" id="authError"></div>
                
                <!-- Login Form -->
                <form class="auth-form active" id="loginForm">
                    <div class="form-group">
                        <label class="form-label">Username</label>
                        <input type="text" class="form-input" name="username" placeholder="Enter your username" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Password</label>
                        <input type="password" class="form-input" name="password" placeholder="Enter your password" required>
                    </div>
                    <button type="submit" class="auth-submit">Sign In</button>
                </form>
                
                <!-- Register Form -->
                <form class="auth-form" id="registerForm">
                    <div class="form-group">
                        <label class="form-label">Username</label>
                        <input type="text" class="form-input" name="username" placeholder="Choose a username" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Email</label>
                        <input type="email" class="form-input" name="email" placeholder="your@email.com" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Google Account (Optional)</label>
                        <input type="email" class="form-input" name="google_account" placeholder="your.google@gmail.com">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Password</label>
                        <input type="password" class="form-input" name="password" placeholder="Create a password" required>
                    </div>
                    <button type="submit" class="auth-submit">Create Account</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Credit Request Modal -->
    <div class="auth-modal-overlay" id="creditModal" style="display: none;">
        <div class="credit-modal">
            <div class="credit-header">
                <div class="credit-title">💳 Purchase Credits</div>
                <div class="credit-subtitle">Send payment to the number below and request approval</div>
            </div>
            
            <div class="credit-body">
                <div class="payment-info">
                    <div class="payment-label">Kaspi Number</div>
                    <div class="payment-value">+7-708-202-1308</div>
                    <div class="payment-label">Recipient</div>
                    <div class="payment-value">Канат Е.</div>
                </div>
                
                <div class="credit-info">
                    <div class="credit-icon">⚡</div>
                    <div class="credit-details">
                        <div class="credit-details-title">5 Credits Package</div>
                        <div class="credit-details-desc">After payment, click "Request" for admin approval</div>
                    </div>
                </div>
                
                <div class="credit-actions">
                    <button class="credit-btn secondary" onclick="closeCreditModal()">Cancel</button>
                    <button class="credit-btn primary" onclick="submitCreditRequest()">Request</button>
                </div>
            </div>
        </div>
    </div>

    <div class="container" id="mainContainer" style="display: none;">
        <!-- Chat Panel -->
        <div class="chat-panel">
            <div class="header">
                <div class="logo">
                    <div class="logo-icon">0</div>
                    <div class="logo-text">Project-0</div>
                </div>
                <div class="header-actions">
                    <div class="credits-badge" id="creditsDisplay">
                        <span class="credits-icon">⚡</span>
                        <span id="creditsCount">0</span>
                    </div>
                    <div class="theme-toggle" id="themeToggle">🌙</div>
                    <div class="user-menu">
                        <div class="user-button" id="userButton">
                            <span id="username">User</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="messages" id="messages">
                <div class="welcome">
                    <div class="welcome-logo">0</div>
                    <div class="welcome-title">AI MVP Generator</div>
                    <div class="welcome-subtitle">
                        Transform your ideas into production-ready prototypes
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
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        Download
                    </button>
                    <button class="preview-btn" id="refreshBtn" style="display:none;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
                        </svg>
                        Refresh
                    </button>
                    <button class="preview-btn" id="newWindowBtn" style="display:none;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
        let authToken = localStorage.getItem('auth_token');
        let currentUser = null;
        let userCredits = 0;
        let isGenerating = false;
        let currentMvpId = null;

        // Theme handling
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon();

        document.getElementById('themeToggle').addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon();
        });

        function updateThemeIcon() {
            const theme = document.documentElement.getAttribute('data-theme');
            document.getElementById('themeToggle').textContent = theme === 'light' ? '🌙' : '☀️';
        }

        // Auth handling
        if (authToken) {
            checkAuth();
        }

        // Auth tabs
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
                
                tab.classList.add('active');
                const formId = tab.dataset.tab === 'login' ? 'loginForm' : 'registerForm';
                document.getElementById(formId).classList.add('active');
            });
        });

        // Login
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get('username'),
                password: formData.get('password')
            };

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const error = await response.json();
                    showAuthError(error.detail || 'Login failed');
                    return;
                }

                const result = await response.json();
                authToken = result.access_token;
                localStorage.setItem('auth_token', authToken);
                currentUser = result.username;
                userCredits = result.credits;
                
                document.getElementById('authModal').style.display = 'none';
                document.getElementById('mainContainer').style.display = 'flex';
                updateUserDisplay();
            } catch (err) {
                showAuthError('Network error. Please try again.');
            }
        });

        // Register
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get('username'),
                email: formData.get('email'),
                google_account: formData.get('google_account') || null,
                password: formData.get('password')
            };

            try {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const error = await response.json();
                    showAuthError(error.detail || 'Registration failed');
                    return;
                }

                const result = await response.json();
                authToken = result.access_token;
                localStorage.setItem('auth_token', authToken);
                currentUser = result.username;
                userCredits = result.credits;
                
                document.getElementById('authModal').style.display = 'none';
                document.getElementById('mainContainer').style.display = 'flex';
                updateUserDisplay();
                
                alert('🎉 Welcome! You received 3 free credits to get started!');
            } catch (err) {
                showAuthError('Network error. Please try again.');
            }
        });

        async function checkAuth() {
            try {
                const response = await fetch('/api/auth/me', {
                    headers: {'Authorization': `Bearer ${authToken}`}
                });

                if (!response.ok) {
                    localStorage.removeItem('auth_token');
                    authToken = null;
                    return;
                }

                const user = await response.json();
                currentUser = user.username;
                userCredits = user.credits;
                
                document.getElementById('authModal').style.display = 'none';
                document.getElementById('mainContainer').style.display = 'flex';
                updateUserDisplay();
            } catch (err) {
                localStorage.removeItem('auth_token');
                authToken = null;
            }
        }

        function updateUserDisplay() {
            document.getElementById('username').textContent = currentUser;
            document.getElementById('creditsCount').textContent = userCredits;
        }

        function showAuthError(message) {
            const errorEl = document.getElementById('authError');
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 5000);
        }

        // Credit modal
        function showCreditModal() {
            document.getElementById('creditModal').style.display = 'flex';
        }

        function closeCreditModal() {
            document.getElementById('creditModal').style.display = 'none';
        }

        async function submitCreditRequest() {
            try {
                const response = await fetch('/api/credits/request', {
                    method: 'POST',
                    headers: {'Authorization': `Bearer ${authToken}`}
                });

                if (response.ok) {
                    alert('✅ Credit request submitted! Admin will review it soon.');
                    closeCreditModal();
                } else {
                    alert('❌ Failed to submit request. Please try again.');
                }
            } catch (err) {
                alert('❌ Network error. Please try again.');
            }
        }

        // Credits button
        document.getElementById('creditsDisplay').addEventListener('click', () => {
            if (userCredits === 0) {
                showCreditModal();
            }
        });

        // Example ideas
        document.querySelectorAll('.example-idea').forEach(el => {
            el.addEventListener('click', () => {
                ideaInput.value = el.dataset.idea;
                ideaInput.focus();
                autoResize();
            });
        });

        const ideaInput = document.getElementById('ideaInput');
        const generateBtn = document.getElementById('generateBtn');
        const messagesDiv = document.getElementById('messages');
        const previewFrame = document.getElementById('previewFrame');
        const downloadBtn = document.getElementById('downloadBtn');
        const refreshBtn = document.getElementById('refreshBtn');
        const newWindowBtn = document.getElementById('newWindowBtn');

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

        async function generate() {
            const idea = ideaInput.value.trim();
            if (!idea || isGenerating) return;

            if (userCredits <= 0) {
                showCreditModal();
                return;
            }

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

            try {
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${authToken}`
                    },
                    body: JSON.stringify({idea})
                });

                if (!response.ok) {
                    throw new Error('Generation failed');
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';

                function read() {
                    reader.read().then(({done, value}) => {
                        if (done) {
                            isGenerating = false;
                            generateBtn.disabled = false;
                            userCredits--;
                            updateUserDisplay();
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
                                    else if (data.type === 'error') {
                                        alert('Error: ' + data.content);
                                    }
                                } catch (e) {}
                            }
                        });

                        read();
                    });
                }

                read();
            } catch (err) {
                console.error(err);
                isGenerating = false;
                generateBtn.disabled = false;
                alert('Failed to generate. Please check if Ollama is running.');
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

ADMIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - Project-0</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: #0a0a0a;
            color: #ededed;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            background: #141414;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }

        .header h1 {
            font-size: 24px;
            margin-bottom: 8px;
        }

        .header p {
            color: #a3a3a3;
            font-size: 14px;
        }

        .login-form {
            background: #141414;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 32px;
            max-width: 400px;
            margin: 100px auto;
        }

        .login-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 24px;
            text-align: center;
        }

        .form-group {
            margin-bottom: 16px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 500;
        }

        .form-input {
            width: 100%;
            padding: 12px 14px;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            color: #ededed;
            font-size: 14px;
            font-family: 'Inter', sans-serif;
            outline: none;
        }

        .form-input:focus {
            border-color: #fff;
        }

        .btn {
            width: 100%;
            padding: 12px;
            background: #fff;
            color: #000;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            font-family: 'Inter', sans-serif;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: #141414;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 20px;
        }

        .stat-label {
            font-size: 12px;
            color: #a3a3a3;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
        }

        .requests-section {
            background: #141414;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 24px;
        }

        .section-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 20px;
        }

        .request-card {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }

        .request-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .request-user {
            font-weight: 600;
        }

        .request-email {
            font-size: 13px;
            color: #a3a3a3;
        }

        .request-status {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }

        .status-pending {
            background: #fef3c7;
            color: #92400e;
        }

        .status-approved {
            background: #d1fae5;
            color: #065f46;
        }

        .status-rejected {
            background: #fee2e2;
            color: #991b1b;
        }

        .request-actions {
            display: flex;
            gap: 8px;
        }

        .action-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            font-family: 'Inter', sans-serif;
        }

        .btn-approve {
            background: #10b981;
            color: white;
        }

        .btn-reject {
            background: #ef4444;
            color: white;
        }

        .btn-approve:hover, .btn-reject:hover {
            opacity: 0.9;
        }
    </style>
</head>
<body>
    <div id="loginSection">
        <div class="login-form">
            <div class="login-title">🔐 Admin Login</div>
            <form id="adminLoginForm">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" class="form-input" name="username" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" class="form-input" name="password" required>
                </div>
                <button type="submit" class="btn">Login</button>
            </form>
        </div>
    </div>

    <div id="adminPanel" style="display: none;">
        <div class="container">
            <div class="header">
                <h1>Admin Dashboard</h1>
                <p>Manage users and credit requests</p>
            </div>

            <div class="stats-grid" id="statsGrid">
                <!-- Stats will be loaded here -->
            </div>

            <div class="requests-section">
                <div class="section-title">Credit Requests</div>
                <div id="requestsList">
                    <!-- Requests will be loaded here -->
                </div>
            </div>
        </div>
    </div>

    <script>
        let adminToken = localStorage.getItem('admin_token');

        if (adminToken) {
            loadAdminPanel();
        }

        document.getElementById('adminLoginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                username: formData.get('username'),
                password: formData.get('password')
            };

            try {
                const response = await fetch('/api/admin/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    alert('Invalid credentials');
                    return;
                }

                const result = await response.json();
                adminToken = result.access_token;
                localStorage.setItem('admin_token', adminToken);
                
                loadAdminPanel();
            } catch (err) {
                alert('Login failed');
            }
        });

        async function loadAdminPanel() {
            document.getElementById('loginSection').style.display = 'none';
            document.getElementById('adminPanel').style.display = 'block';
            
            await loadAnalytics();
            await loadRequests();
            
            setInterval(loadRequests, 10000); // Refresh every 10 seconds
        }

        async function loadAnalytics() {
            try {
                const response = await fetch('/api/admin/analytics', {
                    headers: {'Authorization': `Bearer ${adminToken}`}
                });

                if (!response.ok) return;

                const data = await response.json();
                
                document.getElementById('statsGrid').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-label">Total Users</div>
                        <div class="stat-value">${data.total_users}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Active Users</div>
                        <div class="stat-value">${data.active_users}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Total AI Requests</div>
                        <div class="stat-value">${data.total_ai_requests}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Pending Requests</div>
                        <div class="stat-value">${data.pending_credit_requests}</div>
                    </div>
                `;
            } catch (err) {
                console.error(err);
            }
        }

        async function loadRequests() {
            try {
                const response = await fetch('/api/admin/credit-requests', {
                    headers: {'Authorization': `Bearer ${adminToken}`}
                });

                if (!response.ok) return;

                const requests = await response.json();
                
                if (requests.length === 0) {
                    document.getElementById('requestsList').innerHTML = '<p style="color: #a3a3a3;">No credit requests</p>';
                    return;
                }
                
                document.getElementById('requestsList').innerHTML = requests.map(req => `
                    <div class="request-card">
                        <div class="request-header">
                            <div>
                                <div class="request-user">${req.username}</div>
                                <div class="request-email">${req.email}</div>
                                <div style="margin-top: 8px; font-size: 12px; color: #a3a3a3;">
                                    ${new Date(req.created_at).toLocaleString()}
                                </div>
                            </div>
                            <span class="request-status status-${req.status}">${req.status}</span>
                        </div>
                        ${req.status === 'pending' ? `
                        <div class="request-actions">
                            <button class="action-btn btn-approve" onclick="processRequest(${req.id}, 'approve')">
                                ✓ Approve (+5 credits)
                            </button>
                            <button class="action-btn btn-reject" onclick="processRequest(${req.id}, 'reject')">
                                ✗ Reject
                            </button>
                        </div>
                        ` : ''}
                    </div>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }

        async function processRequest(requestId, action) {
            try {
                const response = await fetch('/api/admin/credit-requests/action', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${adminToken}`
                    },
                    body: JSON.stringify({request_id: requestId, action})
                });

                if (response.ok) {
                    alert(`Request ${action}ed successfully!`);
                    await loadAnalytics();
                    await loadRequests();
                } else {
                    alert('Failed to process request');
                }
            } catch (err) {
                alert('Network error');
            }
        }
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║         🚀 PROJECT-0 (web-MVP) Enhanced Edition 🚀        ║
    ║                                                            ║
    ║   ✨ New Features:                                         ║
    ║   • 🔐 Authentication & Registration                       ║
    ║   • ⚡ Credits System (3 free on signup)                  ║
    ║   • 💳 Credit Purchase System                             ║
    ║   • 👨‍💼 Admin Panel with Analytics                        ║
    ║   • 🌓 Dark/Light Theme Toggle                            ║
    ║                                                            ║
    ║   🌐 Main App: http://localhost:8000                      ║
    ║   🔧 Admin Panel: http://localhost:8000/admin             ║
    ║                                                            ║
    ║   👤 Admin Credentials:                                    ║
    ║   Username: Yernur@                                        ║
    ║   Password: ernur140707                                    ║
    ║                                                            ║
    ║   💰 Payment Info:                                         ║
    ║   Kaspi: +7-708-202-1308 (Канат Е.)                      ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
