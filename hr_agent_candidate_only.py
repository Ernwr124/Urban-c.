"""
HR Agent - AI-Powered Resume Analysis Platform
Version: Candidate Only (Russian)
Full LinkedIn-style profile, avatar upload, resume upload, advanced AI analysis
"""

import os
import io
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File, Form, Depends, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import httpx

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


# ==================== Configuration ====================
class Config:
    DATABASE_URL = "sqlite:///./hr_agent.db"
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    SESSION_LIFETIME_HOURS = 24
    OLLAMA_API_URL = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "gpt-oss:20b-cloud"
    MAX_FILE_SIZE = 10 * 1024 * 1024
    UPLOAD_DIR = Path("./uploads")
    
    @classmethod
    def init(cls):
        cls.UPLOAD_DIR.mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "avatars").mkdir(exist_ok=True)
        (cls.UPLOAD_DIR / "resumes").mkdir(exist_ok=True)


# ==================== Database Models ====================
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    
    # Profile fields (LinkedIn-style)
    headline = Column(String, default="")
    location = Column(String, default="")
    bio = Column(Text, default="")
    phone = Column(String, default="")
    
    # Avatar and resume
    avatar = Column(String, default="")
    resume_file = Column(String, default="")
    
    # Skills
    skills = Column(Text, default="")
    
    # Social links
    linkedin_url = Column(String, default="")
    github_url = Column(String, default="")
    website = Column(String, default="")
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)


