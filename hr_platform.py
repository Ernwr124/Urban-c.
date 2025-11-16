"""
HR Agent Platform - Professional HR Service
FastAPI + SQLite + Ollama Cloud Integration
Single-file architecture with modular structure
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
    role = Column(String, nullable=False)  # 'candidate' or 'hr'
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)


class Analysis(Base):
    """Resume analysis model"""
    __tablename__ = "analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    candidate_name = Column(String)
    filename = Column(String)
    file_path = Column(String)
    analysis_type = Column(String)  # 'resume_analysis', 'comparison', 'tk_check'
    match_score = Column(Float)
    analysis_data = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class Analytics(Base):
    """Analytics and metrics model"""
    __tablename__ = "analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    action = Column(String)  # 'login', 'upload', 'analysis', etc.
    metadata = Column(Text)  # JSON
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
    role: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class AnalysisResult(BaseModel):
    match_score: float
    strengths: List[str]
    weaknesses: List[str]
    skills_match: Dict[str, Any]
    experience_assessment: str
    education_assessment: str
    development_plan: List[str]
    recommendations: List[str]
    summary: str


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


async def analyze_resume_with_ollama(resume_text: str, analysis_type: str = "candidate") -> Dict[str, Any]:
    """Analyze resume using Ollama Cloud"""
    
    if analysis_type == "candidate":
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
    else:
        prompt = f"""Analyze this resume for HR purposes and provide scoring in JSON format.

Resume:
{resume_text}

Return ONLY valid JSON with the same structure as above."""

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
                
                # Try to parse JSON from response
                try:
                    analysis_data = json.loads(content)
                    return analysis_data
                except json.JSONDecodeError:
                    # Fallback if not valid JSON
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


def require_role(required_role: str):
    """Require specific role"""
    def role_checker(user: User = Depends(require_auth)) -> User:
        if user.role != required_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker


# ============================================================================
# HTML TEMPLATES & STYLES
# ============================================================================

BASE_CSS = """
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #ffffff;
    color: #0f0f0f;
    line-height: 1.6;
}

.navbar {
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
    height: 64px;
    display: flex;
    align-items: center;
    padding: 0 2rem;
    position: sticky;
    top: 0;
    z-index: 100;
}

.navbar-brand {
    font-size: 20px;
    font-weight: 700;
    color: #0f0f0f;
    text-decoration: none;
    margin-right: auto;
}

.navbar-links {
    display: flex;
    gap: 2rem;
    align-items: center;
}

.navbar-links a {
    color: #0f0f0f;
    text-decoration: none;
    font-size: 15px;
    transition: color 0.2s;
}

.navbar-links a:hover {
    color: #2563eb;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 3rem 2rem;
}

.card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 2rem;
    box-shadow: 0px 4px 12px rgba(0,0,0,0.05);
    margin-bottom: 2rem;
}

h1 {
    font-size: 48px;
    font-weight: 700;
    margin-bottom: 1.5rem;
    color: #0f0f0f;
}

h2 {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 1rem;
    color: #0f0f0f;
}

h3 {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 0.75rem;
    color: #0f0f0f;
}

p {
    font-size: 16px;
    color: #4b4b4b;
    margin-bottom: 1rem;
}

.btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 500;
    text-decoration: none;
    border: none;
    cursor: pointer;
    transition: all 0.2s;
}

.btn-primary {
    background: #2563eb;
    color: #ffffff;
}

.btn-primary:hover {
    background: #1d4ed8;
}

.btn-secondary {
    background: #0f0f0f;
    color: #ffffff;
}

.btn-secondary:hover {
    background: #1e1e1e;
}

.btn-outline {
    background: transparent;
    color: #2563eb;
    border: 1px solid #2563eb;
}

.btn-outline:hover {
    background: #2563eb;
    color: #ffffff;
}

.form-group {
    margin-bottom: 1.5rem;
}

.form-label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 0.5rem;
    color: #0f0f0f;
}

.form-control {
    width: 100%;
    height: 44px;
    padding: 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 16px;
    color: #0f0f0f;
    background: #ffffff;
}

.form-control:focus {
    outline: none;
    border-color: #2563eb;
}

textarea.form-control {
    height: auto;
    min-height: 120px;
    resize: vertical;
}

select.form-control {
    cursor: pointer;
}

.alert {
    padding: 1rem 1.5rem;
    border-radius: 6px;
    margin-bottom: 1.5rem;
    font-size: 14px;
}

.alert-success {
    background: #d1fae5;
    border: 1px solid #0ea5e9;
    color: #065f46;
}

