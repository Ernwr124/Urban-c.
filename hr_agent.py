"""
HR Agent - AI-Powered Resume Analysis Platform
Professional Beta Version - Candidate Edition
Minimalist Black & White Design with Advanced AI Analysis
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
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import (
    FastAPI, Request, Response, HTTPException, UploadFile, 
    File, Form, Depends, Cookie
)
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
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
    """User model - Candidate profile"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    
    # Profile information
    headline = Column(String, default="")
    location = Column(String, default="")
    bio = Column(Text, default="")
    phone = Column(String, default="")
    
    # Profile media
    avatar = Column(String, default="")
    resume_file = Column(String, default="")
    
    # Skills (manually entered for accurate matching)
    skills = Column(Text, default="")
    
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


# ============================================================================
# AI ANALYSIS - ADVANCED VERSION
# ============================================================================

async def compare_resume_with_job(resume_text: str, job_description: str, candidate_skills: str = "") -> Dict[str, Any]:
    """Compare resume with job description using Ollama - Advanced Russian Analysis"""
    
    skills_section = ""
    if candidate_skills:
        skills_section = f"""

ПОДТВЕРЖДЁННЫЕ НАВЫКИ КАНДИДАТА:
{candidate_skills}

ВАЖНО: Это навыки, которые кандидат явно подтвердил. 
Используй их как ПЕРВИЧНЫЙ ИСТОЧНИК при оценке соответствия навыков.
Помечай навыки как "совпадающие" ТОЛЬКО если они есть в этом списке подтверждённых навыков.
"""
    
    prompt = f"""Ты - эксперт HR-аналитик и карьерный консультант с 15+ летним опытом. Твоя задача - провести МАКСИМАЛЬНО ДЕТАЛЬНЫЙ, ПРОФЕССИОНАЛЬНЫЙ и ТОЧНЫЙ анализ соответствия резюме кандидата описанию вакансии.

КРИТИЧЕСКИ ВАЖНО: ВЕСЬ АНАЛИЗ ДОЛЖЕН БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

РЕЗЮМЕ КАНДИДАТА:
{resume_text}
{skills_section}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ОПИСАНИЕ ВАКАНСИИ:
{job_description}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ТРЕБОВАНИЯ К АНАЛИЗУ:

1. ДЕТАЛЬНОСТЬ:
   - Минимум 7-10 пунктов в каждой категории
   - Каждый пункт должен быть КОНКРЕТНЫМ с примерами
   - Избегай общих фраз типа "хороший опыт"
   - Указывай точные технологии, проекты, достижения

2. ЧЕСТНОСТЬ И ОБЪЕКТИВНОСТЬ:
   - Оценивай реалистично без преувеличений
   - Указывай как сильные, так и слабые стороны
   - Будь конструктивным в критике

3. ПРАКТИЧНОСТЬ:
   - Все рекомендации должны быть реализуемыми
   - Указывай конкретные шаги для улучшения
   - Приоритизируй рекомендации по важности

4. ГЛУБИНА АНАЛИЗА:
   - Оценивай не только наличие навыков, но и их глубину
   - Анализируй соответствие уровня опыта требованиям
   - Учитывай культурный fit и soft skills

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ВЕРНИ ОТВЕТ В ФОРМАТЕ JSON (СТРОГО БЕЗ MARKDOWN):

{{
    "match_score": <число от 0 до 100>,
    
    "pros": [
        "МИНИМУМ 7-10 КОНКРЕТНЫХ сильных сторон на русском",
        "Каждый пункт с конкретными примерами из резюме",
        "Указывай точные технологии, проекты, цифры",
        "Отмечай уникальные преимущества кандидата"
    ],
    
    "cons": [
        "МИНИМУМ 7-10 КОНКРЕТНЫХ недостатков на русском",
        "Указывай что именно отсутствует или недостаточно",
        "Отмечай несоответствия уровня опыта",
        "Будь конструктивным - предлагай пути решения"
    ],
    
    "skills_match": {{
        "matched": [
            "Список навыков которые ЕСТЬ у кандидата и ТРЕБУЮТСЯ в вакансии"
        ],
        "missing": [
            "Список навыков которых НЕТ у кандидата, но ТРЕБУЮТСЯ в вакансии"
        ],
        "additional": [
            "Дополнительные полезные навыки кандидата, не указанные в вакансии"
        ]
    }},
    
    "experience_match": {{
        "score": <0-100>,
        "analysis": "ДЕТАЛЬНЫЙ анализ опыта работы на русском (4-5 предложений): количество лет, релевантность проектов, уровень ответственности, достижения с цифрами, соответствие требованиям позиции"
    }},
    
    "education_match": {{
        "score": <0-100>,
        "analysis": "ДЕТАЛЬНЫЙ анализ образования на русском (3-4 предложения): специальность, уровень (бакалавр/магистр), релевантность вакансии, дополнительные курсы и сертификаты"
    }},
    
    "recommendations": [
        "МИНИМУМ 7-10 КОНКРЕТНЫХ рекомендаций на русском",
        "Каждая рекомендация реализуема и специфична",
        "Указывай приоритет (высокий/средний/низкий)",
        "Предлагай конкретные курсы, книги, проекты"
    ],
    
    "interview_questions": [
        "5-7 КОНКРЕТНЫХ вопросов на русском для проверки опыта",
        "Вопросы должны раскрывать реальную глубину знаний",
        "Включай технические и поведенческие вопросы"
    ],
    
    "summary": "ПОДРОБНОЕ итоговое резюме на русском (4-6 предложений): общая оценка кандидата, ключевые сильные стороны, критические пробелы, потенциал для роста, финальная рекомендация по найму (стоит ли приглашать на интервью)"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

КРИТИЧЕСКИ ВАЖНО:
✓ ВСЕ ТЕКСТЫ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ
✓ МАКСИМАЛЬНАЯ ДЕТАЛИЗАЦИЯ И КОНКРЕТИКА
✓ ЧЕСТНАЯ И ОБЪЕКТИВНАЯ ОЦЕНКА
✓ КОНКРЕТНЫЕ ПРИМЕРЫ ИЗ РЕЗЮМЕ
✓ РЕАЛИЗУЕМЫЕ РЕКОМЕНДАЦИИ
✓ БЕЗ ОБЩИХ ФРАЗ И ШАБЛОНОВ

Верни ТОЛЬКО JSON без дополнительного текста или markdown."""

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
                    analysis_data = json.loads(response_text)
                    # Validate structure
                    if "match_score" in analysis_data and "pros" in analysis_data:
                        return analysis_data
                    else:
                        return create_fallback_analysis()
                except json.JSONDecodeError:
                    print(f"JSON decode error")
                    return create_fallback_analysis()
            else:
                return create_fallback_analysis()
                
    except Exception as e:
        print(f"Ollama error: {str(e)}")
        return create_fallback_analysis()


