"""
HR Agent - AI-Powered Job Match Analysis
Compare your resume with job descriptions using Ollama (gpt-oss:20b-cloud)
Minimalist Black & White Design
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


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration"""
    DATABASE_URL = "sqlite:///./hr_agent.db"
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SESSION_LIFETIME_HOURS = 24
    OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = "gpt-oss:20b-cloud"
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR = Path("./uploads")
    
    @classmethod
    def init(cls):
        """Initialize configuration"""
        cls.UPLOAD_DIR.mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "avatars").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "resumes").mkdir(exist_ok=True)


# ============================================================================
# DATABASE MODELS
# ============================================================================

Base = declarative_base()


class User(Base):
    """User model - LinkedIn-style profile"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    
    # Profile information
    headline = Column(String, default="")  # e.g. "Senior Software Engineer at Company"
    location = Column(String, default="")
    bio = Column(Text, default="")
    phone = Column(String, default="")
    
    # Profile media
    avatar = Column(String, default="")  # Path to avatar image
    resume_file = Column(String, default="")  # Path to uploaded resume
    
    # Social links
    linkedin_url = Column(String, default="")
    github_url = Column(String, default="")
    website = Column(String, default="")
    
    # Meta
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)


class Analysis(Base):
    """Job match analysis model"""
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    filename = Column(String)
    file_path = Column(String)
    job_description = Column(Text)
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


def parse_resume(filename: str, file_content: bytes) -> str:
    """Parse resume based on file type"""
    ext = filename.lower().split('.')[-1]
    
    if ext == 'pdf':
        return parse_pdf(file_content)
    elif ext in ['docx', 'doc']:
        return parse_docx(file_content)
    else:
        return "[Unsupported file format]"


async def compare_resume_with_job(resume_text: str, job_description: str) -> Dict[str, Any]:
    """Compare resume with job description using Ollama"""
    
    prompt = f"""Compare this resume with the job description and provide detailed analysis in JSON format.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Analyze and return ONLY valid JSON with this exact structure:
{{
    "match_score": 0-100,
    "pros": ["list of 5-7 strengths that match job requirements"],
    "cons": ["list of 5-7 gaps or missing requirements"],
    "skills_match": {{
        "matched_skills": ["skills that match"],
        "missing_skills": ["required skills not in resume"],
        "additional_skills": ["extra skills candidate has"]
    }},
    "experience_match": {{
        "score": 0-100,
        "analysis": "detailed comparison text"
    }},
    "education_match": {{
        "score": 0-100,
        "analysis": "detailed comparison text"
    }},
    "recommendations": ["5-7 specific actions to improve match"],
    "summary": "2-3 sentence overall assessment"
}}

