"""
Resume Analyzer - AI-Powered Job Match Analysis
Compare your resume with job description and get instant feedback
Beautiful v0.dev-inspired UI
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
    """Compare resume with job description using Ollama Cloud"""
    
    prompt = f"""Compare this resume with the job description and provide detailed analysis in JSON format.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON with this exact structure:
{{
    "match_score": 0.0-100.0,
    "pros": ["list of 5-7 strong matches between resume and job"],
    "cons": ["list of 5-7 gaps or missing requirements"],
    "skills_match": {{
        "matched_skills": ["skills from resume that match job requirements"],
        "missing_skills": ["required skills not found in resume"],
        "additional_skills": ["extra skills in resume not in job description"]
    }},
    "experience_match": {{
        "score": 0-100,
        "analysis": "detailed comparison of experience vs requirements"
    }},
    "education_match": {{
        "score": 0-100,
        "analysis": "detailed comparison of education vs requirements"
    }},
    "recommendations": ["list of 5-7 specific actions to improve match"],
    "summary": "2-3 sentence overall assessment of fit for this role"
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
                        {"role": "system", "content": "You are an expert HR analyst specializing in job matching. Always respond with valid JSON only."},
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
                    return create_fallback_comparison(resume_text, job_description)
            else:
                return create_fallback_comparison(resume_text, job_description)
                
    except Exception as e:
        print(f"Ollama API error: {str(e)}")
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
            "Contains relevant experience in the field",
            "Shows career progression and growth",
            "Demonstrates technical capabilities",
            "Good educational background"
        ],
        "cons": [
            "Some specific job requirements need verification",
            "Could add more quantifiable achievements",
            "May need additional certifications for this role",
            "Experience level requires manual review",
            "Some technical skills need confirmation"
        ],
        "skills_match": {
            "matched_skills": ["Communication", "Teamwork", "Problem Solving"],
            "missing_skills": ["Specific technical skills pending AI analysis"],
            "additional_skills": ["General professional skills"]
        },
        "experience_match": {
            "score": 70,
            "analysis": f"Resume shows {len(resume_text.split())} words of experience. Detailed comparison pending full AI analysis."
        },
        "education_match": {
            "score": 75,
            "analysis": "Education section present. Detailed analysis pending full AI configuration."
        },
        "recommendations": [
            "Highlight specific achievements from job requirements",
            "Add metrics and quantifiable results",
            "Include relevant certifications if available",
            "Tailor resume to match job keywords",
            "Emphasize experience in required technologies"
        ],
        "summary": f"Resume shows {match_score:.0f}% match with job description based on keyword analysis. Full AI-powered analysis will be available once the service is configured with Ollama API key."
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
# V0.DEV STYLE UI
# ============================================================================

V0_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

:root {
    --color-bg: #ffffff;
    --color-fg: #0a0a0a;
    --color-border: #e5e7eb;
    --color-muted: #6b7280;
    --color-accent: #3b82f6;
    --color-accent-light: #dbeafe;
    --color-success: #10b981;
    --color-warning: #f59e0b;
    --color-danger: #ef4444;
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--color-bg);
    color: var(--color-fg);
    line-height: 1.6;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
}

.nav {
    border-bottom: 1px solid var(--color-border);
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(12px);
    position: sticky;
    top: 0;
    z-index: 50;
}

.nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 64px;
}

.nav-logo {
    font-size: 20px;
    font-weight: 600;
    color: var(--color-fg);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 24px;
}

.nav-link {
    color: var(--color-muted);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    transition: color 0.2s;
}

.nav-link:hover {
    color: var(--color-fg);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 48px 24px;
}

.container-sm {
    max-width: 600px;
    margin: 0 auto;
    padding: 48px 24px;
}

.card {
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 32px;
    box-shadow: var(--shadow);
    margin-bottom: 24px;
}

