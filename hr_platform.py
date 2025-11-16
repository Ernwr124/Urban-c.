"""
HR Agent Platform - Candidate Resume Analysis
FastAPI + SQLite + Ollama Cloud Integration
GitHub-inspired modern UI
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import io
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import (
    FastAPI, Request, Response, HTTPException, UploadFile, 
    File, Form, Depends, status, Cookie
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr
import httpx

# Optional imports for file parsing
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

try:
    from PIL import Image
    import pytesseract
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration"""
    DATABASE_URL = "sqlite:///./hr_platform.db"
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SESSION_LIFETIME_HOURS = 24
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "https://api.ollama.cloud/v1/chat/completions")
    OLLAMA_MODEL = "gpt-oss:20b-cloud"
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR = Path("./uploads")
    
    @classmethod
    def init(cls):
        """Initialize configuration"""
        cls.UPLOAD_DIR.mkdir(exist_ok=True)


# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)


class Analysis(Base):
    """Resume analysis model"""
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    filename = Column(String)
    file_path = Column(String)
    match_score = Column(Float)
    analysis_data = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    """Session model"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True)
    user_id = Column(Integer, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(Config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ============================================================================
# UTILITIES
# ============================================================================

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password"""
    return hash_password(password) == password_hash


def create_session_token() -> str:
    """Create unique session token"""
    return secrets.token_urlsafe(32)


def parse_pdf(file_content: bytes) -> str:
    """Parse PDF file"""
    if not PDF_SUPPORT:
        return "[PDF parsing not available - install PyPDF2]"
    
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"[Error parsing PDF: {str(e)}]"


def parse_docx(file_content: bytes) -> str:
    """Parse DOCX file"""
    if not DOCX_SUPPORT:
        return "[DOCX parsing not available - install python-docx]"
    
    try:
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"[Error parsing DOCX: {str(e)}]"


def parse_image(file_content: bytes) -> str:
    """Parse image using OCR"""
    if not OCR_SUPPORT:
        return "[OCR not available - install PIL and pytesseract]"
    
    try:
        image = Image.open(io.BytesIO(file_content))
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        return f"[Error parsing image: {str(e)}]"


def parse_resume(filename: str, file_content: bytes) -> str:
    """Parse resume based on file type"""
    ext = filename.lower().split('.')[-1]
    
    if ext == 'pdf':
        return parse_pdf(file_content)
    elif ext in ['docx', 'doc']:
        return parse_docx(file_content)
    elif ext in ['png', 'jpg', 'jpeg']:
        return parse_image(file_content)
    else:
        return "[Unsupported file format]"


async def analyze_resume_with_ollama(resume_text: str) -> Dict[str, Any]:
    """Analyze resume using Ollama Cloud"""
    
    prompt = f"""Analyze this resume and provide a detailed assessment in JSON format.

Resume:
{resume_text}

Return ONLY valid JSON with this structure:
{{
    "match_score": 0.0-100.0,
    "strengths": ["list of 3-5 key strengths"],
    "weaknesses": ["list of 3-5 areas for improvement"],
    "skills_match": {{
        "technical_skills": ["list"],
        "soft_skills": ["list"],
        "missing_skills": ["list"]
    }},
    "experience_assessment": "detailed text assessment of experience",
    "education_assessment": "detailed text assessment of education",
    "development_plan": ["list of 3-5 specific development recommendations"],
    "recommendations": ["list of 3-5 specific resume improvements"],
    "summary": "2-3 sentence overall summary"
}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                Config.OLLAMA_API_URL,
                headers={
                    "Authorization": f"Bearer {Config.OLLAMA_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": Config.OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are an expert HR analyst. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                try:
                    analysis_data = json.loads(content)
                    return analysis_data
                except json.JSONDecodeError:
                    return create_fallback_analysis(resume_text)
            else:
                return create_fallback_analysis(resume_text)
                
    except Exception as e:
        print(f"Ollama API error: {str(e)}")
        return create_fallback_analysis(resume_text)


def create_fallback_analysis(resume_text: str) -> Dict[str, Any]:
    """Create fallback analysis when Ollama is unavailable"""
    word_count = len(resume_text.split())
    
    return {
        "match_score": min(75.0, word_count / 10),
        "strengths": [
            "Resume provided with detailed information",
            "Structured content format",
            "Professional presentation"
        ],
        "weaknesses": [
            "AI analysis temporarily unavailable",
            "Manual review recommended"
        ],
        "skills_match": {
            "technical_skills": ["Detected from resume"],
            "soft_skills": ["Communication", "Teamwork"],
            "missing_skills": ["Analysis pending"]
        },
        "experience_assessment": f"Resume contains approximately {word_count} words. Full AI analysis pending.",
        "education_assessment": "Education section detected. Full analysis pending.",
        "development_plan": [
            "Complete detailed skills assessment",
            "Identify specific growth areas",
            "Create personalized learning path"
        ],
        "recommendations": [
            "Add quantifiable achievements",
            "Highlight key technical skills",
            "Include relevant certifications"
        ],
        "summary": "Resume received and basic processing completed. Full AI analysis will be available once the service is fully configured."
    }


# ============================================================================
# AUTHENTICATION
# ============================================================================

async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current authenticated user"""
    if not session_token:
        return None
    
    session = db.query(Session).filter(
        Session.session_token == session_token,
        Session.expires_at > datetime.utcnow()
    ).first()
    
    if not session:
        return None
    
    user = db.query(User).filter(User.id == session.user_id).first()
    return user