Return only the JSON, no other text."""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                Config.OLLAMA_API_URL,
                json={
                    "model": Config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "{}")
                
                try:
                    # Try to parse as JSON
                    analysis_data = json.loads(response_text)
                    return analysis_data
                except json.JSONDecodeError:
                    print(f"JSON decode error. Response: {response_text[:200]}")
                    return create_fallback_comparison(resume_text, job_description)
            else:
                print(f"Ollama API error: {response.status_code}")
                return create_fallback_comparison(resume_text, job_description)
                
    except Exception as e:
        print(f"Ollama connection error: {str(e)}")
        return create_fallback_comparison(resume_text, job_description)


def create_fallback_comparison(resume_text: str, job_description: str) -> Dict[str, Any]:
    """Create fallback comparison when Ollama is unavailable"""
    resume_words = set(resume_text.lower().split())
    job_words = set(job_description.lower().split())
    
    common_words = resume_words.intersection(job_words)
    match_score = min(85.0, (len(common_words) / max(len(job_words), 1)) * 100)
    
    return {
        "match_score": match_score,
        "pros": [
            "Resume format is professional and well-structured",
            "Contains relevant industry experience",
            "Demonstrates technical capabilities",
            "Shows career progression",
            "Good educational foundation"
        ],
        "cons": [
            "Some job requirements need verification",
            "Could emphasize more quantifiable achievements",
            "Additional certifications may be beneficial",
            "Some technical skills require confirmation",
            "Experience depth needs manual review"
        ],
        "skills_match": {
            "matched_skills": ["Communication", "Problem Solving", "Teamwork"],
            "missing_skills": ["Waiting for Ollama analysis"],
            "additional_skills": ["Professional experience"]
        },
        "experience_match": {
            "score": 70,
            "analysis": "Resume shows relevant experience. Full analysis requires Ollama connection."
        },
        "education_match": {
            "score": 75,
            "analysis": "Education background present. Detailed comparison requires Ollama."
        },
        "recommendations": [
            "Ensure Ollama is running: ollama serve",
            "Pull model: ollama pull gpt-oss:20b-cloud",
            "Highlight achievements with metrics",
            "Align resume keywords with job description",
            "Add relevant certifications"
        ],
        "summary": f"Basic analysis shows {match_score:.0f}% keyword match. Connect Ollama for full AI-powered analysis using gpt-oss:20b-cloud model."
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
# MINIMALIST BLACK & WHITE UI
# ============================================================================

MINIMALIST_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --black: #000000;
    --white: #ffffff;
    --gray-light: #f5f5f5;
    --gray-border: #e0e0e0;
    --gray-text: #666666;
    --success: #22c55e;
    --warning: #eab308;
    --danger: #ef4444;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--black);
    color: var(--white);
    line-height: 1.6;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
}

.nav {
    background: var(--black);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    position: sticky;
    top: 0;
    z-index: 50;
    backdrop-filter: blur(10px);
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 72px;
}

.nav-logo {
    font-size: 24px;
    font-weight: 700;
    color: var(--white);
    text-decoration: none;
    letter-spacing: -0.5px;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 32px;
}

.nav-link {
    color: rgba(255, 255, 255, 0.7);
    text-decoration: none;
    font-size: 15px;
    font-weight: 500;
    transition: color 0.2s;
}

.nav-link:hover {
    color: var(--white);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 64px 32px;
}

.container-sm {
    max-width: 600px;
    margin: 0 auto;
    padding: 64px 32px;
}

.hero {
    text-align: center;
    padding: 120px 32px 80px;
}

.hero h1 {
    font-size: 64px;
    font-weight: 700;
    margin-bottom: 24px;
    letter-spacing: -2px;
    line-height: 1.1;
}

.hero p {
    font-size: 20px;
    color: rgba(255, 255, 255, 0.7);
    max-width: 600px;
    margin: 0 auto 48px;
    line-height: 1.6;
}

.card {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 40px;
    backdrop-filter: blur(10px);
    margin-bottom: 24px;
}

.card:hover {
    border-color: rgba(255, 255, 255, 0.2);
    transition: border-color 0.3s;
}

h1 {
    font-size: 40px;
    font-weight: 700;
    margin-bottom: 16px;
    letter-spacing: -1px;
}

h2 {
    font-size: 32px;
    font-weight: 600;
    margin-bottom: 16px;
    letter-spacing: -0.5px;
}

h3 {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 16px;
}

.text-muted {
    color: rgba(255, 255, 255, 0.6);
}

.text-sm {
    font-size: 14px;
}

.text-xs {
    font-size: 12px;
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 14px 32px;
    font-size: 15px;
    font-weight: 600;
    border-radius: 12px;
    border: 2px solid var(--white);
    background: var(--white);
    color: var(--black);
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    gap: 8px;
}

.btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(255, 255, 255, 0.2);
}

.btn-outline {
    background: transparent;
    color: var(--white);
}

.btn-outline:hover {
    background: var(--white);
    color: var(--black);
}

.btn-large {
    padding: 18px 40px;
    font-size: 16px;
}

.btn-block {
    display: flex;
    width: 100%;
}

.form-group {
    margin-bottom: 24px;
}

.form-label {
    display: block;
    font-weight: 600;
    margin-bottom: 12px;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.form-control {
    width: 100%;
    padding: 16px 20px;
    font-size: 15px;
    color: var(--white);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    outline: none;
    transition: all 0.2s;
    font-family: inherit;
}

.form-control:focus {
    border-color: var(--white);
    background: rgba(255, 255, 255, 0.08);
}

textarea.form-control {
    min-height: 240px;
    resize: vertical;
    line-height: 1.6;
}

.alert {
    padding: 20px 24px;
    border-radius: 12px;
    margin-bottom: 24px;
    border: 1px solid;
}

.alert-success {
    background: rgba(34, 197, 94, 0.1);
    border-color: var(--success);
    color: var(--success);
}

.alert-error {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--danger);
    color: var(--danger);
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 24px;
    margin-bottom: 48px;
}

.stat-card {
    background: var(--white);
    color: var(--black);
    border-radius: 16px;
    padding: 32px;
    text-align: center;
}

.stat-value {
    font-size: 48px;
    font-weight: 700;
    margin-bottom: 8px;
    letter-spacing: -1px;
}

.stat-label {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.7;
}

.score-display {
    text-align: center;
    padding: 48px;
}

.score-circle {
    width: 180px;
    height: 180px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 0 auto 32px;
    border: 8px solid;
    position: relative;
}

.score-circle.excellent {
    background: rgba(34, 197, 94, 0.1);
    border-color: var(--success);
    color: var(--success);
}

.score-circle.good {
    background: rgba(234, 179, 8, 0.1);
    border-color: var(--warning);
    color: var(--warning);
}

.score-circle.poor {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--danger);
    color: var(--danger);
}

.score-value {
    font-size: 56px;
    font-weight: 700;
    letter-spacing: -2px;
}

.score-label {
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.8;
}

.grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 24px;
}

.feature-list {
    list-style: none;
}

.feature-item {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 16px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.feature-item:last-child {
    border-bottom: none;
}

.feature-icon {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 700;
}

.feature-icon.pro {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success);
}

.feature-icon.con {
    background: rgba(239, 68, 68, 0.2);
    color: var(--danger);
}

.feature-icon.tip {
    background: rgba(255, 255, 255, 0.1);
    color: var(--white);
}

.badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    margin: 4px;
}

.badge-success {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success);
    border: 1px solid var(--success);
}

.badge-warning {
    background: rgba(234, 179, 8, 0.2);
    color: var(--warning);
    border: 1px solid var(--warning);
}

.badge-info {
    background: rgba(255, 255, 255, 0.1);
    color: var(--white);
    border: 1px solid rgba(255, 255, 255, 0.2);
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th {
    text-align: left;
    padding: 16px 12px;
    font-weight: 600;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.6);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.table td {
    padding: 20px 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.table tr:last-child td {
    border-bottom: none;
}

.file-upload {
    border: 2px dashed rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    padding: 64px 32px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
    background: rgba(255, 255, 255, 0.02);
}

.file-upload:hover {
    border-color: var(--white);
    background: rgba(255, 255, 255, 0.05);
}

.file-upload input {
    display: none;
}

.file-icon {
    font-size: 56px;
    margin-bottom: 24px;
    opacity: 0.6;
}

.progress-bar {
    width: 100%;
    height: 12px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    overflow: hidden;
    margin: 16px 0;
}

.progress-fill {
    height: 100%;
    background: var(--white);
    border-radius: 6px;
    transition: width 0.5s;
}

.section {
    margin-bottom: 40px;
}

.divider {
    height: 1px;
    background: rgba(255, 255, 255, 0.1);
    margin: 40px 0;
}

.flex-between {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

@media (max-width: 768px) {
    .hero h1 {
        font-size: 40px;
    }
    
    .hero p {
        font-size: 16px;
    }
    
    .nav-container {
        padding: 0 16px;
    }
    
    .container {
        padding: 40px 16px;
    }
    
    .card {
        padding: 24px;
    }
    
    .grid-2 {
        grid-template-columns: 1fr;
    }
    
    .stats-grid {
        grid-template-columns: 1fr;
    }
}
"""