def create_fallback_analysis() -> Dict[str, Any]:
    """Create fallback analysis when Ollama is unavailable"""
    return {
        "match_score": 0,
        "pros": [
            "AI-анализ временно недоступен",
            "Запустите Ollama для получения детального анализа"
        ],
        "cons": [
            "Не удалось выполнить анализ",
            "Проверьте подключение к Ollama"
        ],
        "skills_match": {
            "matched": [],
            "missing": ["Ожидание AI-анализа"],
            "additional": []
        },
        "experience_match": {
            "score": 0,
            "analysis": "Для анализа опыта необходимо подключение к Ollama. Запустите: ollama serve"
        },
        "education_match": {
            "score": 0,
            "analysis": "Для анализа образования необходимо подключение к Ollama."
        },
        "recommendations": [
            "Запустите Ollama: ollama serve",
            "Загрузите модель: ollama pull gpt-oss:20b-cloud",
            "Проверьте доступность API на http://localhost:11434"
        ],
        "interview_questions": [
            "AI-анализ недоступен - запустите Ollama для генерации вопросов"
        ],
        "summary": "Для получения детального AI-анализа необходимо подключение к Ollama с моделью gpt-oss:20b-cloud. После подключения вы получите профессиональный анализ с 7-10 пунктами в каждой категории."
    }


# ============================================================================
# AUTH DEPENDENCY
# ============================================================================