def require_auth(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authentication"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ============================================================================
# GITHUB-STYLE UI
# ============================================================================

GITHUB_CSS = """
:root {
    --color-canvas-default: #0d1117;
    --color-canvas-subtle: #161b22;
    --color-canvas-inset: #010409;
    --color-border-default: #30363d;
    --color-border-muted: #21262d;
    --color-fg-default: #e6edf3;
    --color-fg-muted: #7d8590;
    --color-fg-subtle: #6e7681;
    --color-accent: #58a6ff;
    --color-accent-emphasis: #1f6feb;
    --color-success: #3fb950;
    --color-attention: #d29922;
    --color-danger: #f85149;
    --color-btn-bg: #21262d;
    --color-btn-hover-bg: #30363d;
    --color-btn-active-bg: #292e36;
    --color-btn-primary-bg: #238636;
    --color-btn-primary-hover-bg: #2ea043;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
    background: var(--color-canvas-default);
    color: var(--color-fg-default);
    line-height: 1.5;
    font-size: 14px;
}

.header {
    background: var(--color-canvas-subtle);
    border-bottom: 1px solid var(--color-border-default);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-logo {
    font-size: 20px;
    font-weight: 600;
    color: var(--color-fg-default);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

.header-nav {
    display: flex;
    align-items: center;
    gap: 16px;
}

.header-nav a {
    color: var(--color-fg-default);
    text-decoration: none;
    font-size: 14px;
    padding: 8px 12px;
    border-radius: 6px;
    transition: background 0.2s;
}

.header-nav a:hover {
    background: var(--color-btn-hover-bg);
}

.header-user {
    color: var(--color-fg-muted);
    font-size: 14px;
    padding: 8px 12px;
}

.container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 32px 16px;
}

.container-sm {
    max-width: 768px;
    margin: 0 auto;
    padding: 32px 16px;
}

.box {
    background: var(--color-canvas-subtle);
    border: 1px solid var(--color-border-default);
    border-radius: 6px;
    padding: 24px;
    margin-bottom: 16px;
}

.box-header {
    padding-bottom: 16px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--color-border-default);
}

.box-row {
    padding: 16px 0;
    border-bottom: 1px solid var(--color-border-muted);
}

.box-row:last-child {
    border-bottom: none;
}

h1 {
    font-size: 32px;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--color-fg-default);
}

h2 {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 16px;
    color: var(--color-fg-default);
}

h3 {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 12px;
    color: var(--color-fg-default);
}

.text-muted {
    color: var(--color-fg-muted);
}

.text-small {
    font-size: 12px;
}

.btn {
    display: inline-block;
    padding: 5px 16px;
    font-size: 14px;
    font-weight: 500;
    line-height: 20px;
    border-radius: 6px;
    border: 1px solid var(--color-border-default);
    background: var(--color-btn-bg);
    color: var(--color-fg-default);
    text-decoration: none;
    cursor: pointer;
    transition: all 0.2s;
}

.btn:hover {
    background: var(--color-btn-hover-bg);
    border-color: var(--color-fg-subtle);
}

.btn-primary {
    background: var(--color-btn-primary-bg);
    color: #ffffff;
    border-color: transparent;
}

.btn-primary:hover {
    background: var(--color-btn-primary-hover-bg);
}

.btn-large {
    padding: 8px 20px;
    font-size: 16px;
}

.btn-block {
    display: block;
    width: 100%;
    text-align: center;
}

.form-group {
    margin-bottom: 16px;
}

.form-label {
    display: block;
    font-weight: 600;
    margin-bottom: 8px;
    font-size: 14px;
}

.form-control {
    width: 100%;
    padding: 5px 12px;
    font-size: 14px;
    line-height: 20px;
    color: var(--color-fg-default);
    background: var(--color-canvas-inset);
    border: 1px solid var(--color-border-default);
    border-radius: 6px;
    outline: none;
}

.form-control:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.3);
}

textarea.form-control {
    min-height: 100px;
    resize: vertical;
}

.alert {
    padding: 16px;
    border-radius: 6px;
    margin-bottom: 16px;
    border: 1px solid;
}

.alert-success {
    background: rgba(63, 185, 80, 0.15);
    border-color: var(--color-success);
    color: var(--color-success);
}

.alert-error {
    background: rgba(248, 81, 73, 0.15);
    border-color: var(--color-danger);
    color: var(--color-danger);
}

.alert-warning {
    background: rgba(210, 153, 34, 0.15);
    border-color: var(--color-attention);
    color: var(--color-attention);
}

.hero {
    text-align: center;
    padding: 80px 16px;
}

.hero h1 {
    font-size: 48px;
    margin-bottom: 16px;
}

.hero p {
    font-size: 20px;
    color: var(--color-fg-muted);
    max-width: 600px;
    margin: 0 auto 32px;
}

.hero-buttons {
    display: flex;
    gap: 12px;
    justify-content: center;
}

.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.stat-box {
    background: var(--color-canvas-inset);
    border: 1px solid var(--color-border-default);
    border-radius: 6px;
    padding: 16px;
    text-align: center;
}

.stat-value {
    font-size: 32px;
    font-weight: 600;
    color: var(--color-accent);
    display: block;
    margin-bottom: 4px;
}

.stat-label {
    font-size: 12px;
    color: var(--color-fg-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.score-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 120px;
    height: 120px;
    border-radius: 50%;
    font-size: 36px;
    font-weight: 700;
    margin: 24px auto;
    border: 3px solid;
}

.score-excellent {
    background: rgba(63, 185, 80, 0.15);
    border-color: var(--color-success);
    color: var(--color-success);
}

.score-good {
    background: rgba(210, 153, 34, 0.15);
    border-color: var(--color-attention);
    color: var(--color-attention);
}

.score-poor {
    background: rgba(248, 81, 73, 0.15);
    border-color: var(--color-danger);
    color: var(--color-danger);
}

.list {
    list-style: none;
    padding: 0;
}

.list-item {
    padding: 12px 0;
    border-bottom: 1px solid var(--color-border-muted);
    display: flex;
    align-items: flex-start;
    gap: 8px;
}

.list-item:last-child {
    border-bottom: none;
}

.list-item::before {
    content: "•";
    color: var(--color-accent);
    font-weight: bold;
    font-size: 16px;
}

.file-upload {
    border: 2px dashed var(--color-border-default);
    border-radius: 6px;
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
}

.file-upload:hover {
    border-color: var(--color-accent);
    background: var(--color-canvas-inset);
}

.file-upload input {
    display: none;
}

.file-icon {
    font-size: 48px;
    margin-bottom: 16px;
    opacity: 0.5;
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th {
    text-align: left;
    padding: 12px 8px;
    font-weight: 600;
    border-bottom: 1px solid var(--color-border-default);
    color: var(--color-fg-muted);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.table td {
    padding: 12px 8px;
    border-bottom: 1px solid var(--color-border-muted);
}

.table tr:last-child td {
    border-bottom: none;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
    border-radius: 12px;
    border: 1px solid;
}

.badge-success {
    background: rgba(63, 185, 80, 0.15);
    border-color: var(--color-success);
    color: var(--color-success);
}

.badge-warning {
    background: rgba(210, 153, 34, 0.15);
    border-color: var(--color-attention);
    color: var(--color-attention);
}

.badge-danger {
    background: rgba(248, 81, 73, 0.15);
    border-color: var(--color-danger);
    color: var(--color-danger);
}

.progress {
    width: 100%;
    height: 8px;
    background: var(--color-canvas-inset);
    border-radius: 4px;
    overflow: hidden;
    margin: 8px 0;
}

.progress-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
}

.progress-bar-success {
    background: var(--color-success);
}

.progress-bar-warning {
    background: var(--color-attention);
}

.progress-bar-danger {
    background: var(--color-danger);
}

.section {
    margin-bottom: 32px;
}

.grid {
    display: grid;
    gap: 16px;
}

.grid-2 {
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

@media (max-width: 768px) {
    .header {
        padding: 16px;
        flex-direction: column;
        gap: 12px;
    }
    
    .hero h1 {
        font-size: 32px;
    }
    
    .hero p {
        font-size: 16px;
    }
    
    .hero-buttons {
        flex-direction: column;
    }
    
    .stats {
        grid-template-columns: 1fr;
    }
}
"""


def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Generate base HTML with GitHub-style navigation"""
    
    if user:
        nav_links = f"""
            <span class="header-user">{user.email}</span>
            <a href="/dashboard">Dashboard</a>
            <a href="/upload">Upload</a>
            <a href="/profile">Profile</a>
            <a href="/logout">Sign out</a>
        """
    else:
        nav_links = """
            <a href="/login">Sign in</a>
            <a href="/register">Sign up</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Resume Analyzer</title>
    <style>{GITHUB_CSS}</style>
</head>
<body>
    <header class="header">
        <a href="/" class="header-logo">
            <span>📄</span> Resume Analyzer
        </a>
        <nav class="header-nav">
            {nav_links}
        </nav>
    </header>
    <main>
        {content}
    </main>
</body>
</html>"""


# ============================================================================
# PAGE TEMPLATES
# ============================================================================

def landing_page() -> str:
    """Landing page"""
    content = """
    <div class="hero">
        <h1>AI-Powered Resume Analysis</h1>
        <p>Get instant feedback on your resume with detailed insights, skill assessments, and personalized development recommendations</p>
        <div class="hero-buttons">
            <a href="/register" class="btn btn-primary btn-large">Get Started →</a>
            <a href="/login" class="btn btn-large">Sign In</a>
        </div>
    </div>
    
    <div class="container">
        <div class="grid grid-2">
            <div class="box">
                <h3>🎯 Smart Analysis</h3>
                <p class="text-muted">Upload your resume and receive comprehensive AI-powered analysis including strengths, weaknesses, and match scoring.</p>
            </div>
            
            <div class="box">
                <h3>📊 Detailed Insights</h3>
                <p class="text-muted">Get breakdown of technical skills, soft skills, experience assessment, and education evaluation.</p>
            </div>
            
            <div class="box">
                <h3>🚀 Development Plan</h3>
                <p class="text-muted">Receive personalized recommendations for career growth and resume improvements.</p>
            </div>
            
            <div class="box">
                <h3>📈 Track Progress</h3>
                <p class="text-muted">Monitor your resume improvements over time with analysis history and score tracking.</p>
            </div>
        </div>
    </div>
    """
    return get_base_html("Home", content)


def login_page(error: str = "") -> str:
    """Login page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div class="box" style="margin-top: 48px;">
            <h2 style="text-align: center;">Sign in to Resume Analyzer</h2>
            
            {error_html}
            
            <form method="POST" action="/login" style="margin-top: 24px;">
                <div class="form-group">
                    <label class="form-label">Email address</label>
                    <input type="email" name="email" class="form-control" required autocomplete="email">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required autocomplete="current-password">
                </div>
                
                <button type="submit" class="btn btn-primary btn-block btn-large">Sign in</button>
            </form>
            
            <div style="text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--color-border-default);">
                <p class="text-muted">New to Resume Analyzer? <a href="/register" style="color: var(--color-accent);">Create an account</a></p>
            </div>
        </div>
    </div>
    """
    return get_base_html("Sign in", content)


def register_page(error: str = "") -> str:
    """Register page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div class="box" style="margin-top: 48px;">
            <h2 style="text-align: center;">Create your account</h2>
            
            {error_html}
            
            <form method="POST" action="/register" style="margin-top: 24px;">
                <div class="form-group">
                    <label class="form-label">Full name</label>
                    <input type="text" name="full_name" class="form-control" required autocomplete="name">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email address</label>
                    <input type="email" name="email" class="form-control" required autocomplete="email">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required autocomplete="new-password" minlength="6">
                    <p class="text-muted text-small" style="margin-top: 4px;">At least 6 characters</p>
                </div>
                
                <button type="submit" class="btn btn-primary btn-block btn-large">Create account</button>
            </form>
            
            <div style="text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--color-border-default);">
                <p class="text-muted">Already have an account? <a href="/login" style="color: var(--color-accent);">Sign in</a></p>
            </div>
        </div>
    </div>
    """
    return get_base_html("Sign up", content)


def dashboard_page(user: User, db: Session) -> str:
    """Dashboard page"""
    
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    recent_analyses = db.query(Analysis).filter(
        Analysis.user_id == user.id
    ).order_by(Analysis.created_at.desc()).limit(10).all()
    
    avg_score = db.query(Analysis).filter(
        Analysis.user_id == user.id,
        Analysis.match_score.isnot(None)
    ).all()
    
    avg_score_value = sum([a.match_score for a in avg_score]) / len(avg_score) if avg_score else 0
    latest_score = recent_analyses[0].match_score if recent_analyses else 0
    
    recent_list = ""
    for analysis in recent_analyses:
        if analysis.match_score >= 70:
            badge_class = "badge-success"
        elif analysis.match_score >= 50:
            badge_class = "badge-warning"
        else:
            badge_class = "badge-danger"
        
        recent_list += f"""
        <tr>
            <td><strong>{analysis.filename}</strong></td>
            <td><span class="badge {badge_class}">{analysis.match_score:.0f}%</span></td>
            <td class="text-muted text-small">{analysis.created_at.strftime('%b %d, %Y at %H:%M')}</td>
            <td><a href="/analysis/{analysis.id}" class="btn" style="padding: 2px 12px;">View →</a></td>
        </tr>
        """
    
    if not recent_list:
        recent_list = '<tr><td colspan="4" style="text-align: center;" class="text-muted">No analyses yet. <a href="/upload" style="color: var(--color-accent);">Upload your first resume</a></td></tr>'
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 24px;">
            <h1>Dashboard</h1>
            <p class="text-muted">Welcome back, {user.full_name}</p>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <span class="stat-value">{total_analyses}</span>
                <span class="stat-label">Total Analyses</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{avg_score_value:.0f}%</span>
                <span class="stat-label">Average Score</span>
            </div>
            <div class="stat-box">
                <span class="stat-value">{latest_score:.0f}%</span>
                <span class="stat-label">Latest Score</span>
            </div>
        </div>
        
        <div class="box">
            <div class="box-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0;">Recent Analyses</h3>
                    <a href="/upload" class="btn btn-primary">Upload Resume</a>
                </div>
            </div>
            
            <table class="table">
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Score</th>
                        <th>Date</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {recent_list}
                </tbody>
            </table>
        </div>
    </div>
    """
    return get_base_html("Dashboard", content, user)


def profile_page(user: User, db: Session) -> str:
    """Profile page"""
    
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    
    content = f"""
    <div class="container-sm">
        <h1>Profile</h1>
        
        <div class="box">
            <h3>Account information</h3>
            <div class="box-row">
                <div class="text-muted text-small">FULL NAME</div>
                <div>{user.full_name}</div>
            </div>
            <div class="box-row">
                <div class="text-muted text-small">EMAIL</div>
                <div>{user.email}</div>
            </div>
            <div class="box-row">
                <div class="text-muted text-small">MEMBER SINCE</div>
                <div>{user.created_at.strftime('%B %d, %Y')}</div>
            </div>
            <div class="box-row">
                <div class="text-muted text-small">TOTAL ANALYSES</div>
                <div>{total_analyses}</div>
            </div>
        </div>
    </div>
    """
    return get_base_html("Profile", content, user)


def upload_page(user: User, message: str = "", error: str = "") -> str:
    """Upload page"""
    message_html = f'<div class="alert alert-success">{message}</div>' if message else ""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <h1>Upload Resume</h1>
        <p class="text-muted">Upload your resume for AI-powered analysis and insights</p>
        
        {message_html}
        {error_html}
        
        <div class="box" style="margin-top: 24px;">
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <div class="file-upload" onclick="document.getElementById('file-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="file-input" name="file" accept=".pdf,.docx,.doc,.png,.jpg,.jpeg" required onchange="updateFileName(this)">
                    <p id="file-name" style="font-weight: 600; margin-bottom: 8px;">Click to upload or drag and drop</p>
                    <p class="text-muted text-small">Supported formats: PDF, DOCX, PNG, JPG (max 10MB)</p>
                </div>
                
                <button type="submit" class="btn btn-primary btn-block btn-large" style="margin-top: 16px;">Analyze Resume</button>
            </form>
        </div>
    </div>
    
    <script>
    function updateFileName(input) {{
        const fileName = (input.files && input.files[0]) ? input.files[0].name : 'Click to upload or drag and drop';
        document.getElementById('file-name').textContent = fileName;
    }}
    </script>
    """
    return get_base_html("Upload Resume", content, user)


def analysis_result_page(user: User, analysis: Analysis) -> str:
    """Analysis result page"""
    
    analysis_data = json.loads(analysis.analysis_data)
    score = analysis.match_score
    
    if score >= 70:
        score_class = "score-excellent"
        score_text = "Excellent"
    elif score >= 50:
        score_class = "score-good"
        score_text = "Good"
    else:
        score_class = "score-poor"
        score_text = "Needs Improvement"
    
    strengths_html = "".join([f'<li class="list-item">{s}</li>' for s in analysis_data.get('strengths', [])])
    weaknesses_html = "".join([f'<li class="list-item">{s}</li>' for s in analysis_data.get('weaknesses', [])])
    dev_plan_html = "".join([f'<li class="list-item">{s}</li>' for s in analysis_data.get('development_plan', [])])
    recommendations_html = "".join([f'<li class="list-item">{s}</li>' for s in analysis_data.get('recommendations', [])])
    
    tech_skills = analysis_data.get('skills_match', {}).get('technical_skills', [])
    soft_skills = analysis_data.get('skills_match', {}).get('soft_skills', [])
    missing_skills = analysis_data.get('skills_match', {}).get('missing_skills', [])
    
    tech_skills_html = "".join([f'<span class="badge badge-success" style="margin: 4px;">{s}</span>' for s in tech_skills])
    soft_skills_html = "".join([f'<span class="badge badge-success" style="margin: 4px;">{s}</span>' for s in soft_skills])
    missing_skills_html = "".join([f'<span class="badge badge-warning" style="margin: 4px;">{s}</span>' for s in missing_skills])
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 24px;">
            <a href="/dashboard" class="btn">← Back to Dashboard</a>
        </div>
        
        <div class="box" style="text-align: center;">
            <h3>{analysis.filename}</h3>
            <p class="text-muted text-small">{analysis.created_at.strftime('%B %d, %Y at %H:%M')}</p>
            <div class="score-badge {score_class}">{score:.0f}%</div>
            <h2>{score_text}</h2>
            <p class="text-muted">{analysis_data.get('summary', '')}</p>
        </div>
        
        <div class="grid grid-2">
            <div class="box">
                <h3>✅ Strengths</h3>
                <ul class="list">
                    {strengths_html}
                </ul>
            </div>
            
            <div class="box">
                <h3>⚠️ Areas for Improvement</h3>
                <ul class="list">
                    {weaknesses_html}
                </ul>
            </div>
        </div>
        
        <div class="box">
            <h3>💼 Experience Assessment</h3>
            <p class="text-muted">{analysis_data.get('experience_assessment', 'N/A')}</p>
        </div>
        
        <div class="box">
            <h3>🎓 Education Assessment</h3>
            <p class="text-muted">{analysis_data.get('education_assessment', 'N/A')}</p>
        </div>
        
        <div class="box">
            <h3>🛠️ Skills Overview</h3>
            <div class="section">
                <h4 class="text-muted text-small">TECHNICAL SKILLS</h4>
                <div>{tech_skills_html if tech_skills_html else '<span class="text-muted">No technical skills detected</span>'}</div>
            </div>
            <div class="section">
                <h4 class="text-muted text-small">SOFT SKILLS</h4>
                <div>{soft_skills_html if soft_skills_html else '<span class="text-muted">No soft skills detected</span>'}</div>
            </div>
            <div class="section">
                <h4 class="text-muted text-small">RECOMMENDED SKILLS TO ADD</h4>
                <div>{missing_skills_html if missing_skills_html else '<span class="text-muted">No recommendations</span>'}</div>
            </div>
        </div>
        
        <div class="box">
            <h3>🚀 Development Plan</h3>
            <p class="text-muted" style="margin-bottom: 16px;">Personalized recommendations to advance your career</p>
            <ul class="list">
                {dev_plan_html}
            </ul>
        </div>
        
        <div class="box">
            <h3>📝 Resume Recommendations</h3>
            <p class="text-muted" style="margin-bottom: 16px;">Specific improvements to make your resume stand out</p>
            <ul class="list">
                {recommendations_html}
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 32px;">
            <a href="/upload" class="btn btn-primary btn-large">Analyze Another Resume</a>
        </div>
    </div>
    """
    return get_base_html("Analysis Results", content, user)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

app = FastAPI(title="Resume Analyzer", version="2.0.0")


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    Config.init()
    init_db()
    print("Resume Analyzer initialized successfully")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Landing page"""
    return landing_page()


@app.get("/login", response_class=HTMLResponse)
async def login_get():
    """Login page"""
    return login_page()


@app.post("/login")
async def login_post(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle login"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse(login_page(error="Invalid email or password"))
    
    # Create session
    session_token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    
    session = Session(
        session_token=session_token,
        user_id=user.id,
        expires_at=expires_at
    )
    db.add(session)
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Set cookie
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=Config.SESSION_LIFETIME_HOURS * 3600
    )
    
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_get():
    """Register page"""
    return register_page()


@app.post("/register")
async def register_post(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle registration"""
    
    # Check if user exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return HTMLResponse(register_page(error="Email already registered"))
    
    # Create user
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name
    )
    db.add(user)
    db.commit()
    
    return RedirectResponse(url="/login", status_code=302)