.hero {
    text-align: center;
    padding: 80px 24px 60px;
    background: linear-gradient(to bottom, #f9fafb 0%, #ffffff 100%);
}

.hero h1 {
    font-size: 56px;
    font-weight: 700;
    margin-bottom: 16px;
    background: linear-gradient(to right, #0a0a0a, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.hero p {
    font-size: 20px;
    color: var(--color-muted);
    max-width: 600px;
    margin: 0 auto 40px;
}

h1 {
    font-size: 36px;
    font-weight: 700;
    margin-bottom: 8px;
    letter-spacing: -0.02em;
}

h2 {
    font-size: 28px;
    font-weight: 600;
    margin-bottom: 16px;
    letter-spacing: -0.01em;
}

h3 {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 12px;
}

.text-muted {
    color: var(--color-muted);
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
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    border-radius: 8px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    gap: 8px;
}

.btn-primary {
    background: var(--color-fg);
    color: var(--color-bg);
    border-color: var(--color-fg);
}

.btn-primary:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-lg);
}

.btn-outline {
    background: transparent;
    color: var(--color-fg);
    border-color: var(--color-border);
}

.btn-outline:hover {
    background: var(--color-bg);
    border-color: var(--color-fg);
}

.btn-large {
    padding: 12px 28px;
    font-size: 16px;
}

.btn-block {
    display: flex;
    width: 100%;
}

.form-group {
    margin-bottom: 20px;
}

.form-label {
    display: block;
    font-weight: 500;
    margin-bottom: 8px;
    font-size: 14px;
}

.form-control {
    width: 100%;
    padding: 12px 16px;
    font-size: 15px;
    color: var(--color-fg);
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    outline: none;
    transition: all 0.2s;
    font-family: inherit;
}

.form-control:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px var(--color-accent-light);
}

textarea.form-control {
    min-height: 200px;
    resize: vertical;
    line-height: 1.6;
}

.alert {
    padding: 16px 20px;
    border-radius: 8px;
    margin-bottom: 24px;
    border: 1px solid;
}

.alert-success {
    background: #d1fae5;
    border-color: var(--color-success);
    color: #065f46;
}

.alert-error {
    background: #fee2e2;
    border-color: var(--color-danger);
    color: #991b1b;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
}

.stat-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 24px;
    color: white;
    box-shadow: var(--shadow);
}

.stat-card.blue {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
}

.stat-card.green {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.stat-card.orange {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.stat-value {
    font-size: 36px;
    font-weight: 700;
    margin-bottom: 4px;
}

.stat-label {
    font-size: 13px;
    opacity: 0.9;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.score-display {
    text-align: center;
    padding: 40px;
}

.score-circle {
    width: 160px;
    height: 160px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 0 auto 24px;
    border: 8px solid;
    position: relative;
}

.score-circle.excellent {
    background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
    border-color: var(--color-success);
    color: #065f46;
}

.score-circle.good {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-color: var(--color-warning);
    color: #92400e;
}

.score-circle.poor {
    background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
    border-color: var(--color-danger);
    color: #991b1b;
}

.score-value {
    font-size: 48px;
    font-weight: 700;
}

.score-label {
    font-size: 14px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 24px;
}

.feature-list {
    list-style: none;
}

.feature-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 0;
    border-bottom: 1px solid var(--color-border);
}

.feature-item:last-child {
    border-bottom: none;
}

.feature-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
}

.feature-icon.pro {
    background: #d1fae5;
    color: var(--color-success);
}

.feature-icon.con {
    background: #fee2e2;
    color: var(--color-danger);
}

.badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
    border-radius: 6px;
    margin: 4px;
}

.badge-success {
    background: #d1fae5;
    color: #065f46;
}

.badge-warning {
    background: #fef3c7;
    color: #92400e;
}

.badge-info {
    background: #dbeafe;
    color: #1e40af;
}

.table {
    width: 100%;
    border-collapse: collapse;
}

.table th {
    text-align: left;
    padding: 12px;
    font-weight: 600;
    font-size: 13px;
    color: var(--color-muted);
    border-bottom: 1px solid var(--color-border);
}

.table td {
    padding: 16px 12px;
    border-bottom: 1px solid var(--color-border);
}

.table tr:last-child td {
    border-bottom: none;
}

.file-upload {
    border: 2px dashed var(--color-border);
    border-radius: 12px;
    padding: 48px 24px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: #f9fafb;
}

.file-upload:hover {
    border-color: var(--color-accent);
    background: var(--color-accent-light);
}

.file-upload input {
    display: none;
}

.file-icon {
    font-size: 48px;
    margin-bottom: 16px;
}