def require_auth(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> User:
    """Require authentication"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = db.query(Session).filter(Session.session_token == session_token).first()
    if not session or session.expires_at < datetime.utcnow():
        if session:
            db.delete(session)
            db.commit()
        raise HTTPException(status_code=401, detail="Session expired")
    
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user


# ============================================================================
# HTML TEMPLATES - BEAUTIFUL BLACK & WHITE DESIGN
# ============================================================================

def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Base HTML template with modern design"""
    
    nav_links = ""
    if user:
        avatar_html = ""
        if user.avatar:
            avatar_html = f'<img src="/uploads/avatars/{user.avatar}" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; margin-right: 8px;">'
        else:
            avatar_html = '<span style="font-size: 20px; margin-right: 8px;">👤</span>'
        
        nav_links = f"""
            <a href="/dashboard" class="nav-link">Панель</a>
            <a href="/analyze" class="nav-link">Анализ</a>
            <a href="/profile" class="nav-link" style="display: flex; align-items: center;">
                {avatar_html}{user.full_name}
            </a>
            <a href="/logout" class="nav-link">Выйти</a>
        """
    else:
        nav_links = """
            <a href="/login" class="nav-link">Войти</a>
            <a href="/register" class="btn-primary">Начать бесплатно</a>
        """
    
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HR Agent</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        :root {{
            --black: #000000;
            --white: #FFFFFF;
            --gray-100: #F5F5F5;
            --gray-200: #E5E5E5;
            --gray-300: #D4D4D4;
            --gray-400: #A3A3A3;
            --gray-500: #737373;
            --gray-600: #525252;
            --gray-700: #404040;
            --gray-800: #262626;
            --gray-900: #171717;
            --success: #22c55e;
            --warning: #eab308;
            --danger: #ef4444;
            --blue: #3b82f6;
            --purple: #a855f7;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
            background: var(--black);
            color: var(--white);
            line-height: 1.6;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}
        
        /* Navigation */
        nav {{
            background: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            position: sticky;
            top: 0;
            z-index: 1000;
            backdrop-filter: blur(20px);
        }}
        
        .nav-container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .logo {{
            font-size: 26px;
            font-weight: 700;
            color: var(--white);
            text-decoration: none;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, var(--white), var(--gray-400));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .nav-links {{
            display: flex;
            gap: 32px;
            align-items: center;
        }}
        
        .nav-link {{
            color: var(--white);
            text-decoration: none;
            opacity: 0.7;
            transition: all 0.2s;
            font-weight: 500;
            font-size: 15px;
        }}
        
        .nav-link:hover {{
            opacity: 1;
        }}
        
        /* Buttons */
        .btn, .btn-primary, .btn-outline, .btn-danger {{
            padding: 12px 24px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            transition: all 0.2s;
            font-size: 15px;
            border: none;
            text-align: center;
        }}
        
        .btn-primary {{
            background: var(--white);
            color: var(--black);
        }}
        
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(255, 255, 255, 0.15);
        }}
        
        .btn-outline {{
            background: transparent;
            color: var(--white);
            border: 1.5px solid rgba(255, 255, 255, 0.3);
        }}
        
        .btn-outline:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--white);
        }}
        
        .btn-danger {{
            background: var(--danger);
            color: var(--white);
        }}
        
        .btn-large {{
            padding: 16px 32px;
            font-size: 16px;
        }}
        
        /* Layout */
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 64px 32px;
        }}
        
        .container-sm {{
            max-width: 800px;
            margin: 0 auto;
            padding: 64px 32px;
        }}
        
        /* Card */
        .card {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 24px;
            transition: all 0.3s;
        }}
        
        .card:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-2px);
        }}
        
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }}
        
        /* Form */
        .form-group {{
            margin-bottom: 24px;
        }}
        
        .form-label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            font-size: 14px;
            color: var(--white);
        }}
        
        .form-control {{
            width: 100%;
            padding: 14px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 1.5px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: var(--white);
            font-size: 15px;
            transition: all 0.2s;
            font-family: inherit;
        }}
        
        .form-control:focus {{
            outline: none;
            border-color: var(--white);
            background: rgba(255, 255, 255, 0.08);
        }}
        
        .form-control::placeholder {{
            color: var(--gray-500);
        }}
        
        textarea.form-control {{
            min-height: 140px;
            resize: vertical;
        }}
        
        /* Typography */
        h1 {{
            font-size: 56px;
            font-weight: 700;
            margin-bottom: 16px;
            letter-spacing: -1.5px;
            line-height: 1.1;
        }}
        
        h2 {{
            font-size: 40px;
            font-weight: 700;
            margin-bottom: 16px;
            letter-spacing: -1px;
        }}
        
        h3 {{
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 16px;
        }}
        
        .text-muted {{
            color: var(--gray-400);
        }}
        
        .text-sm {{
            font-size: 14px;
        }}
        
        .text-xs {{
            font-size: 12px;
        }}
        
        /* Stats */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 24px;
            margin-bottom: 48px;
        }}
        
        .stat-card {{
            background: rgba(255, 255, 255, 0.03);
            padding: 32px;
            border-radius: 16px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s;
        }}
        
        .stat-card:hover {{
            background: rgba(255, 255, 255, 0.06);
            transform: translateY(-4px);
        }}
        
        .stat-value {{
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 8px;
            background: linear-gradient(135deg, var(--white), var(--gray-400));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .stat-label {{
            color: var(--gray-400);
            font-size: 14px;
            font-weight: 500;
        }}
        
        /* File Upload */
        .file-upload {{
            border: 2px dashed rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            padding: 64px 32px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }}
        
        .file-upload:hover {{
            border-color: var(--white);
            background: rgba(255, 255, 255, 0.03);
        }}
        
        .file-icon {{
            font-size: 64px;
            margin-bottom: 16px;
            filter: grayscale(1);
        }}
        
        input[type="file"] {{
            display: none;
        }}
        
        /* Profile */
        .profile-header {{
            display: flex;
            gap: 32px;
            align-items: flex-start;
            margin-bottom: 32px;
        }}
        
        .profile-avatar {{
            width: 160px;
            height: 160px;
            border-radius: 50%;
            object-fit: cover;
            border: 4px solid var(--white);
            box-shadow: 0 8px 32px rgba(255, 255, 255, 0.1);
        }}
        
        .profile-info {{
            flex: 1;
        }}
        
        .skills-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }}
        
        .skill-tag {{
            background: rgba(255, 255, 255, 0.08);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            font-weight: 500;
        }}
        
        .social-links {{
            display: flex;
            gap: 16px;
            margin-top: 16px;
            flex-wrap: wrap;
        }}
        
        .social-link {{
            color: var(--blue);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }}
        
        .social-link:hover {{
            opacity: 0.8;
        }}
        
        /* Score Badge */
        .score-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 120px;
            height: 120px;
            border-radius: 50%;
            font-size: 48px;
            font-weight: 700;
            margin: 32px 0;
        }}
        
        .score-success {{
            background: linear-gradient(135deg, var(--success), #16a34a);
            color: var(--white);
            box-shadow: 0 8px 32px rgba(34, 197, 94, 0.3);
        }}
        
        .score-warning {{
            background: linear-gradient(135deg, var(--warning), #ca8a04);
            color: var(--white);
            box-shadow: 0 8px 32px rgba(234, 179, 8, 0.3);
        }}
        
        .score-danger {{
            background: linear-gradient(135deg, var(--danger), #dc2626);
            color: var(--white);
            box-shadow: 0 8px 32px rgba(239, 68, 68, 0.3);
        }}
        
        /* Lists */
        ul {{
            margin-left: 20px;
            margin-top: 12px;
        }}
        
        li {{
            margin-bottom: 12px;
            line-height: 1.7;
            color: var(--gray-300);
        }}
        
        /* Hero Section */
        .hero {{
            text-align: center;
            padding: 120px 32px 80px;
        }}
        
        .hero h1 {{
            font-size: 72px;
            margin-bottom: 24px;
        }}
        
        .hero-subtitle {{
            font-size: 20px;
            color: var(--gray-400);
            max-width: 600px;
            margin: 0 auto 48px;
            line-height: 1.6;
        }}
        
        /* Responsive */
        @media (max-width: 768px) {{
            .profile-header {{
                flex-direction: column;
                align-items: center;
                text-align: center;
            }}
            
            h1 {{
                font-size: 40px;
            }}
            
            .hero h1 {{
                font-size: 48px;
            }}
            
            .nav-links {{
                gap: 16px;
            }}
        }}
        
        /* Loading Animation */
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .loading {{
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }}
    </style>
</head>
<body>
    <nav>
        <div class="nav-container">
            <a href="/" class="logo">HR Agent</a>
            <div class="nav-links">{nav_links}</div>
        </div>
    </nav>
    <main>{content}</main>
</body>
</html>"""


# ============================================================================
# ROUTES
# ============================================================================

app = FastAPI(
    title="HR Agent",
    description="AI-Powered Resume Analysis Platform",
    version="2.0.0-beta"
)


@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    Config.init()
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing():
    """Landing page"""
    content = """
    <div class="hero">
        <h1>HR Agent</h1>
        <p class="hero-subtitle">
            Профессиональный AI-анализ вашего резюме. Узнайте насколько вы подходите для вакансии мечты.
        </p>
        <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
            <a href="/register" class="btn-primary btn-large">Начать бесплатно</a>
            <a href="/login" class="btn-outline btn-large">Войти</a>
        </div>
    </div>
    
    <div class="container" style="padding-top: 0;">
        <div class="stats-grid">
            <div class="stat-card">
                <div style="font-size: 48px; margin-bottom: 16px;">🎯</div>
                <div class="stat-value">AI</div>
                <div class="stat-label">Анализ с gpt-oss:20b</div>
            </div>
            <div class="stat-card">
                <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
                <div class="stat-value">7-10</div>
                <div class="stat-label">Пунктов в категории</div>
            </div>
            <div class="stat-card">
                <div style="font-size: 48px; margin-bottom: 16px;">⚡</div>
                <div class="stat-value">60сек</div>
                <div class="stat-label">Время анализа</div>
            </div>
        </div>
    </div>
    """
    return get_base_html("Главная", content)


@app.get("/register", response_class=HTMLResponse)
async def register_page():
    """Registration page"""
    content = """
    <div class="container-sm">
        <div style="text-align: center; margin-bottom: 48px;">
            <h1 style="font-size: 48px;">Регистрация</h1>
            <p class="text-muted">Создайте аккаунт для начала работы</p>
        </div>
        
        <div class="card">
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Полное имя *</label>
                    <input type="text" name="full_name" class="form-control" required placeholder="Иван Иванов">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email *</label>
                    <input type="email" name="email" class="form-control" required placeholder="ivan@example.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль *</label>
                    <input type="password" name="password" class="form-control" required placeholder="Минимум 6 символов">
                </div>
                
                <button type="submit" class="btn-primary btn-large" style="width: 100%;">
                    Создать аккаунт
                </button>
            </form>
        </div>
        
        <p class="text-muted text-sm" style="text-align: center; margin-top: 24px;">
            Уже есть аккаунт? <a href="/login" style="color: var(--white); font-weight: 600;">Войти</a>
        </p>
    </div>
    """
    return get_base_html("Регистрация", content)


@app.post("/register")
async def register_post(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle registration"""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть минимум 6 символов")
    
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session.session_token,
        httponly=True,
        max_age=Config.SESSION_LIFETIME_HOURS * 3600
    )
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Login page"""
    content = """
    <div class="container-sm">
        <div style="text-align: center; margin-bottom: 48px;">
            <h1 style="font-size: 48px;">Вход</h1>
            <p class="text-muted">Войдите в свой аккаунт</p>
        </div>
        
        <div class="card">
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="ivan@example.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required placeholder="Введите пароль">
                </div>
                
                <button type="submit" class="btn-primary btn-large" style="width: 100%;">
                    Войти
                </button>
            </form>
        </div>
        
        <p class="text-muted text-sm" style="text-align: center; margin-top: 24px;">
            Нет аккаунта? <a href="/register" style="color: var(--white); font-weight: 600;">Зарегистрироваться</a>
        </p>
    </div>
    """
    return get_base_html("Вход", content)


@app.post("/login")
async def login_post(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle login"""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    
    user.last_login = datetime.utcnow()
    
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session.session_token,
        httponly=True,
        max_age=Config.SESSION_LIFETIME_HOURS * 3600
    )
    return response


@app.get("/logout")
async def logout(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Logout"""
    if session_token:
        session = db.query(Session).filter(Session.session_token == session_token).first()
        if session:
            db.delete(session)
            db.commit()
    
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Dashboard"""
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    analyses = db.query(Analysis).filter(Analysis.user_id == user.id).order_by(
        Analysis.created_at.desc()
    ).limit(10).all()
    
    avg_score = 0
    if analyses:
        scores = [a.match_score for a in analyses if a.match_score]
        avg_score = sum(scores) / len(scores) if scores else 0
    
    history_html = ""
    for analysis in analyses:
        score = int(analysis.match_score) if analysis.match_score else 0
        
        if score >= 70:
            color_class = "score-success"
            color = "var(--success)"
        elif score >= 50:
            color_class = "score-warning"
            color = "var(--warning)"
        else:
            color_class = "score-danger"
            color = "var(--danger)"
        
        job_preview = (analysis.job_description[:180] + "...") if len(analysis.job_description) > 180 else analysis.job_description
        
        history_html += f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 32px;">
                <div style="flex: 1;">
                    <h3 style="margin-bottom: 12px;">{analysis.filename}</h3>
                    <p class="text-muted text-sm" style="margin-bottom: 8px;">
                        {analysis.created_at.strftime('%d.%m.%Y в %H:%M')}
                    </p>
                    <p class="text-sm" style="color: var(--gray-400); line-height: 1.6;">
                        {job_preview}
                    </p>
                </div>
                <div style="text-align: center;">
                    <div class="score-badge {color_class}" style="width: 100px; height: 100px; font-size: 32px;">
                        {score}%
                    </div>
                    <a href="/result/{analysis.id}" class="btn-outline" style="margin-top: 16px; display: inline-block;">
                        Посмотреть
                    </a>
                </div>
            </div>
        </div>
        """
    
    if not history_html:
        history_html = """
        <div class="card" style="text-align: center; padding: 80px 32px;">
            <div style="font-size: 72px; margin-bottom: 24px;">📄</div>
            <h3 style="margin-bottom: 16px;">Анализов пока нет</h3>
            <p class="text-muted" style="margin-bottom: 32px;">
                Загрузите своё резюме и описание вакансии для получения детального AI-анализа
            </p>
            <a href="/analyze" class="btn-primary btn-large">Начать анализ</a>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 48px;">
            <h1>Панель управления</h1>
            <p class="text-muted">Добро пожаловать, {user.full_name}!</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_analyses}</div>
                <div class="stat-label">Всего анализов</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{int(avg_score)}%</div>
                <div class="stat-label">Средний балл</div>
            </div>
        </div>
        
        <div style="margin-bottom: 48px; display: flex; gap: 16px; flex-wrap: wrap;">
            <a href="/analyze" class="btn-primary btn-large">Новый анализ</a>
            <a href="/profile" class="btn-outline btn-large">Мой профиль</a>
        </div>
        
        <h2 style="margin-bottom: 32px;">История анализов</h2>
        {history_html}
    </div>
    """
    return get_base_html("Панель", content, user)


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(user: User = Depends(require_auth)):
    """Analysis page"""
    content = """
    <div class="container-sm">
        <div style="margin-bottom: 48px;">
            <h1>AI-Анализ резюме</h1>
            <p class="text-muted">
                Получите профессиональный анализ соответствия вашего резюме выбранной вакансии
            </p>
        </div>
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <h3 style="margin-bottom: 24px;">📄 Шаг 1: Загрузите резюме</h3>
                <div class="file-upload" onclick="document.getElementById('resume-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="resume-input" name="resume" accept=".pdf,.docx" required>
                    <p style="font-weight: 600; font-size: 18px; margin-bottom: 8px;">Выберите файл резюме</p>
                    <p class="text-muted">PDF или DOCX, максимум 10MB</p>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-bottom: 24px;">💼 Шаг 2: Опишите вакансию</h3>
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Полное описание вакансии *</label>
                    <textarea 
                        name="job_description" 
                        class="form-control" 
                        required 
                        placeholder="Вставьте полное описание вакансии: должность, требования, обязанности, квалификация, технологии..."
                        style="min-height: 220px;"
                    ></textarea>
                    <p class="text-muted text-xs" style="margin-top: 12px;">
                        💡 Чем детальнее описание, тем точнее и полезнее будет AI-анализ
                    </p>
                </div>
            </div>
            
            <button type="submit" class="btn-primary btn-large" style="width: 100%; font-size: 18px;">
                🚀 Запустить AI-анализ
            </button>
        </form>
    </div>
    
    <script>
        document.getElementById('resume-input').addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name || '';
            if (fileName) {
                const uploadDiv = document.querySelector('.file-upload');
                uploadDiv.innerHTML = `
                    <div class="file-icon">✅</div>
                    <p style="font-weight: 600; font-size: 18px; margin-bottom: 8px;">${fileName}</p>
                    <p class="text-muted">Файл успешно загружен</p>
                `;
            }
        });
    </script>
    """
    return get_base_html("Анализ резюме", content, user)


@app.post("/analyze")
async def analyze_post(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Handle analysis"""
    content = await resume.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс 10MB)")
    
    resume_text = parse_resume(resume.filename, content)
    
    if "[Error" in resume_text or "[Unsupported" in resume_text:
        raise HTTPException(status_code=400, detail=f"Ошибка обработки файла: {resume_text}")
    
    analysis_result = await compare_resume_with_job(resume_text, job_description, user.skills)
    
    analysis = Analysis(
        user_id=user.id,
        filename=resume.filename,
        file_path="",
        job_description=job_description,
        match_score=analysis_result.get('match_score', 0),
        analysis_data=json.dumps(analysis_result, ensure_ascii=False)
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    
    return RedirectResponse(f"/result/{analysis.id}", status_code=303)


@app.get("/result/{analysis_id}", response_class=HTMLResponse)
async def result_page(analysis_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Result page"""
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Анализ не найден")
    
    data = json.loads(analysis.analysis_data)
    score = int(data.get('match_score', 0))
    
    if score >= 70:
        color_class = "score-success"
        status_text = "Отличное соответствие"
        status_icon = "🎉"
    elif score >= 50:
        color_class = "score-warning"
        status_text = "Хорошее соответствие"
        status_icon = "👍"
    else:
        color_class = "score-danger"
        status_text = "Требуется улучшение"
        status_icon = "📈"
    
    # Pros
    pros_html = ""
    for pro in data.get('pros', []):
        pros_html += f"<li>{pro}</li>"
    
    # Cons
    cons_html = ""
    for con in data.get('cons', []):
        cons_html += f"<li>{con}</li>"
    
    # Recommendations
    recs_html = ""
    for rec in data.get('recommendations', []):
        recs_html += f"<li>{rec}</li>"
    
    # Interview questions
    questions_html = ""
    for q in data.get('interview_questions', []):
        questions_html += f"<li>{q}</li>"
    
    # Skills
    skills_match = data.get('skills_match', {})
    matched = skills_match.get('matched', [])
    missing = skills_match.get('missing', [])
    additional = skills_match.get('additional', [])
    
    matched_html = ", ".join(matched) if matched else "Не указано"
    missing_html = ", ".join(missing) if missing else "Не указано"
    additional_html = ", ".join(additional) if additional else "Не указано"
    
    # Experience and Education
    exp_match = data.get('experience_match', {})
    exp_score = exp_match.get('score', 0)
    exp_analysis = exp_match.get('analysis', 'Нет данных')
    
    edu_match = data.get('education_match', {})
    edu_score = edu_match.get('score', 0)
    edu_analysis = edu_match.get('analysis', 'Нет данных')
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 32px;">
            <h1>Результат анализа</h1>
            <p class="text-muted">
                {analysis.filename} • {analysis.created_at.strftime('%d.%m.%Y в %H:%M')}
            </p>
        </div>
        
        <!-- Main Score -->
        <div class="card" style="text-align: center; background: linear-gradient(135deg, rgba(255,255,255,0.03), rgba(255,255,255,0.08)); padding: 60px 40px;">
            <div style="font-size: 56px; margin-bottom: 24px;">{status_icon}</div>
            <div class="score-badge {color_class}" style="width: 140px; height: 140px; font-size: 56px; margin: 0 auto;">
                {score}%
            </div>
            <h2 style="margin: 32px 0 8px;">{status_text}</h2>
            <p class="text-muted">Соответствие вакансии</p>
        </div>
        
        <!-- Pros & Cons -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 24px; margin-top: 24px;">
            <div class="card">
                <h3 style="color: var(--success); margin-bottom: 24px;">✓ Сильные стороны</h3>
                <ul>{pros_html}</ul>
            </div>
            
            <div class="card">
                <h3 style="color: var(--danger); margin-bottom: 24px;">✗ Области для улучшения</h3>
                <ul>{cons_html}</ul>
            </div>
        </div>
        
        <!-- Skills Analysis -->
        <div class="card">
            <h3 style="margin-bottom: 24px;">🎯 Анализ навыков</h3>
            <div style="display: grid; gap: 24px;">
                <div>
                    <strong style="color: var(--success); font-size: 16px;">✓ Есть у вас:</strong>
                    <p class="text-muted" style="margin-top: 8px; line-height: 1.8;">{matched_html}</p>
                </div>
                <div>
                    <strong style="color: var(--danger); font-size: 16px;">✗ Не хватает:</strong>
                    <p class="text-muted" style="margin-top: 8px; line-height: 1.8;">{missing_html}</p>
                </div>
                <div>
                    <strong style="color: var(--blue); font-size: 16px;">+ Дополнительные:</strong>
                    <p class="text-muted" style="margin-top: 8px; line-height: 1.8;">{additional_html}</p>
                </div>
            </div>
        </div>
        
        <!-- Experience & Education -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 24px;">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h3 style="margin: 0;">💼 Опыт работы</h3>
                    <span style="font-size: 24px; font-weight: 700; color: var(--success);">{exp_score}%</span>
                </div>
                <p class="text-muted" style="line-height: 1.8;">
                    {exp_analysis}
                </p>
            </div>
            
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <h3 style="margin: 0;">🎓 Образование</h3>
                    <span style="font-size: 24px; font-weight: 700; color: var(--success);">{edu_score}%</span>
                </div>
                <p class="text-muted" style="line-height: 1.8;">
                    {edu_analysis}
                </p>
            </div>
        </div>
        
        <!-- Recommendations -->
        <div class="card">
            <h3 style="margin-bottom: 24px;">💡 Рекомендации для улучшения</h3>
            <ul>{recs_html}</ul>
        </div>
        
        <!-- Interview Questions -->
        {f'''
        <div class="card" style="background: linear-gradient(135deg, rgba(59,130,246,0.05), rgba(168,85,247,0.05));">
            <h3 style="margin-bottom: 24px;">❓ Возможные вопросы на интервью</h3>
            <p class="text-muted" style="margin-bottom: 16px;">
                Подготовьтесь к этим вопросам перед собеседованием:
            </p>
            <ul>{questions_html}</ul>
        </div>
        ''' if questions_html and 'недоступен' not in questions_html else ''}
        
        <!-- Summary -->
        <div class="card" style="background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)); border: 2px solid rgba(255,255,255,0.1);">
            <h3 style="margin-bottom: 16px;">📋 Итоговое резюме</h3>
            <p style="line-height: 1.9; font-size: 16px; color: var(--gray-300);">
                {data.get('summary', 'Нет данных')}
            </p>
        </div>
        
        <!-- Actions -->
        <div style="display: flex; gap: 16px; margin-top: 48px; flex-wrap: wrap;">
            <a href="/dashboard" class="btn-outline btn-large">← Назад к панели</a>
            <a href="/analyze" class="btn-primary btn-large">Новый анализ</a>
            <a href="/profile" class="btn-outline btn-large">Обновить профиль</a>
        </div>
    </div>
    """
    return get_base_html("Результат анализа", content, user)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """Profile page"""
    
    avatar_html = ""
    if user.avatar:
        avatar_html = f'<img src="/uploads/avatars/{user.avatar}" class="profile-avatar" alt="{user.full_name}">'
    else:
        avatar_html = '''<div class="profile-avatar" style="background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05)); 
            display: flex; align-items: center; justify-content: center; font-size: 72px;">👤</div>'''
    
    skills_html = ""
    if user.skills:
        skills_list = [s.strip() for s in user.skills.split(',') if s.strip()]
        for skill in skills_list:
            skills_html += f'<span class="skill-tag">{skill}</span>'
    else:
        skills_html = '<p class="text-muted">Навыки не указаны</p>'
    
    social_html = ""
    if user.linkedin_url:
        social_html += f'<a href="{user.linkedin_url}" target="_blank" class="social-link">🔗 LinkedIn</a>'
    if user.github_url:
        social_html += f'<a href="{user.github_url}" target="_blank" class="social-link">💻 GitHub</a>'
    if user.website:
        social_html += f'<a href="{user.website}" target="_blank" class="social-link">🌐 Веб-сайт</a>'
    
    if not social_html:
        social_html = '<p class="text-muted text-sm">Социальные сети не добавлены</p>'
    
    resume_html = ""
    if user.resume_file:
        resume_html = f'''
        <div style="display: flex; gap: 16px; align-items: center;">
            <a href="/uploads/resumes/{user.resume_file}" target="_blank" class="btn-outline">
                📄 Скачать резюме
            </a>
            <span class="text-muted text-sm">{user.resume_file}</span>
        </div>
        '''
    else:
        resume_html = '<p class="text-muted">Резюме не загружено</p>'
    
    content = f"""
    <div class="container">
        <h1 style="margin-bottom: 48px;">Профиль</h1>
        
        <div class="card">
            <div class="profile-header">
                {avatar_html}
                <div class="profile-info">
                    <h2 style="margin-bottom: 12px;">{user.full_name}</h2>
                    <p class="text-muted" style="font-size: 20px; margin-bottom: 12px;">
                        {user.headline or 'Добавьте заголовок профиля'}
                    </p>
                    <p class="text-muted" style="margin-bottom: 8px;">
                        📍 {user.location or 'Не указано'} • 📧 {user.email}
                    </p>
                    {f'<p class="text-muted">📱 {user.phone}</p>' if user.phone else ''}
                    <div class="social-links">
                        {social_html}
                    </div>
                </div>
            </div>
            
            {f'''
            <div style="margin-top: 32px; padding-top: 32px; border-top: 1px solid rgba(255,255,255,0.1);">
                <h3 style="margin-bottom: 16px;">О себе</h3>
                <p class="text-muted" style="line-height: 1.8;">
                    {user.bio}
                </p>
            </div>
            ''' if user.bio else ''}
            
            <div style="margin-top: 32px; padding-top: 32px; border-top: 1px solid rgba(255,255,255,0.1);">
                <h3 style="margin-bottom: 20px;">Навыки</h3>
                <div class="skills-list">
                    {skills_html}
                </div>
                <p class="text-muted text-xs" style="margin-top: 16px;">
                    💡 Эти навыки используются для более точного AI-анализа
                </p>
            </div>
            
            <div style="margin-top: 32px; padding-top: 32px; border-top: 1px solid rgba(255,255,255,0.1);">
                <h3 style="margin-bottom: 20px;">Резюме</h3>
                {resume_html}
            </div>
            
            <div style="margin-top: 40px; padding-top: 32px; border-top: 1px solid rgba(255,255,255,0.1);">
                <a href="/profile/edit" class="btn-primary btn-large">Редактировать профиль</a>
            </div>
        </div>
    </div>
    """
    return get_base_html("Профиль", content, user)


@app.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(user: User = Depends(require_auth)):
    """Edit profile page"""
    
    avatar_preview = ""
    if user.avatar:
        avatar_preview = f'''
        <div style="text-align: center; margin-bottom: 24px;">
            <img src="/uploads/avatars/{user.avatar}" 
                 style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid var(--white);">
        </div>
        '''
    
    content = f"""
    <div class="container-sm">
        <h1 style="margin-bottom: 48px;">Редактирование профиля</h1>
        
        <form method="POST" action="/profile/update" enctype="multipart/form-data">
            <!-- Avatar -->
            <div class="card">
                <h3 style="margin-bottom: 24px;">Фото профиля</h3>
                {avatar_preview}
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Загрузить новое фото</label>
                    <input type="file" name="avatar" accept="image/*" class="form-control">
                    <p class="text-muted text-xs" style="margin-top: 8px;">PNG, JPG или WEBP, макс 5MB</p>
                </div>
            </div>
            
            <!-- Basic Info -->
            <div class="card">
                <h3 style="margin-bottom: 24px;">Основная информация</h3>
                
                <div class="form-group">
                    <label class="form-label">Полное имя *</label>
                    <input type="text" name="full_name" class="form-control" value="{user.full_name}" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Заголовок профиля</label>
                    <input type="text" name="headline" class="form-control" value="{user.headline}" 
                           placeholder="Frontend Developer | React Specialist">
                    <p class="text-muted text-xs" style="margin-top: 8px;">
                        Например: "Senior Python Developer" или "Data Scientist"
                    </p>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Местоположение</label>
                    <input type="text" name="location" class="form-control" value="{user.location}" 
                           placeholder="Москва, Россия">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input type="tel" name="phone" class="form-control" value="{user.phone}" 
                           placeholder="+7 (999) 123-45-67">
                </div>
                
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">О себе</label>
                    <textarea name="bio" class="form-control" 
                              placeholder="Расскажите о себе, своём опыте и карьерных целях...">{user.bio}</textarea>
                </div>
            </div>
            
            <!-- Skills -->
            <div class="card">
                <h3 style="margin-bottom: 24px;">Навыки</h3>
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Ваши навыки *</label>
                    <textarea name="skills" class="form-control" 
                              placeholder="Python, JavaScript, React, Node.js, Docker, Kubernetes...">{user.skills}</textarea>
                    <p class="text-muted text-xs" style="margin-top: 8px;">
                        💡 Перечислите через запятую. Эти навыки будут использоваться для более точного AI-анализа
                    </p>
                </div>
            </div>
            
            <!-- Social Links -->
            <div class="card">
                <h3 style="margin-bottom: 24px;">Социальные сети</h3>
                
                <div class="form-group">
                    <label class="form-label">LinkedIn</label>
                    <input type="url" name="linkedin_url" class="form-control" value="{user.linkedin_url}" 
                           placeholder="https://linkedin.com/in/username">
                </div>
                
                <div class="form-group">
                    <label class="form-label">GitHub</label>
                    <input type="url" name="github_url" class="form-control" value="{user.github_url}" 
                           placeholder="https://github.com/username">
                </div>
                
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Личный сайт</label>
                    <input type="url" name="website" class="form-control" value="{user.website}" 
                           placeholder="https://mywebsite.com">
                </div>
            </div>
            
            <!-- Resume -->
            <div class="card">
                <h3 style="margin-bottom: 24px;">Резюме</h3>
                {f'<p class="text-muted text-sm" style="margin-bottom: 16px;">Текущее: {user.resume_file}</p>' if user.resume_file else ''}
                <div class="form-group" style="margin-bottom: 0;">
                    <label class="form-label">Загрузить резюме</label>
                    <input type="file" name="resume" accept=".pdf,.docx" class="form-control">
                    <p class="text-muted text-xs" style="margin-top: 8px;">PDF или DOCX, макс 10MB</p>
                </div>
            </div>
            
            <!-- Actions -->
            <div style="display: flex; gap: 16px; flex-wrap: wrap;">
                <button type="submit" class="btn-primary btn-large">Сохранить изменения</button>
                <a href="/profile" class="btn-outline btn-large">Отмена</a>
            </div>
        </form>
    </div>
    """
    return get_base_html("Редактирование профиля", content, user)


@app.post("/profile/update")
async def update_profile(
    full_name: str = Form(...),
    headline: str = Form(""),
    location: str = Form(""),
    phone: str = Form(""),
    bio: str = Form(""),
    skills: str = Form(""),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    website: str = Form(""),
    avatar: Optional[UploadFile] = File(None),
    resume: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """Update profile"""
    
    user.full_name = full_name
    user.headline = headline
    user.location = location
    user.phone = phone
    user.bio = bio
    user.skills = skills
    user.linkedin_url = linkedin_url
    user.github_url = github_url
    user.website = website
    
    # Handle avatar upload
    if avatar and avatar.filename:
        avatar_content = await avatar.read()
        if len(avatar_content) <= 5 * 1024 * 1024:  # 5MB
            ext = avatar.filename.split('.')[-1]
            filename = f"avatar_{user.id}_{secrets.token_urlsafe(8)}.{ext}"
            filepath = Config.UPLOAD_DIR / "avatars" / filename
            
            with open(filepath, 'wb') as f:
                f.write(avatar_content)
            
            user.avatar = filename
    
    # Handle resume upload
    if resume and resume.filename:
        resume_content = await resume.read()
        if len(resume_content) <= Config.MAX_FILE_SIZE:
            ext = resume.filename.split('.')[-1]
            filename = f"resume_{user.id}_{secrets.token_urlsafe(8)}.{ext}"
            filepath = Config.UPLOAD_DIR / "resumes" / filename
            
            with open(filepath, 'wb') as f:
                f.write(resume_content)
            
            user.resume_file = filename
    
    db.commit()
    return RedirectResponse("/profile", status_code=303)


@app.get("/uploads/{folder}/{filename}")
async def serve_upload(folder: str, filename: str):
    """Serve uploaded files"""
    file_path = Config.UPLOAD_DIR / folder / filename
    if file_path.exists():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 HR Agent - Beta Version")
    print("="*60)
    print("✨ Professional Resume Analysis Platform")
    print("🎯 Advanced AI Analysis with gpt-oss:20b-cloud")
    print("🎨 Beautiful Black & White Design")
    print("📊 7-10 Points per Category")
    print("="*60)
    print("\n💡 Запуск на http://localhost:8000\n")
    uvicorn.run("hr_agent:app", host="0.0.0.0", port=8000, reload=True)