@app.get("/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    """Handle logout"""
    if session_token:
        db.query(Session).filter(Session.session_token == session_token).delete()
        db.commit()
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Dashboard page"""
    return dashboard_page(user, db)


@app.get("/profile", response_class=HTMLResponse)
async def profile(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Profile page"""
    return profile_page(user, db)


@app.get("/upload", response_class=HTMLResponse)
async def upload_get(user: User = Depends(require_auth)):
    """Upload page"""
    return upload_page(user)


@app.post("/upload")
async def upload_post(
    file: UploadFile = File(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle file upload and analysis"""
    
    # Validate file size
    file_content = await file.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(upload_page(user, error="File too large (max 10MB)"))
    
    # Save file
    file_path = Config.UPLOAD_DIR / f"{user.id}_{datetime.utcnow().timestamp()}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Parse resume
    resume_text = parse_resume(file.filename, file_content)
    
    # Analyze with Ollama
    analysis_data = await analyze_resume_with_ollama(resume_text)
    
    # Save analysis
    analysis = Analysis(
        user_id=user.id,
        filename=file.filename,
        file_path=str(file_path),
        match_score=analysis_data.get("match_score", 0),
        analysis_data=json.dumps(analysis_data)
    )
    db.add(analysis)
    db.commit()
    
    return RedirectResponse(url=f"/analysis/{analysis.id}", status_code=302)


@app.get("/analysis/{analysis_id}", response_class=HTMLResponse)
async def analysis_detail(
    analysis_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Analysis detail page"""
    
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return analysis_result_page(user, analysis)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "hr_platform:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