class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    filename = Column(String)
    file_path = Column(String)
    job_description = Column(Text)
    match_score = Column(Float)
    analysis_data = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True)
    user_id = Column(Integer, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==================== Database Setup ====================
engine = create_engine(Config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== Helper Functions ====================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

def create_session_token() -> str:
    return secrets.token_urlsafe(32)

def parse_pdf(file_content: bytes) -> str:
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

def parse_docx_file(file_content: bytes) -> str:
    if not DOCX_SUPPORT:
        return "[DOCX parsing not available - install python-docx]"
    try:
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"[Error parsing DOCX: {str(e)}]"


# ==================== AI Analysis ====================
async def compare_resume_with_job(resume_text: str, job_description: str, candidate_skills: str = "") -> dict:
    """
    Advanced AI analysis with 7-10 points in each category
    """
    skills_section = f"\nНАВЫКИ КАНДИДАТА (указаны вручную):\n{candidate_skills}\n" if candidate_skills else ""
    
    prompt = f"""
ЗАДАЧА: Проведи МАКСИМАЛЬНО ДЕТАЛЬНЫЙ и ТОЧНЫЙ анализ соответствия резюме вакансии на русском языке.

РЕЗЮМЕ КАНДИДАТА:
{resume_text}
{skills_section}

ОПИСАНИЕ ВАКАНСИИ:
{job_description}

ТРЕБОВАНИЯ К АНАЛИЗУ:
1. Будь максимально детальным - давай 7-10 конкретных пунктов в каждой категории
2. Будь честным и конструктивным  
3. Указывай конкретные примеры из резюме
4. Давай практичные и реализуемые рекомендации
5. Анализируй не только наличие навыков, но и их глубину
6. Учитывай опыт работы, образование, проекты
7. Оценивай соответствие уровня позиции опыту кандидата

Верни ответ СТРОГО в формате JSON (без markdown, без комментариев):
{{
    "match_score": <число от 0 до 100>,
    "pros": [
        "Минимум 7-10 конкретных сильных сторон с примерами из резюме",
        "Каждый пункт должен быть детальным и специфичным",
        "Указывай конкретные технологии, проекты, достижения"
    ],
    "cons": [
        "Минимум 7-10 конкретных недостатков или областей для улучшения",
        "Будь конструктивным и давай пути решения",
        "Указывай что именно не хватает для идеального соответствия"
    ],
    "skills_match": {{
        "matched": ["список навыков которые есть у кандидата и требуются в вакансии"],
        "missing": ["список навыков которых не хватает кандидату для вакансии"]
    }},
    "experience_match": "Детальный анализ опыта работы (3-4 предложения). Опиши конкретные проекты и достижения, насколько они релевантны вакансии.",
    "education_match": "Анализ образования (2-3 предложения). Соответствует ли уровень образования требованиям позиции.",
    "recommendations": [
        "Минимум 7-10 конкретных практичных рекомендаций",
        "Каждая рекомендация должна быть реализуемой",
        "Указывай конкретные курсы, сертификации, проекты для развития"
    ],
    "summary": "Подробное итоговое резюме анализа (3-5 предложений). Дай честную оценку - стоит ли кандидату подавать заявку на эту позицию и почему."
}}

ВАЖНО: 
- Все тексты ТОЛЬКО на русском языке
- Будь максимально конкретным и давай реальные примеры
- Не используй общие фразы - только специфичные детали
- В каждой категории минимум 7 пунктов, оптимально 10
"""
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                Config.OLLAMA_API_URL,
                json={
                    "model": Config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis_text = result.get("response", "")
                
                # Extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    return analysis
    except Exception as e:
        print(f"AI Error: {e}")
    
    # Fallback response if AI fails
    return {
        "match_score": 0,
        "pros": ["AI-анализ временно недоступен. Убедитесь что Ollama запущен."],
        "cons": ["Не удалось выполнить анализ"],
        "skills_match": {"matched": [], "missing": []},
        "experience_match": "Анализ недоступен - проверьте подключение к Ollama",
        "education_match": "Анализ недоступен",
        "recommendations": [
            "Запустите Ollama: ollama serve",
            "Убедитесь что модель загружена: ollama pull gpt-oss:20b-cloud"
        ],
        "summary": "AI-анализ временно недоступен. Запустите Ollama и попробуйте снова."
    }


# ==================== Auth Dependency ====================
def require_auth(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> User:
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


# ==================== HTML Base Template ====================
def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    """Base HTML template with navigation"""
    
    nav_links = ""
    if user:
        avatar_url = f"/uploads/avatars/{user.avatar}" if user.avatar else ""
        avatar_html = f'<img src="{avatar_url}" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; margin-right: 8px;">' if user.avatar else "👤"
        
        nav_links = f"""
            <a href="/dashboard" class="nav-link">Панель</a>
            <a href="/analyze" class="nav-link">Анализ</a>
            <a href="/profile" class="nav-link" style="display: flex; align-items: center;">
                {avatar_html} {user.full_name}
            </a>
            <a href="/logout" class="nav-link">Выйти</a>
        """
    else:
        nav_links = """
            <a href="/login" class="nav-link">Войти</a>
            <a href="/register" class="btn">Начать</a>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - HR Agent</title>
        <style>
            :root {{
                --black: #000000;
                --white: #FFFFFF;
                --gray: #666666;
                --light-gray: rgba(255, 255, 255, 0.1);
                --border: rgba(255, 255, 255, 0.15);
                --success: #22c55e;
                --warning: #eab308;
                --danger: #ef4444;
                --blue: #3b82f6;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif;
                background: var(--black);
                color: var(--white);
                line-height: 1.6;
            }}
            
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
            
            nav {{
                background: rgba(255, 255, 255, 0.05);
                border-bottom: 1px solid var(--border);
                position: sticky;
                top: 0;
                z-index: 1000;
                backdrop-filter: blur(10px);
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
                font-size: 24px;
                font-weight: 700;
                color: var(--white);
                text-decoration: none;
                letter-spacing: -0.5px;
            }}
            
            .nav-links {{
                display: flex;
                gap: 24px;
                align-items: center;
            }}
            
            .nav-link {{
                color: var(--white);
                text-decoration: none;
                opacity: 0.8;
                transition: opacity 0.2s;
                font-weight: 500;
            }}
            
            .nav-link:hover {{
                opacity: 1;
            }}
            
            .btn {{
                padding: 12px 24px;
                background: var(--white);
                color: var(--black);
                border: none;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: all 0.2s;
                font-size: 14px;
            }}
            
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(255, 255, 255, 0.2);
            }}
            
            .btn-outline {{
                background: transparent;
                color: var(--white);
                border: 1px solid var(--white);
            }}
            
            .btn-outline:hover {{
                background: var(--white);
                color: var(--black);
            }}
            
            .btn-large {{
                padding: 16px 32px;
                font-size: 16px;
            }}
            
            .btn-danger {{
                background: var(--danger);
                color: var(--white);
            }}
            
            .card {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 32px;
                margin-bottom: 24px;
                transition: all 0.3s;
            }}
            
            .card:hover {{
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.2);
            }}
            
            .form-group {{
                margin-bottom: 24px;
            }}
            
            .form-label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                font-size: 14px;
            }}
            
            .form-control {{
                width: 100%;
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--white);
                font-size: 16px;
                transition: all 0.2s;
            }}
            
            .form-control:focus {{
                outline: none;
                border-color: var(--white);
                background: rgba(255, 255, 255, 0.15);
            }}
            
            textarea.form-control {{
                min-height: 120px;
                resize: vertical;
                font-family: inherit;
            }}
            
            .text-muted {{
                color: var(--gray);
            }}
            
            .text-xs {{
                font-size: 12px;
            }}
            
            .text-sm {{
                font-size: 14px;
            }}
            
            h1 {{
                font-size: 48px;
                margin-bottom: 16px;
                font-weight: 700;
                letter-spacing: -1px;
            }}
            
            h2 {{
                font-size: 36px;
                margin-bottom: 16px;
                font-weight: 700;
            }}
            
            h3 {{
                font-size: 24px;
                margin-bottom: 16px;
                font-weight: 600;
            }}
            
            .hero {{
                text-align: center;
                padding: 120px 32px;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 24px;
                margin-bottom: 48px;
            }}
            
            .stat-card {{
                background: rgba(255, 255, 255, 0.05);
                padding: 32px;
                border-radius: 12px;
                text-align: center;
                border: 1px solid var(--border);
            }}
            
            .stat-value {{
                font-size: 48px;
                font-weight: 700;
                margin-bottom: 8px;
            }}
            
            .stat-label {{
                color: var(--gray);
                font-size: 14px;
                font-weight: 500;
            }}
            
            .file-upload {{
                border: 2px dashed var(--border);
                border-radius: 12px;
                padding: 64px 32px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s;
            }}
            
            .file-upload:hover {{
                border-color: var(--white);
                background: rgba(255, 255, 255, 0.05);
            }}
            
            .file-icon {{
                font-size: 64px;
                margin-bottom: 16px;
            }}
            
            input[type="file"] {{
                display: none;
            }}
            
            .profile-header {{
                display: flex;
                gap: 32px;
                align-items: start;
                margin-bottom: 32px;
            }}
            
            .profile-avatar {{
                width: 150px;
                height: 150px;
                border-radius: 50%;
                object-fit: cover;
                border: 4px solid var(--white);
            }}
            
            .profile-info {{
                flex: 1;
            }}
            
            .social-links {{
                display: flex;
                gap: 16px;
                margin-top: 16px;
            }}
            
            .social-link {{
                color: var(--blue);
                text-decoration: none;
                font-size: 14px;
            }}
            
            .social-link:hover {{
                text-decoration: underline;
            }}
            
            .skills-list {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 16px;
            }}
            
            .skill-tag {{
                background: rgba(255, 255, 255, 0.1);
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 14px;
                border: 1px solid var(--border);
            }}
            
            .analysis-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 24px;
                margin-top: 32px;
            }}
            
            ul {{
                margin-left: 20px;
                margin-top: 12px;
            }}
            
            li {{
                margin-bottom: 8px;
                line-height: 1.6;
            }}
            
            @media (max-width: 768px) {{
                .profile-header {{
                    flex-direction: column;
                    text-align: center;
                }}
                
                .nav-links {{
                    flex-wrap: wrap;
                    gap: 12px;
                }}
                
                h1 {{
                    font-size: 36px;
                }}
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
    </html>
    """


# ==================== FastAPI App ====================
app = FastAPI(title="HR Agent", version="2.0.0")


@app.on_event("startup")
async def startup():
    Config.init()
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing():
    """Landing page"""
    content = """
    <div class="hero">
        <h1>HR Agent</h1>
        <p style="font-size: 24px; color: var(--gray); margin-bottom: 64px; max-width: 600px; margin-left: auto; margin-right: auto;">
            AI-платформа для анализа резюме и подбора идеальной вакансии
        </p>
        <a href="/register" class="btn btn-large">Начать анализ</a>
        <a href="/login" class="btn btn-outline btn-large" style="margin-left: 16px;">Войти</a>
    </div>
    """
    return get_base_html("Главная", content)


@app.get("/register", response_class=HTMLResponse)
async def register_page():
    """Registration page"""
    content = """
    <div class="container-sm">
        <h1>Регистрация</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Создайте аккаунт чтобы начать анализ резюме</p>
        
        <div class="card">
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Полное имя</label>
                    <input type="text" name="full_name" class="form-control" required placeholder="Иван Иванов">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required placeholder="ivan@example.com">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required placeholder="Минимум 6 символов">
                </div>
                
                <button type="submit" class="btn btn-large" style="width: 100%;">Создать аккаунт</button>
            </form>
        </div>
        
        <p class="text-muted text-sm" style="text-align: center; margin-top: 24px;">
            Уже есть аккаунт? <a href="/login" style="color: var(--white); text-decoration: none; font-weight: 600;">Войти</a>
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
    # Check if user exists
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    
    # Create user
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create session
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    # Set cookie and redirect
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
        <h1>Вход</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Войдите в свой аккаунт</p>
        
        <div class="card">
            <form method="POST" action="/login">
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                
                <button type="submit" class="btn btn-large" style="width: 100%;">Войти</button>
            </form>
        </div>
        
        <p class="text-muted text-sm" style="text-align: center; margin-top: 24px;">
            Нет аккаунта? <a href="/register" style="color: var(--white); text-decoration: none; font-weight: 600;">Зарегистрироваться</a>
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
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    # Create session
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    # Set cookie and redirect
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        key="session_token",
        value=session.session_token,
        httponly=True,
        max_age=Config.SESSION_LIFETIME_HOURS * 3600
    )
    return response


@app.get("/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    """Logout and delete session"""
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
    """Dashboard with analysis history"""
    # Get stats
    total_analyses = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    analyses = db.query(Analysis).filter(Analysis.user_id == user.id).order_by(Analysis.created_at.desc()).limit(10).all()
    
    # Calculate average score
    avg_score = 0
    if analyses:
        scores = [a.match_score for a in analyses if a.match_score]
        avg_score = sum(scores) / len(scores) if scores else 0
    
    # Build history HTML
    history_html = ""
    for analysis in analyses:
        score = int(analysis.match_score) if analysis.match_score else 0
        color = "var(--success)" if score >= 70 else "var(--warning)" if score >= 50 else "var(--danger)"
        
        history_html += f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="flex: 1;">
                    <h3 style="margin-bottom: 8px;">{analysis.filename}</h3>
                    <p class="text-muted text-sm">{analysis.created_at.strftime('%d.%m.%Y в %H:%M')}</p>
                    <p class="text-sm" style="margin-top: 8px; opacity: 0.8;">
                        {analysis.job_description[:150]}...
                    </p>
                </div>
                <div style="text-align: right; margin-left: 32px;">
                    <div style="font-size: 48px; font-weight: 700; color: {color}; margin-bottom: 8px;">
                        {score}%
                    </div>
                    <a href="/result/{analysis.id}" class="btn btn-outline">Посмотреть</a>
                </div>
            </div>
        </div>
        """
    
    if not history_html:
        history_html = """
        <div class="card" style="text-align: center; padding: 64px 32px;">
            <div style="font-size: 64px; margin-bottom: 16px;">📄</div>
            <h3>Анализов пока нет</h3>
            <p class="text-muted" style="margin-top: 8px;">Загрузите своё резюме и описание вакансии для начала</p>
            <a href="/analyze" class="btn btn-large" style="margin-top: 24px;">Начать анализ</a>
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
        
        <div style="margin-bottom: 48px;">
            <a href="/analyze" class="btn btn-large">Новый анализ</a>
            <a href="/profile" class="btn btn-outline btn-large" style="margin-left: 16px;">Мой профиль</a>
        </div>
        
        <h2 style="margin-bottom: 24px;">История анализов</h2>
        {history_html}
    </div>
    """
    return get_base_html("Панель", content, user)


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(user: User = Depends(require_auth)):
    """Resume analysis page"""
    content = """
    <div class="container-sm">
        <h1>Анализ резюме</h1>
        <p class="text-muted" style="margin-bottom: 32px;">
            Загрузите своё резюме и опишите вакансию мечты
        </p>
        
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <h3>Шаг 1: Загрузите резюме</h3>
                <div class="file-upload" onclick="document.getElementById('resume-input').click();" style="margin-top: 24px;">
                    <div class="file-icon">📄</div>
                    <input type="file" id="resume-input" name="resume" accept=".pdf,.docx" required>
                    <p style="font-weight: 600; margin-bottom: 8px;">Выберите файл резюме</p>
                    <p class="text-muted text-sm">PDF или DOCX, максимум 10MB</p>
                </div>
            </div>
            
            <div class="card">
                <h3>Шаг 2: Опишите вакансию</h3>
                <div class="form-group" style="margin-top: 24px; margin-bottom: 0;">
                    <label class="form-label">Полное описание вакансии</label>
                    <textarea 
                        name="job_description" 
                        class="form-control" 
                        required 
                        placeholder="Вставьте полное описание вакансии: требования, обязанности, квалификация..."
                        style="min-height: 200px;"
                    ></textarea>
                    <p class="text-muted text-xs" style="margin-top: 8px;">
                        Чем детальнее описание, тем точнее будет анализ
                    </p>
                </div>
            </div>
            
            <button type="submit" class="btn btn-large" style="width: 100%;">
                Запустить AI-анализ
            </button>
        </form>
    </div>
    
    <script>
        document.getElementById('resume-input').addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name || '';
            if (fileName) {
                const uploadDiv = document.querySelector('.file-upload');
                uploadDiv.innerHTML = '<div class="file-icon">✅</div><p style="font-weight: 600;">' + fileName + '</p><p class="text-muted text-sm">Файл загружен</p>';
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
    """Handle resume analysis"""
    # Read file
    content = await resume.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    
    # Parse resume
    if resume.filename.endswith('.pdf'):
        resume_text = parse_pdf(content)
    elif resume.filename.endswith('.docx'):
        resume_text = parse_docx_file(content)
    else:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")
    
    # AI Analysis
    analysis_result = await compare_resume_with_job(resume_text, job_description, user.skills)
    
    # Save to database
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
    """Display analysis results"""
    analysis = db.query(Analysis).filter(
        Analysis.id == analysis_id,
        Analysis.user_id == user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Анализ не найден")
    
    # Parse analysis data
    data = json.loads(analysis.analysis_data)
    score = int(data.get('match_score', 0))
    
    # Determine color based on score
    if score >= 70:
        color = "var(--success)"
        status = "Отличное соответствие"
    elif score >= 50:
        color = "var(--warning)"
        status = "Хорошее соответствие"
    else:
        color = "var(--danger)"
        status = "Требуется улучшение"
    
    # Build pros HTML
    pros_html = ""
    for pro in data.get('pros', []):
        pros_html += f"<li>{pro}</li>"
    
    # Build cons HTML
    cons_html = ""
    for con in data.get('cons', []):
        cons_html += f"<li>{con}</li>"
    
    # Build recommendations HTML
    recs_html = ""
    for rec in data.get('recommendations', []):
        recs_html += f"<li>{rec}</li>"
    
    # Skills match
    skills_match = data.get('skills_match', {})
    matched_skills = skills_match.get('matched', [])
    missing_skills = skills_match.get('missing', [])
    
    matched_html = ", ".join(matched_skills) if matched_skills else "Не указано"
    missing_html = ", ".join(missing_skills) if missing_skills else "Не указано"
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 32px;">
            <h1>Результат анализа</h1>
            <p class="text-muted">
                {analysis.filename} • {analysis.created_at.strftime('%d.%m.%Y в %H:%M')}
            </p>
        </div>
        
        <!-- Match Score -->
        <div class="card" style="text-align: center; background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.1));">
            <div style="font-size: 96px; font-weight: 700; color: {color}; margin: 24px 0; line-height: 1;">
                {score}%
            </div>
            <h2 style="margin-bottom: 8px;">{status}</h2>
            <p class="text-muted">Соответствие вакансии</p>
        </div>
        
        <!-- Pros and Cons Grid -->
        <div class="analysis-grid">
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
            <h3>Анализ навыков</h3>
            <div style="margin-top: 24px;">
                <p style="margin-bottom: 16px;">
                    <strong style="color: var(--success);">Есть у вас:</strong><br>
                    <span class="text-muted">{matched_html}</span>
                </p>
                <p>
                    <strong style="color: var(--danger);">Не хватает:</strong><br>
                    <span class="text-muted">{missing_html}</span>
                </p>
            </div>
        </div>
        
        <!-- Experience & Education -->
        <div class="analysis-grid">
            <div class="card">
                <h3>Анализ опыта работы</h3>
                <p class="text-muted" style="margin-top: 16px; line-height: 1.8;">
                    {data.get('experience_match', 'Нет данных')}
                </p>
            </div>
            
            <div class="card">
                <h3>Анализ образования</h3>
                <p class="text-muted" style="margin-top: 16px; line-height: 1.8;">
                    {data.get('education_match', 'Нет данных')}
                </p>
            </div>
        </div>
        
        <!-- Recommendations -->
        <div class="card">
            <h3 style="margin-bottom: 24px;">💡 Рекомендации для улучшения</h3>
            <ul>{recs_html}</ul>
        </div>
        
        <!-- Summary -->
        <div class="card" style="background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(59,130,246,0.05));">
            <h3 style="margin-bottom: 16px;">📋 Итоговое резюме</h3>
            <p style="line-height: 1.8; font-size: 16px;">
                {data.get('summary', 'Нет данных')}
            </p>
        </div>
        
        <!-- Actions -->
        <div style="display: flex; gap: 16px; margin-top: 32px;">
            <a href="/dashboard" class="btn btn-outline btn-large">Назад к панели</a>
            <a href="/analyze" class="btn btn-large">Новый анализ</a>
        </div>
    </div>
    """
    return get_base_html("Результат анализа", content, user)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(user: User = Depends(require_auth), db: Session = Depends(get_db)):
    """User profile page (LinkedIn-style)"""
    
    # Avatar
    avatar_html = ""
    if user.avatar:
        avatar_html = f'<img src="/uploads/avatars/{user.avatar}" class="profile-avatar" alt="{user.full_name}">'
    else:
        avatar_html = '<div class="profile-avatar" style="background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; font-size: 64px;">👤</div>'
    
    # Skills
    skills_html = ""
    if user.skills:
        skills_list = [s.strip() for s in user.skills.split(',') if s.strip()]
        for skill in skills_list:
            skills_html += f'<span class="skill-tag">{skill}</span>'
    else:
        skills_html = '<p class="text-muted">Навыки не указаны</p>'
    
    # Social links
    social_html = ""
    if user.linkedin_url:
        social_html += f'<a href="{user.linkedin_url}" target="_blank" class="social-link">🔗 LinkedIn</a>'
    if user.github_url:
        social_html += f'<a href="{user.github_url}" target="_blank" class="social-link">💻 GitHub</a>'
    if user.website:
        social_html += f'<a href="{user.website}" target="_blank" class="social-link">🌐 Сайт</a>'
    
    # Resume
    resume_html = ""
    if user.resume_file:
        resume_html = f'<a href="/uploads/resumes/{user.resume_file}" target="_blank" class="btn btn-outline">📄 Скачать резюме</a>'
    else:
        resume_html = '<p class="text-muted">Резюме не загружено</p>'
    
    content = f"""
    <div class="container">
        <h1 style="margin-bottom: 32px;">Профиль</h1>
        
        <div class="card">
            <div class="profile-header">
                {avatar_html}
                <div class="profile-info">
                    <h2 style="margin-bottom: 8px;">{user.full_name}</h2>
                    <p class="text-muted" style="font-size: 18px; margin-bottom: 8px;">
                        {user.headline or 'Добавьте заголовок профиля'}
                    </p>
                    <p class="text-muted text-sm">
                        📍 {user.location or 'Не указано'} • 📧 {user.email}
                    </p>
                    {f'<p class="text-muted text-sm">📱 {user.phone}</p>' if user.phone else ''}
                    <div class="social-links">
                        {social_html if social_html else '<p class="text-muted text-sm">Социальные сети не добавлены</p>'}
                    </div>
                </div>
            </div>
            
            <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border);">
                <h3>О себе</h3>
                <p class="text-muted" style="margin-top: 16px; line-height: 1.8;">
                    {user.bio or 'Расскажите о себе...'}
                </p>
            </div>
            
            <div style="margin-top: 32px;">
                <h3 style="margin-bottom: 16px;">Навыки</h3>
                <div class="skills-list">
                    {skills_html}
                </div>
            </div>
            
            <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border);">
                <h3 style="margin-bottom: 16px;">Резюме</h3>
                {resume_html}
            </div>
            
            <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border);">
                <a href="/profile/edit" class="btn btn-large">Редактировать профиль</a>
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
        avatar_preview = f'<img src="/uploads/avatars/{user.avatar}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; margin-bottom: 16px;">'
    
    content = f"""
    <div class="container-sm">
        <h1>Редактирование профиля</h1>
        <p class="text-muted" style="margin-bottom: 32px;">Заполните информацию о себе</p>
        
        <form method="POST" action="/profile/update" enctype="multipart/form-data">
            <!-- Avatar -->
            <div class="card">
                <h3>Фото профиля</h3>
                {avatar_preview}
                <div class="form-group">
                    <label class="form-label">Загрузить новое фото</label>
                    <input type="file" name="avatar" accept="image/*" class="form-control">
                    <p class="text-muted text-xs" style="margin-top: 8px;">PNG, JPG до 5MB</p>
                </div>
            </div>
            
            <!-- Basic Info -->
            <div class="card">
                <h3>Основная информация</h3>
                <div class="form-group">
                    <label class="form-label">Полное имя *</label>
                    <input type="text" name="full_name" class="form-control" value="{user.full_name}" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Заголовок профиля</label>
                    <input type="text" name="headline" class="form-control" value="{user.headline}" placeholder="Frontend Developer | React Specialist">
                    <p class="text-muted text-xs" style="margin-top: 8px;">Например: "Senior Python Developer" или "Data Scientist"</p>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Местоположение</label>
                    <input type="text" name="location" class="form-control" value="{user.location}" placeholder="Москва, Россия">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input type="tel" name="phone" class="form-control" value="{user.phone}" placeholder="+7 (999) 123-45-67">
                </div>
                
                <div class="form-group">
                    <label class="form-label">О себе</label>
                    <textarea name="bio" class="form-control" placeholder="Расскажите о себе, своём опыте и целях...">{user.bio}</textarea>
                </div>
            </div>
            
            <!-- Skills -->
            <div class="card">
                <h3>Навыки</h3>
                <div class="form-group">
                    <label class="form-label">Ваши навыки</label>
                    <textarea name="skills" class="form-control" placeholder="Python, JavaScript, React, Node.js, SQL...">{user.skills}</textarea>
                    <p class="text-muted text-xs" style="margin-top: 8px;">
                        Перечислите через запятую. Эти навыки будут учитываться при AI-анализе.
                    </p>
                </div>
            </div>
            
            <!-- Social Links -->
            <div class="card">
                <h3>Социальные сети и контакты</h3>
                <div class="form-group">
                    <label class="form-label">LinkedIn</label>
                    <input type="url" name="linkedin_url" class="form-control" value="{user.linkedin_url}" placeholder="https://linkedin.com/in/username">
                </div>
                
                <div class="form-group">
                    <label class="form-label">GitHub</label>
                    <input type="url" name="github_url" class="form-control" value="{user.github_url}" placeholder="https://github.com/username">
                </div>
                
                <div class="form-group">
                    <label class="form-label">Личный сайт</label>
                    <input type="url" name="website" class="form-control" value="{user.website}" placeholder="https://mywebsite.com">
                </div>
            </div>
            
            <!-- Resume Upload -->
            <div class="card">
                <h3>Резюме</h3>
                {f'<p class="text-muted text-sm" style="margin-bottom: 16px;">Текущее резюме: {user.resume_file}</p>' if user.resume_file else ''}
                <div class="form-group">
                    <label class="form-label">Загрузить резюме</label>
                    <input type="file" name="resume" accept=".pdf,.docx" class="form-control">
                    <p class="text-muted text-xs" style="margin-top: 8px;">PDF или DOCX до 10MB</p>
                </div>
            </div>
            
            <!-- Submit -->
            <button type="submit" class="btn btn-large" style="width: 100%;">Сохранить изменения</button>
            <a href="/profile" class="btn btn-outline btn-large" style="width: 100%; margin-top: 16px;">Отмена</a>
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
    """Update user profile"""
    
    # Update basic fields
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
        if len(avatar_content) <= 5 * 1024 * 1024:  # 5MB limit
            ext = avatar.filename.split('.')[-1]
            filename = f"{user.id}_{secrets.token_urlsafe(8)}.{ext}"
            filepath = Config.UPLOAD_DIR / "avatars" / filename
            
            with open(filepath, 'wb') as f:
                f.write(avatar_content)
            
            user.avatar = filename
    
    # Handle resume upload
    if resume and resume.filename:
        resume_content = await resume.read()
        if len(resume_content) <= Config.MAX_FILE_SIZE:
            ext = resume.filename.split('.')[-1]
            filename = f"{user.id}_resume_{secrets.token_urlsafe(8)}.{ext}"
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
    print("\n" + "="*50)
    print("🚀 HR Agent - Candidate Only Version")
    print("="*50)
    print("✅ Full LinkedIn-style profile")
    print("✅ Avatar & Resume upload")
    print("✅ Advanced AI analysis (7-10 points)")
    print("✅ Russian language only")
    print("="*50 + "\n")
    uvicorn.run("hr_agent_candidate_only:app", host="0.0.0.0", port=8000, reload=True)