.alert-error {
    background: #fee2e2;
    border: 1px solid #ef4444;
    color: #991b1b;
}

.grid {
    display: grid;
    gap: 2rem;
}

.grid-2 {
    grid-template-columns: repeat(2, 1fr);
}

.grid-3 {
    grid-template-columns: repeat(3, 1fr);
}

.stat-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1.5rem;
    text-align: center;
}

.stat-value {
    font-size: 36px;
    font-weight: 700;
    color: #2563eb;
    margin-bottom: 0.5rem;
}

.stat-label {
    font-size: 14px;
    color: #4b4b4b;
}

.hero {
    text-align: center;
    padding: 6rem 2rem;
    background: linear-gradient(180deg, #ffffff 0%, #f9fafb 100%);
}

.hero h1 {
    font-size: 56px;
    margin-bottom: 1.5rem;
}

.hero p {
    font-size: 20px;
    color: #4b4b4b;
    max-width: 600px;
    margin: 0 auto 2rem;
}

.features {
    padding: 4rem 2rem;
}

.feature-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
    margin-top: 3rem;
}

.feature-card {
    text-align: center;
    padding: 2rem;
}

.feature-icon {
    font-size: 48px;
    margin-bottom: 1rem;
}

.analysis-result {
    background: #f9fafb;
    border-left: 4px solid #2563eb;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

.score-circle {
    width: 150px;
    height: 150px;
    border-radius: 50%;
    background: #2563eb;
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
    font-weight: 700;
    margin: 0 auto 2rem;
}

.list-disc {
    list-style: disc;
    padding-left: 1.5rem;
    margin-bottom: 1rem;
}

.list-disc li {
    margin-bottom: 0.5rem;
    color: #4b4b4b;
}

.file-upload {
    border: 2px dashed #d1d5db;
    border-radius: 8px;
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s;
}

.file-upload:hover {
    border-color: #2563eb;
}

.file-upload input[type="file"] {
    display: none;
}

table {
    width: 100%;
    border-collapse: collapse;
}

table th {
    background: #f9fafb;
    padding: 1rem;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid #e5e7eb;
}

table td {
    padding: 1rem;
    border-bottom: 1px solid #e5e7eb;
}

@media (max-width: 768px) {
    .navbar {
        padding: 0 1rem;
    }
    
    .navbar-links {
        gap: 1rem;
        font-size: 14px;
    }
    
    .container {
        padding: 2rem 1rem;
    }
    
    .hero h1 {
        font-size: 36px;
    }
    
    .grid-2, .grid-3, .feature-grid {
        grid-template-columns: 1fr;
    }
    
    h1 {
        font-size: 32px;
    }
    
    h2 {
        font-size: 24px;
    }
}
"""


def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Generate base HTML with navigation"""
    
    if user:
        nav_links = f"""
            <span style="color: #4b4b4b; margin-right: 1rem;">{user.email}</span>
            <a href="/dashboard">Dashboard</a>
            <a href="/profile">Profile</a>
            <a href="/upload">Upload</a>
            <a href="/logout">Logout</a>
        """
    else:
        nav_links = """
            <a href="/login">Login</a>
            <a href="/register">Register</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HR Platform</title>
    <style>{BASE_CSS}</style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="navbar-brand">HR Platform</a>
        <div class="navbar-links">
            {nav_links}
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
    """Landing page HTML"""
    content = """
    <div class="hero">
        <h1>HR Agent Platform</h1>
        <p>Professional HR service for intelligent resume analysis, candidate comparison, and compliance checking with Kazakhstan Labor Code</p>
        <div style="display: flex; gap: 1rem; justify-content: center; margin-top: 2rem;">
            <a href="/register" class="btn btn-primary">Get Started</a>
            <a href="/login" class="btn btn-outline">Sign In</a>
        </div>
    </div>
    
    <div class="features">
        <div class="container">
            <h2 style="text-align: center;">Platform Features</h2>
            <div class="feature-grid">
                <div class="feature-card">
                    <div class="feature-icon">📄</div>
                    <h3>Resume Analysis</h3>
                    <p>AI-powered analysis of resumes with detailed feedback and recommendations</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">👥</div>
                    <h3>Candidate Comparison</h3>
                    <p>Compare multiple candidates side-by-side with intelligent matching scores</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">⚖️</div>
                    <h3>Labor Code Check</h3>
                    <p>Verify vacancy requirements against Kazakhstan Labor Code regulations</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">📊</div>
                    <h3>Development Plans</h3>
                    <p>Personalized career development recommendations for candidates</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🎯</div>
                    <h3>Skills Matching</h3>
                    <p>Detailed analysis of technical and soft skills alignment</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">📈</div>
                    <h3>Analytics Dashboard</h3>
                    <p>Track hiring metrics and candidate performance over time</p>
                </div>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="card" style="text-align: center; background: #f9fafb;">
            <h2>Ready to Transform Your HR Process?</h2>
            <p style="font-size: 18px; margin-bottom: 2rem;">Join hundreds of companies using HR Platform for smarter hiring</p>
            <a href="/register" class="btn btn-primary" style="font-size: 18px; padding: 1rem 2rem;">Start Free Trial</a>
        </div>
    </div>
    """
    return get_base_html("Home", content)


def login_page(error: str = "") -> str:
    """Login page HTML"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container" style="max-width: 500px;">
        <div class="card">
            <h2>Sign In</h2>
            <p style="margin-bottom: 2rem;">Access your HR Platform account</p>
            
            {error_html}
            
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">Email Address</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                
                <button type="submit" class="btn btn-primary" style="width: 100%;">Sign In</button>
            </form>
            
            <p style="text-align: center; margin-top: 1.5rem;">
                Don't have an account? <a href="/register" style="color: #2563eb;">Register here</a>
            </p>
        </div>
    </div>
    """
    return get_base_html("Login", content)


def register_page(error: str = "") -> str:
    """Register page HTML"""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container" style="max-width: 500px;">
        <div class="card">
            <h2>Create Account</h2>
            <p style="margin-bottom: 2rem;">Join HR Platform today</p>
            
            {error_html}
            
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Full Name</label>
                    <input type="text" name="full_name" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email Address</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-control" required minlength="6">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Role</label>
                    <select name="role" class="form-control" required>
                        <option value="">Select your role...</option>
                        <option value="candidate">Candidate</option>
                        <option value="hr">HR Specialist</option>
                    </select>
                </div>
                
                <button type="submit" class="btn btn-primary" style="width: 100%;">Create Account</button>
            </form>
            
            <p style="text-align: center; margin-top: 1.5rem;">
                Already have an account? <a href="/login" style="color: #2563eb;">Sign in here</a>
            </p>
        </div>
    </div>
    """
    return get_base_html("Register", content)


def dashboard_page(user: User, db: Session) -> str:
    """Dashboard page HTML"""
    
    # Get statistics
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    recent_analyses = db.query(Analysis).filter(
        Analysis.user_id == user.id
    ).order_by(Analysis.created_at.desc()).limit(5).all()
    
    avg_score = db.query(Analysis).filter(
        Analysis.user_id == user.id,
        Analysis.match_score.isnot(None)
    ).all()
    
    avg_score_value = sum([a.match_score for a in avg_score]) / len(avg_score) if avg_score else 0
    
    if user.role == "candidate":
        role_specific = f"""
        <div class="card">
            <h3>Quick Actions</h3>
            <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                <a href="/upload" class="btn btn-primary">Upload Resume</a>
                <a href="/profile" class="btn btn-outline">View Profile</a>
            </div>
        </div>
        """
    else:
        role_specific = f"""
        <div class="card">
            <h3>Quick Actions</h3>
            <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                <a href="/upload" class="btn btn-primary">Analyze Resume</a>
                <a href="/admin" class="btn btn-secondary">Admin Panel</a>
            </div>
        </div>
        """
    
    recent_list = ""
    for analysis in recent_analyses:
        score_color = "#0ea5e9" if analysis.match_score >= 70 else "#ef4444" if analysis.match_score < 50 else "#f59e0b"
        recent_list += f"""
        <tr>
            <td>{analysis.candidate_name or 'N/A'}</td>
            <td>{analysis.filename}</td>
            <td><span style="color: {score_color}; font-weight: 600;">{analysis.match_score:.1f}%</span></td>
            <td>{analysis.created_at.strftime('%Y-%m-%d %H:%M')}</td>
            <td><a href="/analysis/{analysis.id}" style="color: #2563eb;">View</a></td>
        </tr>
        """
    
    if not recent_list:
        recent_list = '<tr><td colspan="5" style="text-align: center; color: #4b4b4b;">No analyses yet</td></tr>'
    
    content = f"""
    <div class="container">
        <h1>Dashboard</h1>
        <p>Welcome back, {user.full_name}!</p>
        
        <div class="grid grid-3" style="margin-bottom: 2rem;">
            <div class="stat-card">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">Total Analyses</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{avg_score_value:.0f}%</div>
                <div class="stat-label">Average Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{user.role.upper()}</div>
                <div class="stat-label">Account Type</div>
            </div>
        </div>
        
        {role_specific}
        
        <div class="card">
            <h3>Recent Analyses</h3>
            <table style="margin-top: 1rem;">
                <thead>
                    <tr>
                        <th>Candidate</th>
                        <th>File</th>
                        <th>Score</th>
                        <th>Date</th>
                        <th>Action</th>
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


def profile_page(user: User) -> str:
    """Profile page HTML"""
    content = f"""
    <div class="container" style="max-width: 800px;">
        <h1>Profile</h1>
        
        <div class="card">
            <h3>Account Information</h3>
            <div class="grid grid-2" style="margin-top: 1.5rem;">
                <div>
                    <p style="font-weight: 600; margin-bottom: 0.25rem;">Full Name</p>
                    <p>{user.full_name}</p>
                </div>
                <div>
                    <p style="font-weight: 600; margin-bottom: 0.25rem;">Email</p>
                    <p>{user.email}</p>
                </div>
                <div>
                    <p style="font-weight: 600; margin-bottom: 0.25rem;">Role</p>
                    <p style="text-transform: capitalize;">{user.role}</p>
                </div>
                <div>
                    <p style="font-weight: 600; margin-bottom: 0.25rem;">Member Since</p>
                    <p>{user.created_at.strftime('%B %d, %Y')}</p>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3>Settings</h3>
            <p style="color: #4b4b4b;">Profile settings and preferences coming soon...</p>
        </div>
    </div>
    """
    return get_base_html("Profile", content, user)


def upload_page(user: User, message: str = "", error: str = "") -> str:
    """Upload page HTML"""
    message_html = f'<div class="alert alert-success">{message}</div>' if message else ""
    error_html = f'<div class="alert alert-error">{error}</div>' if error else ""
    
    content = f"""
    <div class="container" style="max-width: 800px;">
        <h1>Upload Resume</h1>
        <p>Upload a resume for AI-powered analysis</p>
        
        {message_html}
        {error_html}
        
        <div class="card">
            <form method="POST" action="/upload" enctype="multipart/form-data">
                <div class="form-group">
                    <label class="form-label">Candidate Name (Optional)</label>
                    <input type="text" name="candidate_name" class="form-control" placeholder="Enter candidate name...">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Resume File</label>
                    <div class="file-upload" onclick="document.getElementById('file-input').click();">
                        <input type="file" id="file-input" name="file" accept=".pdf,.docx,.doc,.png,.jpg,.jpeg" required onchange="updateFileName(this)">
                        <p id="file-name" style="color: #4b4b4b;">Click to select file or drag and drop</p>
                        <p style="font-size: 14px; color: #4b4b4b; margin-top: 0.5rem;">Supported: PDF, DOCX, PNG, JPG (max 10MB)</p>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-primary" style="width: 100%;">Analyze Resume</button>
            </form>
        </div>
    </div>
    
    <script>
    function updateFileName(input) {{
        const fileName = input.files[0]?.name || 'Click to select file or drag and drop';
        document.getElementById('file-name').textContent = fileName;
    }}
    </script>
    """
    return get_base_html("Upload Resume", content, user)


def analysis_result_page(user: User, analysis: Analysis, db: Session) -> str:
    """Analysis result page HTML"""
    
    analysis_data = json.loads(analysis.analysis_data)
    
    score_color = "#0ea5e9" if analysis.match_score >= 70 else "#ef4444" if analysis.match_score < 50 else "#f59e0b"
    
    strengths_html = "".join([f"<li>{s}</li>" for s in analysis_data.get('strengths', [])])
    weaknesses_html = "".join([f"<li>{s}</li>" for s in analysis_data.get('weaknesses', [])])
    dev_plan_html = "".join([f"<li>{s}</li>" for s in analysis_data.get('development_plan', [])])
    recommendations_html = "".join([f"<li>{s}</li>" for s in analysis_data.get('recommendations', [])])
    
    content = f"""
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
            <h1>Analysis Results</h1>
            <a href="/dashboard" class="btn btn-outline">Back to Dashboard</a>
        </div>
        
        <div class="card">
            <div style="text-align: center;">
                <h3>{analysis.candidate_name or 'Resume Analysis'}</h3>
                <p style="color: #4b4b4b;">{analysis.filename}</p>
                <div class="score-circle" style="background: {score_color};">
                    {analysis.match_score:.0f}
                </div>
                <p style="font-size: 18px; color: #4b4b4b;">{analysis_data.get('summary', '')}</p>
            </div>
        </div>
        
        <div class="grid grid-2">
            <div class="card">
                <h3>Strengths</h3>
                <ul class="list-disc">
                    {strengths_html}
                </ul>
            </div>
            
            <div class="card">
                <h3>Areas for Improvement</h3>
                <ul class="list-disc">
                    {weaknesses_html}
                </ul>
            </div>
        </div>
        
        <div class="card">
            <h3>Experience Assessment</h3>
            <p>{analysis_data.get('experience_assessment', 'N/A')}</p>
        </div>
        
        <div class="card">
            <h3>Education Assessment</h3>
            <p>{analysis_data.get('education_assessment', 'N/A')}</p>
        </div>
        
        <div class="card">
            <h3>Development Plan</h3>
            <ul class="list-disc">
                {dev_plan_html}
            </ul>
        </div>
        
        <div class="card">
            <h3>Resume Recommendations</h3>
            <ul class="list-disc">
                {recommendations_html}
            </ul>
        </div>
    </div>
    """
    return get_base_html("Analysis Results", content, user)


def admin_page(user: User, db: Session) -> str:
    """Admin page HTML"""
    
    if user.role != "hr":
        return get_base_html("Access Denied", "<div class='container'><h1>Access Denied</h1></div>", user)
    
    total_users = db.query(User).count()
    total_analyses = db.query(Analysis).count()
    total_candidates = db.query(User).filter(User.role == "candidate").count()
    total_hr = db.query(User).filter(User.role == "hr").count()
    
    recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    
    users_list = ""
    for u in recent_users:
        users_list += f"""
        <tr>
            <td>{u.full_name}</td>
            <td>{u.email}</td>
            <td style="text-transform: capitalize;">{u.role}</td>
            <td>{u.created_at.strftime('%Y-%m-%d')}</td>
            <td>{'✓' if u.is_active else '✗'}</td>
        </tr>
        """
    
    content = f"""
    <div class="container">
        <h1>Admin Panel</h1>
        <p>Platform overview and management</p>
        
        <div class="grid grid-3" style="margin-bottom: 2rem;">
            <div class="stat-card">
                <div class="stat-value">{total_users}</div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">Total Analyses</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_candidates}/{total_hr}</div>
                <div class="stat-label">Candidates / HR</div>
            </div>
        </div>
        
        <div class="card">
            <h3>Recent Users</h3>
            <table style="margin-top: 1rem;">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Joined</th>
                        <th>Active</th>
                    </tr>
                </thead>
                <tbody>
                    {users_list}
                </tbody>
            </table>
        </div>
    </div>
    """
    return get_base_html("Admin Panel", content, user)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

app = FastAPI(title="HR Agent Platform", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Initialize application"""
    Config.init()
    init_db()
    print("HR Platform initialized successfully")


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
    
    # Log analytics
    analytics = Analytics(
        user_id=user.id,
        action="login",
        metadata=json.dumps({"email": email})
    )
    db.add(analytics)
    
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
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle registration"""
    
    # Validate role
    if role not in ["candidate", "hr"]:
        return HTMLResponse(register_page(error="Invalid role selected"))
    
    # Check if user exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return HTMLResponse(register_page(error="Email already registered"))
    
    # Create user
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role
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
async def profile(user: User = Depends(require_auth)):
    """Profile page"""
    return profile_page(user)


@app.get("/upload", response_class=HTMLResponse)
async def upload_get(user: User = Depends(require_auth)):
    """Upload page"""
    return upload_page(user)


@app.post("/upload")
async def upload_post(
    candidate_name: str = Form(""),
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
    analysis_data = await analyze_resume_with_ollama(resume_text, user.role)
    
    # Save analysis
    analysis = Analysis(
        user_id=user.id,
        candidate_name=candidate_name or "Unknown",
        filename=file.filename,
        file_path=str(file_path),
        analysis_type="resume_analysis",
        match_score=analysis_data.get("match_score", 0),
        analysis_data=json.dumps(analysis_data)
    )
    db.add(analysis)
    
    # Log analytics
    analytics = Analytics(
        user_id=user.id,
        action="upload",
        metadata=json.dumps({"filename": file.filename})
    )
    db.add(analytics)
    
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
    
    return analysis_result_page(user, analysis, db)


@app.get("/admin", response_class=HTMLResponse)
async def admin(
    user: User = Depends(require_role("hr")),
    db: Session = Depends(get_db)
):
    """Admin panel"""
    return admin_page(user, db)


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