def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Generate base HTML"""
    
    if user:
        nav_links = f"""
            <a href="/dashboard" class="nav-link">Dashboard</a>
            <a href="/analyze" class="nav-link">Analyze</a>
            <a href="/profile" class="nav-link">{user.full_name}</a>
            <a href="/logout" class="nav-link">Sign out</a>
        """
    else:
        nav_links = """
            <a href="/login" class="nav-link">Sign in</a>
            <a href="/register" class="btn">Get Started</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HR Agent</title>
    <style>{MINIMALIST_CSS}</style>
</head>
<body>
    <nav class="nav">
        <div class="nav-container">
            <a href="/" class="nav-logo">HR Agent</a>
            <div class="nav-links">
                {nav_links}
            </div>
        </div>
    </nav>
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
        <h1>Match Your Resume<br>with Your Dream Job</h1>
        <p>AI-powered analysis that compares your resume with job descriptions. Get instant feedback on how well you match the position.</p>
        <div style="display: flex; gap: 16px; justify-content: center;">
            <a href="/register" class="btn btn-large">Get Started</a>
            <a href="/login" class="btn btn-outline btn-large">Sign In</a>
        </div>
    </div>
    
    <div class="container">
        <div class="grid-2">
            <div class="card">
                <h3>Match Percentage</h3>
                <p class="text-muted">See exactly how well your resume aligns with job requirements. Clear percentage score with detailed breakdown.</p>
            </div>
            
            <div class="card">
                <h3>Pros & Cons</h3>
                <p class="text-muted">Discover your strengths for the position and areas where you need improvement. Honest, actionable feedback.</p>
            </div>
            
            <div class="card">
                <h3>Skills Analysis</h3>
                <p class="text-muted">Identify matched skills, missing requirements, and additional qualifications you bring to the table.</p>
            </div>
            
            <div class="card">
                <h3>Smart Recommendations</h3>
                <p class="text-muted">Get specific advice on improving your match score. Powered by Ollama AI (gpt-oss:20b-cloud).</p>
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
        <div class="card">
            <h2>Welcome back</h2>
            <p class="text-muted" style="margin-bottom: 32px;">Sign in to your HR Agent account</p>
            
            {error_html}
            
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="you@example.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required placeholder="••••••••">
                </div>
                
                <button type="submit" class="btn btn-block btn-large">Sign In</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Don't have an account? <a href="/register" style="color: var(--white); text-decoration: underline;">Create one</a>
            </p>
        </div>
    </div>
    """
    return get_base_html("Sign in", content)


def register_page(error: str = "") -> str:
    """Register page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div class="card">
            <h2>Create account</h2>
            <p class="text-muted" style="margin-bottom: 32px;">Get started with HR Agent</p>
            
            {error_html}
            
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Full Name</label>
                    <input type="text" name="full_name" class="form-control" required placeholder="John Doe">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="you@example.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required minlength="6" placeholder="Minimum 6 characters">
                </div>
                
                <button type="submit" class="btn btn-block btn-large">Create Account</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Already have an account? <a href="/login" style="color: var(--white); text-decoration: underline;">Sign in</a>
            </p>
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
            badge_class = "badge-warning"
        
        recent_list += f"""
        <tr>
            <td>
                <strong>{analysis.filename}</strong>
                <div class="text-muted text-xs">{analysis.created_at.strftime('%b %d, %Y at %H:%M')}</div>
            </td>
            <td><span class="{badge_class}">{analysis.match_score:.0f}%</span></td>
            <td><a href="/result/{analysis.id}" class="btn btn-outline" style="padding: 8px 20px;">View</a></td>
        </tr>
        """
    
    if not recent_list:
        recent_list = '<tr><td colspan="3" style="text-align: center;" class="text-muted">No analyses yet. <a href="/analyze" style="color: var(--white); text-decoration: underline;">Create your first one</a></td></tr>'
    
    content = f"""
    <div class="container">
        <div class="flex-between" style="margin-bottom: 48px;">
            <div>
                <h1>Dashboard</h1>
                <p class="text-muted">Welcome back, {user.full_name}</p>
            </div>
            <a href="/analyze" class="btn btn-large">New Analysis</a>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">Analyses</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_score_value:.0f}%</div>
                <div class="stat-label">Avg Match</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{latest_score:.0f}%</div>
                <div class="stat-label">Latest</div>
            </div>
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 24px;">Recent Analyses</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Resume & Date</th>
                        <th>Score</th>
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
    """LinkedIn-style profile page"""
    
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    
    # Avatar display
    avatar_url = f"/uploads/avatars/{user.avatar}" if user.avatar else ""
    avatar_html = f'<img src="{avatar_url}" alt="Avatar" class="profile-avatar">' if user.avatar else '<div class="profile-avatar-placeholder">{user.full_name[0].upper()}</div>'
    
    # Resume download
    resume_html = ""
    if user.resume_file:
        resume_html = f'<a href="/download-resume" class="btn btn-outline" style="padding: 8px 20px;">📄 Download Resume</a>'
    
    # Social links
    social_links = ""
    if user.linkedin_url:
        social_links += f'<a href="{user.linkedin_url}" target="_blank" class="social-link">LinkedIn</a>'
    if user.github_url:
        social_links += f'<a href="{user.github_url}" target="_blank" class="social-link">GitHub</a>'
    if user.website:
        social_links += f'<a href="{user.website}" target="_blank" class="social-link">Website</a>'
    
    content = f"""
    <div class="container">
        <!-- Profile Header Card -->
        <div class="profile-header-card">
            <div class="profile-cover"></div>
            <div class="profile-header-content">
                <div class="profile-avatar-section">
                    {avatar_html}
                </div>
                <div class="profile-header-info">
                    <h1 style="font-size: 32px; margin-bottom: 8px;">{user.full_name}</h1>
                    <p class="profile-headline">{user.headline or 'Add your headline'}</p>
                    <p class="text-muted text-sm">{user.location or 'Add your location'} • {total_analyses} analyses</p>
                    <div class="profile-actions">
                        <a href="/edit-profile" class="btn btn-primary">Edit Profile</a>
                        {resume_html}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="grid-2" style="align-items: start;">
            <!-- Left Column -->
            <div>
                <!-- About Section -->
                <div class="card">
                    <div class="flex-between" style="margin-bottom: 20px;">
                        <h3>About</h3>
                        <a href="/edit-profile#about" class="btn btn-outline" style="padding: 6px 16px;">Edit</a>
                    </div>
                    <p class="text-muted">{user.bio or 'Tell us about yourself, your experience, and what makes you unique.'}</p>
                </div>
                
                <!-- Contact Section -->
                <div class="card">
                    <h3 style="margin-bottom: 20px;">Contact Information</h3>
                    <div class="contact-info">
                        <div class="contact-item">
                            <span class="contact-label">Email</span>
                            <span class="contact-value">{user.email}</span>
                        </div>
                        {f'<div class="contact-item"><span class="contact-label">Phone</span><span class="contact-value">{user.phone}</span></div>' if user.phone else ''}
                    </div>
                </div>
                
                <!-- Social Links -->
                {f'<div class="card"><h3 style="margin-bottom: 20px;">Social Links</h3><div style="display: flex; gap: 12px; flex-wrap: wrap;">{social_links}</div></div>' if social_links else ''}
            </div>
            
            <!-- Right Column -->
            <div>
                <!-- Resume Section -->
                <div class="card">
                    <div class="flex-between" style="margin-bottom: 20px;">
                        <h3>Resume</h3>
                        <a href="/upload-resume-profile" class="btn btn-outline" style="padding: 6px 16px;">Upload</a>
                    </div>
                    {f'<div class="resume-preview"><p>📄 {user.resume_file.split("/")[-1] if "/" in user.resume_file else user.resume_file}</p><a href="/download-resume" class="btn btn-outline" style="padding: 6px 16px; margin-top: 12px;">Download</a></div>' if user.resume_file else '<p class="text-muted">Upload your resume to use it for quick job matching</p>'}
                </div>
                
                <!-- Stats Section -->
                <div class="card">
                    <h3 style="margin-bottom: 20px;">Activity</h3>
                    <div class="stat-item">
                        <span class="stat-item-value">{total_analyses}</span>
                        <span class="stat-item-label">Job Analyses</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-item-value">{user.created_at.strftime('%b %Y')}</span>
                        <span class="stat-item-label">Member Since</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <style>
    .profile-header-card {{
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        overflow: hidden;
        margin-bottom: 24px;
    }}
    
    .profile-cover {{
        height: 120px;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
    }}
    
    .profile-header-content {{
        padding: 0 40px 32px;
        position: relative;
    }}
    
    .profile-avatar-section {{
        margin-top: -60px;
        margin-bottom: 16px;
    }}
    
    .profile-avatar {{
        width: 140px;
        height: 140px;
        border-radius: 50%;
        border: 4px solid var(--black);
        object-fit: cover;
    }}
    
    .profile-avatar-placeholder {{
        width: 140px;
        height: 140px;
        border-radius: 50%;
        border: 4px solid var(--black);
        background: var(--white);
        color: var(--black);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 48px;
        font-weight: 700;
    }}
    
    .profile-headline {{
        font-size: 18px;
        margin-bottom: 8px;
        color: rgba(255,255,255,0.9);
    }}
    
    .profile-actions {{
        display: flex;
        gap: 12px;
        margin-top: 20px;
    }}
    
    .contact-info {{
        display: flex;
        flex-direction: column;
        gap: 16px;
    }}
    
    .contact-item {{
        display: flex;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    
    .contact-item:last-child {{
        border-bottom: none;
    }}
    
    .contact-label {{
        color: rgba(255,255,255,0.6);
        font-size: 14px;
    }}
    
    .contact-value {{
        font-weight: 500;
    }}
    
    .social-link {{
        padding: 8px 16px;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        text-decoration: none;
        color: var(--white);
        font-size: 14px;
        transition: all 0.2s;
    }}
    
    .social-link:hover {{
        background: rgba(255,255,255,0.1);
        border-color: var(--white);
    }}
    
    .resume-preview {{
        background: rgba(255,255,255,0.05);
        padding: 20px;
        border-radius: 8px;
        text-align: center;
    }}
    
    .stat-item {{
        display: flex;
        justify-content: space-between;
        padding: 16px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }}
    
    .stat-item:last-child {{
        border-bottom: none;
    }}
    
    .stat-item-value {{
        font-size: 20px;
        font-weight: 600;
    }}
    
    .stat-item-label {{
        color: rgba(255,255,255,0.6);
        font-size: 14px;
    }}
    </style>
    """
    return get_base_html("Profile", content, user)


def edit_profile_page(user: User, error: str = "", success: str = "") -> str:
    """Edit profile page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    success_html = f'<div class="alert alert-success">{success}</div>' if success else ""
    
    content = f"""
    <div class="container-sm">
        <div style="margin-bottom: 32px;">
            <a href="/profile" class="btn btn-outline">← Back to Profile</a>
        </div>
        
        <h1>Edit Profile</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Update your professional information</p>
        
        {error_html}
        {success_html}
        
        <!-- Avatar Upload -->
        <div class="card">
            <h3 style="margin-bottom: 20px;">Profile Picture</h3>
            <form method="POST" action="/upload-avatar" enctype="multipart/form-data" style="display: flex; align-items: center; gap: 24px;">
                <div>
                    {f'<img src="/uploads/avatars/{user.avatar}" alt="Avatar" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid rgba(255,255,255,0.2);">' if user.avatar else f'<div style="width: 100px; height: 100px; border-radius: 50%; background: var(--white); color: var(--black); display: flex; align-items: center; justify-content: center; font-size: 36px; font-weight: 700;">{user.full_name[0].upper()}</div>'}
                </div>
                <div style="flex: 1;">
                    <input type="file" name="avatar" accept="image/*" class="form-control" style="margin-bottom: 12px;">
                    <button type="submit" class="btn btn-primary">Upload Photo</button>
                </div>
            </form>
        </div>
        
        <!-- Basic Information -->
        <form method="POST" action="/update-profile">
            <div class="card">
                <h3 style="margin-bottom: 20px;">Basic Information</h3>
                
                <div class="form-group">
                    <label class="form-label">Full Name</label>
                    <input type="text" name="full_name" class="form-control" value="{user.full_name}" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Headline</label>
                    <input type="text" name="headline" class="form-control" value="{user.headline or ''}" placeholder="e.g. Senior Software Engineer at Tech Company">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Location</label>
                    <input type="text" name="location" class="form-control" value="{user.location or ''}" placeholder="e.g. San Francisco, CA">
                </div>
                
                <div class="form-group">
                    <label class="form-label">About</label>
                    <textarea name="bio" class="form-control" placeholder="Tell us about yourself, your experience, and what makes you unique...">{user.bio or ''}</textarea>
                </div>
            </div>
            
            <!-- Contact Information -->
            <div class="card">
                <h3 style="margin-bottom: 20px;">Contact Information</h3>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" class="form-control" value="{user.email}" disabled style="opacity: 0.6;">
                    <p class="text-muted text-xs" style="margin-top: 4px;">Email cannot be changed</p>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Phone</label>
                    <input type="tel" name="phone" class="form-control" value="{user.phone or ''}" placeholder="+1 (555) 123-4567">
                </div>
            </div>
            
            <!-- Social Links -->
            <div class="card">
                <h3 style="margin-bottom: 20px;">Social Links</h3>
                
                <div class="form-group">
                    <label class="form-label">LinkedIn Profile</label>
                    <input type="url" name="linkedin_url" class="form-control" value="{user.linkedin_url or ''}" placeholder="https://linkedin.com/in/yourprofile">
                </div>
                
                <div class="form-group">
                    <label class="form-label">GitHub Profile</label>
                    <input type="url" name="github_url" class="form-control" value="{user.github_url or ''}" placeholder="https://github.com/yourusername">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Personal Website</label>
                    <input type="url" name="website" class="form-control" value="{user.website or ''}" placeholder="https://yourwebsite.com">
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary btn-block btn-large">Save Changes</button>
        </form>
    </div>
    """
    return get_base_html("Edit Profile", content, user)


def upload_resume_profile_page(user: User, error: str = "") -> str:
    """Upload resume to profile page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <div style="margin-bottom: 32px;">
            <a href="/profile" class="btn btn-outline">← Back to Profile</a>
        </div>
        
        <h1>Upload Resume</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Upload your resume to your profile for quick job matching</p>
        
        {error_html}
        
        <div class="card">
            <form method="POST" action="/upload-resume-profile" enctype="multipart/form-data">
                <div class="file-upload" onclick="document.getElementById('resume-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="resume-input" name="resume" accept=".pdf,.docx,.doc" required onchange="updateResumeFileName(this)">
                    <p id="resume-name" style="font-weight: 600; margin-bottom: 8px; font-size: 16px;">Click to upload your resume</p>
                    <p class="text-muted text-xs">PDF or DOCX, max 10MB</p>
                </div>
                
                <button type="submit" class="btn btn-primary btn-block btn-large" style="margin-top: 24px;">Upload Resume</button>
            </form>
        </div>
        
        {f'<div class="card"><h3>Current Resume</h3><p>📄 {user.resume_file.split("/")[-1] if "/" in user.resume_file else user.resume_file}</p><a href="/download-resume" class="btn btn-outline" style="margin-top: 12px;">Download Current Resume</a></div>' if user.resume_file else ''}
    </div>
    
    <script>
    function updateResumeFileName(input) {{
        const fileName = (input.files && input.files[0]) ? input.files[0].name : 'Click to upload your resume';
        document.getElementById('resume-name').textContent = fileName;
    }}
    </script>
    """
    return get_base_html("Upload Resume", content, user)


def analyze_page(user: User, error: str = "") -> str:
    """Analyze page"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <h1>Analyze Match</h1>
        <p class="text-muted" style="margin-bottom: 48px;">Upload your resume and paste the job description</p>
        
        {error_html}
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <h3>1. Upload Resume</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">PDF or DOCX format, max 10MB</p>
                
                <div class="file-upload" onclick="document.getElementById('file-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="file-input" name="file" accept=".pdf,.docx,.doc" required onchange="updateFileName(this)">
                    <p id="file-name" style="font-weight: 600; margin-bottom: 8px; font-size: 16px;">Click to upload resume</p>
                    <p class="text-muted text-xs">Supported: PDF, DOCX</p>
                </div>
            </div>
            
            <div class="card">
                <h3>2. Job Description</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">Paste the complete job posting including all requirements</p>
                
                <div class="form-group">
                    <textarea name="job_description" class="form-control" required placeholder="Paste the full job description here...

Example:
Job Title: Senior Software Engineer
Location: Remote
Salary: $120k-$150k

About the Role:
We're looking for an experienced Software Engineer...

Requirements:
• 5+ years of experience with Python
• Strong background in web development
• Experience with databases and APIs...

Responsibilities:
• Design and implement features..."></textarea>
                </div>
            </div>
            
            <button type="submit" class="btn btn-block btn-large">Analyze Match</button>
        </form>
    </div>
    
    <script>
    function updateFileName(input) {{
        const fileName = (input.files && input.files[0]) ? input.files[0].name : 'Click to upload resume';
        document.getElementById('file-name').textContent = fileName;
    }}
    </script>
    """
    return get_base_html("Analyze", content, user)


def result_page(user: User, analysis: Analysis) -> str:
    """Result page"""
    
    data = json.loads(analysis.analysis_data)
    score = analysis.match_score
    
    if score >= 70:
        score_class = "excellent"
        score_text = "Excellent Match"
    elif score >= 50:
        score_class = "good"
        score_text = "Good Match"
    else:
        score_class = "poor"
        score_text = "Needs Work"
    
    pros_html = "".join([f'<li class="feature-item"><span class="feature-icon pro">✓</span><span>{p}</span></li>' for p in data.get('pros', [])])
    cons_html = "".join([f'<li class="feature-item"><span class="feature-icon con">✗</span><span>{c}</span></li>' for c in data.get('cons', [])])
    
    matched_skills = data.get('skills_match', {}).get('matched_skills', [])
    missing_skills = data.get('skills_match', {}).get('missing_skills', [])
    additional_skills = data.get('skills_match', {}).get('additional_skills', [])
    
    matched_html = "".join([f'<span class="badge badge-success">{s}</span>' for s in matched_skills])
    missing_html = "".join([f'<span class="badge badge-warning">{s}</span>' for s in missing_skills])
    additional_html = "".join([f'<span class="badge badge-info">{s}</span>' for s in additional_skills])
    
    recommendations_html = "".join([f'<li class="feature-item"><span class="feature-icon tip">💡</span><span>{r}</span></li>' for r in data.get('recommendations', [])])
    
    exp_score = data.get('experience_match', {}).get('score', 0)
    edu_score = data.get('education_match', {}).get('score', 0)
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 32px;">
            <a href="/dashboard" class="btn btn-outline">← Dashboard</a>
        </div>
        
        <div class="card">
            <div class="score-display">
                <div class="score-circle {score_class}">
                    <div class="score-value">{score:.0f}%</div>
                    <div class="score-label">Match</div>
                </div>
                <h2>{score_text}</h2>
                <p class="text-muted">{data.get('summary', '')}</p>
                <div class="text-muted text-sm" style="margin-top: 20px;">
                    📄 {analysis.filename} • {analysis.created_at.strftime('%B %d, %Y')}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3>Strengths</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">What makes you a great fit</p>
                <ul class="feature-list">
                    {pros_html}
                </ul>
            </div>
            
            <div class="card">
                <h3>Areas to Address</h3>
                <p class="text-muted text-sm" style="margin-bottom: 24px;">Requirements to strengthen</p>
                <ul class="feature-list">
                    {cons_html}
                </ul>
            </div>
        </div>
        
        <div class="card">
            <h3>Skills Analysis</h3>
            
            <div class="section">
                <h4 class="text-sm text-muted">MATCHED SKILLS</h4>
                <div style="margin-top: 12px;">
                    {matched_html if matched_html else '<span class="text-muted">No matched skills</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">MISSING SKILLS</h4>
                <div style="margin-top: 12px;">
                    {missing_html if missing_html else '<span class="text-muted">No missing skills</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">ADDITIONAL SKILLS</h4>
                <div style="margin-top: 12px;">
                    {additional_html if additional_html else '<span class="text-muted">No additional skills</span>'}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3>Experience Match</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {exp_score}%"></div>
                </div>
                <p style="margin-top: 16px; font-weight: 600; font-size: 18px;">{exp_score}%</p>
                <p class="text-muted text-sm" style="margin-top: 8px;">{data.get('experience_match', {}).get('analysis', '')}</p>
            </div>
            
            <div class="card">
                <h3>Education Match</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {edu_score}%"></div>
                </div>
                <p style="margin-top: 16px; font-weight: 600; font-size: 18px;">{edu_score}%</p>
                <p class="text-muted text-sm" style="margin-top: 8px;">{data.get('education_match', {}).get('analysis', '')}</p>
            </div>
        </div>
        
        <div class="card">
            <h3>Recommendations</h3>
            <p class="text-muted text-sm" style="margin-bottom: 24px;">Actions to improve your match</p>
            <ul class="feature-list">
                {recommendations_html}
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 48px;">
            <a href="/analyze" class="btn btn-large">Analyze Another Position</a>
        </div>
    </div>
    """
    return get_base_html("Results", content, user)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

app = FastAPI(title="HR Agent", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    Config.init()
    init_db()
    print("=" * 50)
    print("HR Agent initialized successfully")
    print(f"Using Ollama model: {Config.OLLAMA_MODEL}")
    print(f"Ollama URL: {Config.OLLAMA_API_URL}")
    print("=" * 50)


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
    
    session_token = create_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    
    session = Session(
        session_token=session_token,
        user_id=user.id,
        expires_at=expires_at
    )
    db.add(session)
    
    user.last_login = datetime.utcnow()
    db.commit()
    
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
    
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return HTMLResponse(register_page(error="Email already registered"))
    
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


@app.get("/edit-profile", response_class=HTMLResponse)
async def edit_profile_get(user: User = Depends(require_auth)):
    """Edit profile page"""
    return edit_profile_page(user)


@app.post("/update-profile")
async def update_profile(
    full_name: str = Form(...),
    headline: str = Form(""),
    location: str = Form(""),
    bio: str = Form(""),
    phone: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    website: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update profile information"""
    user.full_name = full_name
    user.headline = headline
    user.location = location
    user.bio = bio
    user.phone = phone
    user.linkedin_url = linkedin_url
    user.github_url = github_url
    user.website = website
    
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=302)


@app.post("/upload-avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Upload profile avatar"""
    
    # Validate file type
    if not avatar.content_type.startswith("image/"):
        return HTMLResponse(edit_profile_page(user, error="Please upload an image file"))
    
    # Validate file size
    file_content = await avatar.read()
    if len(file_content) > 5 * 1024 * 1024:  # 5MB
        return HTMLResponse(edit_profile_page(user, error="Image too large (max 5MB)"))
    
    # Save file
    file_ext = avatar.filename.split(".")[-1] if "." in avatar.filename else "jpg"
    filename = f"{user.id}_{datetime.utcnow().timestamp()}.{file_ext}"
    file_path = Config.UPLOAD_DIR / "avatars" / filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Update user
    user.avatar = filename
    db.commit()
    
    return RedirectResponse(url="/edit-profile", status_code=302)


@app.get("/upload-resume-profile", response_class=HTMLResponse)
async def upload_resume_profile_get(user: User = Depends(require_auth)):
    """Upload resume to profile page"""
    return upload_resume_profile_page(user)


@app.post("/upload-resume-profile")
async def upload_resume_profile_post(
    resume: UploadFile = File(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle resume upload to profile"""
    
    # Validate file type
    if not (resume.filename.endswith(".pdf") or resume.filename.endswith(".docx") or resume.filename.endswith(".doc")):
        return HTMLResponse(upload_resume_profile_page(user, error="Only PDF and DOCX files are supported"))
    
    # Validate file size
    file_content = await resume.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(upload_resume_profile_page(user, error="File too large (max 10MB)"))
    
    # Save file
    filename = f"{user.id}_resume_{datetime.utcnow().timestamp()}_{resume.filename}"
    file_path = Config.UPLOAD_DIR / "resumes" / filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Update user
    user.resume_file = filename
    db.commit()
    
    return RedirectResponse(url="/profile", status_code=302)


@app.get("/download-resume")
async def download_resume(user: User = Depends(require_auth)):
    """Download user's resume"""
    if not user.resume_file:
        raise HTTPException(status_code=404, detail="No resume uploaded")
    
    file_path = Config.UPLOAD_DIR / "resumes" / user.resume_file
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path, filename=user.resume_file.split("_", 3)[-1] if "_" in user.resume_file else user.resume_file)


@app.get("/uploads/{folder}/{filename}")
async def serve_upload(folder: str, filename: str):
    """Serve uploaded files"""
    file_path = Config.UPLOAD_DIR / folder / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(file_path)


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_get(user: User = Depends(require_auth)):
    """Analyze page"""
    return analyze_page(user)


@app.post("/analyze")
async def analyze_post(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle analysis request"""
    
    file_content = await file.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(analyze_page(user, error="File too large (max 10MB)"))
    
    file_path = Config.UPLOAD_DIR / f"{user.id}_{datetime.utcnow().timestamp()}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    resume_text = parse_resume(file.filename, file_content)
    analysis_data = await compare_resume_with_job(resume_text, job_description)
    
    analysis = Analysis(
        user_id=user.id,
        filename=file.filename,
        file_path=str(file_path),
        job_description=job_description,
        match_score=analysis_data.get("match_score", 0),
        analysis_data=json.dumps(analysis_data)
    )
    db.add(analysis)
    db.commit()
    
    return RedirectResponse(url=f"/result/{analysis.id}", status_code=302)


@app.get("/result/{analysis_id}", response_class=HTMLResponse)
async def result_detail(
    analysis_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Result detail page"""
    
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return result_page(user, analysis)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model": Config.OLLAMA_MODEL,
        "timestamp": datetime.utcnow().isoformat()
    }


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