.progress-bar {
    width: 100%;
    height: 8px;
    background: var(--color-border);
    border-radius: 4px;
    overflow: hidden;
    margin: 8px 0;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--color-success), var(--color-accent));
    border-radius: 4px;
    transition: width 0.3s;
}

.section {
    margin-bottom: 32px;
}

.divider {
    height: 1px;
    background: var(--color-border);
    margin: 32px 0;
}

.flex-between {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.gap-2 {
    gap: 8px;
}

.gap-4 {
    gap: 16px;
}

@media (max-width: 768px) {
    .hero h1 {
        font-size: 36px;
    }
    
    .hero p {
        font-size: 16px;
    }
    
    .nav-container {
        padding: 0 16px;
    }
    
    .container {
        padding: 32px 16px;
    }
    
    .card {
        padding: 24px;
    }
    
    .grid-2 {
        grid-template-columns: 1fr;
    }
}
"""


def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Generate base HTML with v0.dev-style navigation"""
    
    if user:
        nav_links = f"""
            <a href="/dashboard" class="nav-link">Dashboard</a>
            <a href="/analyze" class="nav-link">New Analysis</a>
            <a href="/profile" class="nav-link">{user.full_name}</a>
            <a href="/logout" class="nav-link">Sign out</a>
        """
    else:
        nav_links = """
            <a href="/login" class="nav-link">Sign in</a>
            <a href="/register" class="btn btn-primary">Get Started</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Resume Analyzer</title>
    <style>{V0_CSS}</style>
</head>
<body>
    <nav class="nav">
        <div class="nav-container">
            <a href="/" class="nav-logo">
                ✨ Resume Analyzer
            </a>
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
        <h1>Match Your Resume with Your Dream Job</h1>
        <p>Upload your resume and paste the job description. Get instant AI-powered analysis showing how well you match the position.</p>
        <div style="display: flex; gap: 16px; justify-content: center;">
            <a href="/register" class="btn btn-primary btn-large">Start Analyzing →</a>
            <a href="/login" class="btn btn-outline btn-large">Sign In</a>
        </div>
    </div>
    
    <div class="container">
        <div class="grid-2">
            <div class="card">
                <h3>📊 Match Percentage</h3>
                <p class="text-muted">See exactly how well your resume aligns with the job requirements. Get a clear percentage score.</p>
            </div>
            
            <div class="card">
                <h3>✅ Pros & Cons</h3>
                <p class="text-muted">Discover your strengths for the position and areas where you might need improvement.</p>
            </div>
            
            <div class="card">
                <h3>🎯 Skills Analysis</h3>
                <p class="text-muted">Identify matched skills, missing requirements, and additional qualifications you bring.</p>
            </div>
            
            <div class="card">
                <h3>💡 Recommendations</h3>
                <p class="text-muted">Get actionable advice on how to improve your match score and stand out.</p>
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
            <p class="text-muted" style="margin-bottom: 32px;">Sign in to your account to continue</p>
            
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
                
                <button type="submit" class="btn btn-primary btn-block btn-large">Sign In</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Don't have an account? <a href="/register" style="color: var(--color-accent); text-decoration: none;">Create one</a>
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
            <h2>Create your account</h2>
            <p class="text-muted" style="margin-bottom: 32px;">Get started with your resume analysis</p>
            
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
                    <input type="password" name="password" class="form-control" required minlength="6" placeholder="At least 6 characters">
                </div>
                
                <button type="submit" class="btn btn-primary btn-block btn-large">Create Account</button>
            </form>
            
            <div class="divider"></div>
            
            <p class="text-muted text-sm" style="text-align: center;">
                Already have an account? <a href="/login" style="color: var(--color-accent); text-decoration: none;">Sign in</a>
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
            badge_class = "badge badge-warning"
        
        recent_list += f"""
        <tr>
            <td>
                <strong>{analysis.filename}</strong>
                <div class="text-muted text-xs">{analysis.created_at.strftime('%b %d, %Y at %H:%M')}</div>
            </td>
            <td><span class="{badge_class}">{analysis.match_score:.0f}%</span></td>
            <td><a href="/result/{analysis.id}" class="btn btn-outline" style="padding: 6px 16px;">View Details →</a></td>
        </tr>
        """
    
    if not recent_list:
        recent_list = '<tr><td colspan="3" style="text-align: center;" class="text-muted">No analyses yet. <a href="/analyze" style="color: var(--color-accent);">Create your first one</a></td></tr>'
    
    content = f"""
    <div class="container">
        <div class="flex-between" style="margin-bottom: 32px;">
            <div>
                <h1>Dashboard</h1>
                <p class="text-muted">Welcome back, {user.full_name}</p>
            </div>
            <a href="/analyze" class="btn btn-primary btn-large">New Analysis</a>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card blue">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">Total Analyses</div>
            </div>
            <div class="stat-card green">
                <div class="stat-value">{avg_score_value:.0f}%</div>
                <div class="stat-label">Average Match</div>
            </div>
            <div class="stat-card orange">
                <div class="stat-value">{latest_score:.0f}%</div>
                <div class="stat-label">Latest Score</div>
            </div>
        </div>
        
        <div class="card">
            <h3 style="margin-bottom: 20px;">Recent Analyses</h3>
            <table class="table">
                <thead>
                    <tr>
                        <th>Resume & Date</th>
                        <th>Match Score</th>
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
        <p class="text-muted" style="margin-bottom: 32px;">Manage your account information</p>
        
        <div class="card">
            <div class="section">
                <h3>Account Details</h3>
                <div style="margin-top: 20px;">
                    <div style="margin-bottom: 16px;">
                        <div class="text-muted text-sm">FULL NAME</div>
                        <div style="font-weight: 500; margin-top: 4px;">{user.full_name}</div>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <div class="text-muted text-sm">EMAIL</div>
                        <div style="font-weight: 500; margin-top: 4px;">{user.email}</div>
                    </div>
                    <div style="margin-bottom: 16px;">
                        <div class="text-muted text-sm">MEMBER SINCE</div>
                        <div style="font-weight: 500; margin-top: 4px;">{user.created_at.strftime('%B %d, %Y')}</div>
                    </div>
                    <div>
                        <div class="text-muted text-sm">TOTAL ANALYSES</div>
                        <div style="font-weight: 500; margin-top: 4px;">{total_analyses}</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    return get_base_html("Profile", content, user)


def analyze_page(user: User, error: str = "") -> str:
    """Analyze page with job description"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container-sm">
        <h1>Analyze Resume Match</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Upload your resume and paste the job description to see how well you match</p>
        
        {error_html}
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <h3>1. Upload Your Resume</h3>
                <p class="text-muted text-sm" style="margin-bottom: 20px;">PDF or DOCX format</p>
                
                <div class="file-upload" onclick="document.getElementById('file-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="file-input" name="file" accept=".pdf,.docx,.doc" required onchange="updateFileName(this)">
                    <p id="file-name" style="font-weight: 500; margin-bottom: 8px;">Click to upload resume</p>
                    <p class="text-muted text-xs">Max file size: 10MB</p>
                </div>
            </div>
            
            <div class="card">
                <h3>2. Paste Job Description</h3>
                <p class="text-muted text-sm" style="margin-bottom: 20px;">Copy the full job posting including requirements, responsibilities, and qualifications</p>
                
                <div class="form-group">
                    <textarea name="job_description" class="form-control" required placeholder="Paste the complete job description here...

Example:
Job Title: Senior Software Engineer
Location: Remote
Salary: $120k-$150k

About the role:
We're looking for an experienced Software Engineer...

Requirements:
- 5+ years of experience with Python
- Strong background in web development
- Experience with databases..."></textarea>
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary btn-block btn-large">Analyze Match →</button>
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
    """Result page showing match analysis"""
    
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
        score_text = "Needs Improvement"
    
    pros_html = "".join([f'<li class="feature-item"><span class="feature-icon pro">✓</span><span>{p}</span></li>' for p in data.get('pros', [])])
    cons_html = "".join([f'<li class="feature-item"><span class="feature-icon con">✗</span><span>{c}</span></li>' for c in data.get('cons', [])])
    
    matched_skills = data.get('skills_match', {}).get('matched_skills', [])
    missing_skills = data.get('skills_match', {}).get('missing_skills', [])
    additional_skills = data.get('skills_match', {}).get('additional_skills', [])
    
    matched_html = "".join([f'<span class="badge badge-success">{s}</span>' for s in matched_skills])
    missing_html = "".join([f'<span class="badge badge-warning">{s}</span>' for s in missing_skills])
    additional_html = "".join([f'<span class="badge badge-info">{s}</span>' for s in additional_skills])
    
    recommendations_html = "".join([f'<li class="feature-item"><span class="feature-icon pro">💡</span><span>{r}</span></li>' for r in data.get('recommendations', [])])
    
    exp_score = data.get('experience_match', {}).get('score', 0)
    edu_score = data.get('education_match', {}).get('score', 0)
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 24px;">
            <a href="/dashboard" class="btn btn-outline">← Back to Dashboard</a>
        </div>
        
        <div class="card">
            <div class="score-display">
                <div class="score-circle {score_class}">
                    <div class="score-value">{score:.0f}%</div>
                    <div class="score-label">Match</div>
                </div>
                <h2>{score_text}</h2>
                <p class="text-muted">{data.get('summary', '')}</p>
                <div class="text-muted text-sm" style="margin-top: 16px;">
                    📄 {analysis.filename} • {analysis.created_at.strftime('%B %d, %Y')}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3 style="color: var(--color-success);">✅ Your Strengths</h3>
                <p class="text-muted text-sm" style="margin-bottom: 20px;">What makes you a great fit for this role</p>
                <ul class="feature-list">
                    {pros_html}
                </ul>
            </div>
            
            <div class="card">
                <h3 style="color: var(--color-danger);">⚠️ Areas to Address</h3>
                <p class="text-muted text-sm" style="margin-bottom: 20px;">Requirements you may need to strengthen</p>
                <ul class="feature-list">
                    {cons_html}
                </ul>
            </div>
        </div>
        
        <div class="card">
            <h3>🎯 Skills Analysis</h3>
            
            <div class="section">
                <h4 class="text-sm text-muted">MATCHED SKILLS</h4>
                <div style="margin-top: 8px;">
                    {matched_html if matched_html else '<span class="text-muted">No matched skills detected</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">MISSING SKILLS</h4>
                <div style="margin-top: 8px;">
                    {missing_html if missing_html else '<span class="text-muted">No missing skills detected</span>'}
                </div>
            </div>
            
            <div class="section">
                <h4 class="text-sm text-muted">ADDITIONAL SKILLS YOU BRING</h4>
                <div style="margin-top: 8px;">
                    {additional_html if additional_html else '<span class="text-muted">No additional skills detected</span>'}
                </div>
            </div>
        </div>
        
        <div class="grid-2">
            <div class="card">
                <h3>💼 Experience Match</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {exp_score}%"></div>
                </div>
                <p style="margin-top: 12px; font-weight: 600;">{exp_score}% Match</p>
                <p class="text-muted text-sm">{data.get('experience_match', {}).get('analysis', '')}</p>
            </div>
            
            <div class="card">
                <h3>🎓 Education Match</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {edu_score}%"></div>
                </div>
                <p style="margin-top: 12px; font-weight: 600;">{edu_score}% Match</p>
                <p class="text-muted text-sm">{data.get('education_match', {}).get('analysis', '')}</p>
            </div>
        </div>
        
        <div class="card">
            <h3>💡 Recommendations</h3>
            <p class="text-muted text-sm" style="margin-bottom: 20px;">Actions to improve your match for this position</p>
            <ul class="feature-list">
                {recommendations_html}
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 32px;">
            <a href="/analyze" class="btn btn-primary btn-large">Analyze Another Position</a>
        </div>
    </div>
    """
    return get_base_html("Analysis Results", content, user)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

app = FastAPI(title="Resume Analyzer", version="3.0.0")


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
    
    # Validate file size
    file_content = await file.read()
    if len(file_content) > Config.MAX_FILE_SIZE:
        return HTMLResponse(analyze_page(user, error="File too large (max 10MB)"))
    
    # Save file
    file_path = Config.UPLOAD_DIR / f"{user.id}_{datetime.utcnow().timestamp()}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Parse resume
    resume_text = parse_resume(file.filename, file_content)
    
    # Compare with job description
    analysis_data = await compare_resume_with_job(resume_text, job_description)
    
    # Save analysis
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
