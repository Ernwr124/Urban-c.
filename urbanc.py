"""
UrbanC - AI-Powered Resume Analyzer
Simple resume analysis platform for candidates (Russian only)
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


# Configuration
class Config:
    DATABASE_URL = "sqlite:///./urbanc.db"
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


# Database Models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    headline = Column(String, default="")
    location = Column(String, default="")
    bio = Column(Text, default="")
    phone = Column(String, default="")
    avatar = Column(String, default="")
    resume_file = Column(String, default="")
    skills = Column(Text, default="")
    linkedin_url = Column(String, default="")
    github_url = Column(String, default="")
    website = Column(String, default="")
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


# Database setup
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


# Helper functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

def create_session_token() -> str:
    return secrets.token_urlsafe(32)

def parse_pdf(file_content: bytes) -> str:
    if not PDF_SUPPORT:
        return "[PDF parsing not available]"
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except:
        return "[Error parsing PDF]"

def parse_docx_file(file_content: bytes) -> str:
    if not DOCX_SUPPORT:
        return "[DOCX parsing not available]"
    try:
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except:
        return "[Error parsing DOCX]"


# AI Analysis
async def compare_resume_with_job(resume_text: str, job_description: str, candidate_skills: str = "") -> dict:
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

Верни ответ СТРОГО в формате JSON (без markdown, без комментариев):
{{
    "match_score": <число от 0 до 100>,
    "pros": [
        "7-10 конкретных сильных сторон с примерами из резюме"
    ],
    "cons": [
        "7-10 конкретных недостатков или областей для улучшения"
    ],
    "skills_match": {{
        "matched": ["навыки которые есть"],
        "missing": ["навыки которых не хватает"]
    }},
    "experience_match": "детальный анализ опыта работы (3-4 предложения)",
    "education_match": "анализ образования (2-3 предложения)",
    "recommendations": [
        "7-10 конкретных практичных рекомендаций"
    ],
    "summary": "подробное итоговое резюме анализа (3-5 предложений)"
}}

ВАЖНО: Все тексты должны быть на русском языке. Будь конкретным и давай примеры!
"""
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                Config.OLLAMA_API_URL,
                json={"model": Config.OLLAMA_MODEL, "prompt": prompt, "stream": False}
            )
            
            if response.status_code == 200:
                result = response.json()
                analysis_text = result.get("response", "")
                
                import re
                json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    return analysis
    except:
        pass
    
    return {
        "match_score": 0,
        "pros": ["AI недоступен. Проверьте подключение к Ollama."],
        "cons": ["Не удалось выполнить анализ"],
        "skills_match": {"matched": [], "missing": []},
        "experience_match": "Анализ недоступен",
        "education_match": "Анализ недоступен",
        "recommendations": ["Убедитесь что Ollama запущен: ollama serve"],
        "summary": "AI-анализ временно недоступен. Запустите Ollama и попробуйте снова."
    }


# Auth dependency
def require_auth(session_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = db.query(Session).filter(Session.session_token == session_token).first()
    if not session or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user


# HTML Base
def get_base_html(title: str, content: str, user: Optional[User] = None) -> str:
    nav_links = ""
    if user:
        nav_links = f"""
            <a href="/dashboard" class="nav-link">Панель</a>
            <a href="/analyze" class="nav-link">Анализ</a>
            <a href="/profile" class="nav-link">{user.full_name}</a>
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
        <title>{title} - UrbanC</title>
        <style>
            :root {{
                --black: #000000;
                --white: #FFFFFF;
                --gray: #666666;
                --light-gray: rgba(255, 255, 255, 0.1);
                --success: #22c55e;
                --warning: #eab308;
                --danger: #ef4444;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--black); color: var(--white); line-height: 1.6; }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 64px 32px; }}
            .container-sm {{ max-width: 800px; margin: 0 auto; padding: 64px 32px; }}
            nav {{ background: rgba(255, 255, 255, 0.05); border-bottom: 1px solid var(--light-gray); }}
            .nav-container {{ max-width: 1200px; margin: 0 auto; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }}
            .logo {{ font-size: 24px; font-weight: 700; color: var(--white); text-decoration: none; }}
            .nav-links {{ display: flex; gap: 24px; align-items: center; }}
            .nav-link {{ color: var(--white); text-decoration: none; opacity: 0.8; transition: opacity 0.2s; }}
            .nav-link:hover {{ opacity: 1; }}
            .btn {{ padding: 12px 24px; background: var(--white); color: var(--black); border: none; border-radius: 6px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.2s; }}
            .btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(255,255,255,0.2); }}
            .btn-outline {{ background: transparent; color: var(--white); border: 1px solid var(--white); }}
            .btn-large {{ padding: 16px 32px; font-size: 18px; }}
            .card {{ background: rgba(255, 255, 255, 0.05); border: 1px solid var(--light-gray); border-radius: 12px; padding: 32px; margin-bottom: 24px; }}
            .form-group {{ margin-bottom: 24px; }}
            .form-label {{ display: block; margin-bottom: 8px; font-weight: 600; }}
            .form-control {{ width: 100%; padding: 12px 16px; background: rgba(255, 255, 255, 0.1); border: 1px solid var(--light-gray); border-radius: 6px; color: var(--white); font-size: 16px; }}
            .form-control:focus {{ outline: none; border-color: var(--white); }}
            textarea.form-control {{ min-height: 150px; resize: vertical; }}
            .text-muted {{ color: var(--gray); }}
            .text-xs {{ font-size: 12px; }}
            .text-sm {{ font-size: 14px; }}
            h1 {{ font-size: 48px; margin-bottom: 16px; }}
            h2 {{ font-size: 36px; margin-bottom: 16px; }}
            h3 {{ font-size: 24px; margin-bottom: 16px; }}
            .hero {{ text-align: center; padding: 80px 32px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px; margin-bottom: 32px; }}
            .stat-card {{ background: rgba(255, 255, 255, 0.05); padding: 24px; border-radius: 12px; text-align: center; }}
            .stat-value {{ font-size: 36px; font-weight: 700; margin-bottom: 8px; }}
            .stat-label {{ color: var(--gray); font-size: 14px; }}
            .file-upload {{ border: 2px dashed var(--light-gray); border-radius: 12px; padding: 48px; text-align: center; cursor: pointer; transition: all 0.3s; }}
            .file-upload:hover {{ border-color: var(--white); background: rgba(255, 255, 255, 0.05); }}
            .file-icon {{ font-size: 64px; margin-bottom: 16px; }}
            input[type="file"] {{ display: none; }}
        </style>
    </head>
    <body>
        <nav>
            <div class="nav-container">
                <a href="/" class="logo">UrbanC</a>
                <div class="nav-links">{nav_links}</div>
            </div>
        </nav>
        <main>{content}</main>
    </body>
    </html>
    """


# FastAPI App
app = FastAPI(title="UrbanC", version="1.0.0")

@app.on_event("startup")
async def startup():
    Config.init()
    init_db()

@app.get("/", response_class=HTMLResponse)
async def landing():
    content = """
    <div class="hero">
        <h1>UrbanC</h1>
        <p style="font-size: 20px; color: var(--gray); margin-bottom: 48px;">AI-анализ вашего резюме</p>
        <a href="/register" class="btn btn-large">Начать анализ</a>
    </div>
    """
    return get_base_html("Главная", content)

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    content = """
    <div class="container-sm">
        <h1>Регистрация</h1>
        <div class="card">
            <form method="POST" action="/register">
                <div class="form-group">
                    <label class="form-label">Полное имя</label>
                    <input type="text" name="full_name" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Email</label>
                    <input type="email" name="email" class="form-control" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Пароль</label>
                    <input type="password" name="password" class="form-control" required>
                </div>
                <button type="submit" class="btn btn-large" style="width: 100%;">Создать аккаунт</button>
            </form>
        </div>
        <p class="text-muted text-sm" style="text-align: center;">
            Уже есть аккаунт? <a href="/login" style="color: var(--white);">Войти</a>
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
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    db.commit()
    
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session_token", session.session_token, httponly=True, max_age=Config.SESSION_LIFETIME_HOURS * 3600)
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    content = """
    <div class="container-sm">
        <h1>Вход</h1>
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
    </div>
    """
    return get_base_html("Вход", content)

@app.post("/login")
async def login_post(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    session = Session(
        session_token=create_session_token(),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(hours=Config.SESSION_LIFETIME_HOURS)
    )
    db.add(session)
    db.commit()
    
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session_token", session.session_token, httponly=True, max_age=Config.SESSION_LIFETIME_HOURS * 3600)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session_token")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: User = Depends(require_auth), db: Session = Depends(get_db)):
    total = db.query(Analysis).filter(Analysis.user_id == user.id).count()
    analyses = db.query(Analysis).filter(Analysis.user_id == user.id).order_by(Analysis.created_at.desc()).limit(5).all()
    
    history_html = ""
    for a in analyses:
        color = "var(--success)" if a.match_score >= 70 else "var(--warning)" if a.match_score >= 50 else "var(--danger)"
        history_html += f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3>{a.filename}</h3>
                    <p class="text-muted text-sm">{a.created_at.strftime('%d.%m.%Y %H:%M')}</p>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 32px; font-weight: 700; color: {color};">{int(a.match_score)}%</div>
                    <a href="/result/{a.id}" class="btn btn-outline">Посмотреть</a>
                </div>
            </div>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div style="margin-bottom: 48px;">
            <h1>Панель управления</h1>
            <p class="text-muted">Добро пожаловать, {user.full_name}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total}</div>
                <div class="stat-label">Всего анализов</div>
            </div>
        </div>
        
        <div style="margin-bottom: 32px;">
            <a href="/analyze" class="btn btn-large">Новый анализ</a>
            <a href="/profile" class="btn btn-outline btn-large" style="margin-left: 16px;">Профиль</a>
        </div>
        
        <h2>Последние анализы</h2>
        {history_html if history_html else '<div class="card"><p class="text-muted">Анализов пока нет</p></div>'}
    </div>
    """
    return get_base_html("Панель", content, user)

@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(user: User = Depends(require_auth)):
    content = """
    <div class="container-sm">
        <h1>Анализ резюме</h1>
        <form method="POST" action="/analyze" enctype="multipart/form-data">
            <div class="card">
                <div class="file-upload" onclick="document.getElementById('resume-input').click();">
                    <div class="file-icon">📄</div>
                    <input type="file" id="resume-input" name="resume" accept=".pdf,.docx" required>
                    <p style="font-weight: 600; margin-bottom: 8px;">Выберите резюме</p>
                    <p class="text-muted text-sm">PDF или DOCX, макс 10MB</p>
                </div>
            </div>
            <div class="card">
                <div class="form-group">
                    <label class="form-label">Описание вакансии</label>
                    <textarea name="job_description" class="form-control" required placeholder="Вставьте полное описание вакансии..."></textarea>
                </div>
            </div>
            <button type="submit" class="btn btn-large" style="width: 100%;">Анализировать</button>
        </form>
    </div>
    """
    return get_base_html("Анализ", content, user)

@app.post("/analyze")
async def analyze_post(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    content = await resume.read()
    if len(content) > Config.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    resume_text = parse_pdf(content) if resume.filename.endswith('.pdf') else parse_docx_file(content)
    
    analysis = await compare_resume_with_job(resume_text, job_description, user.skills)
    
    analysis_record = Analysis(
        user_id=user.id,
        filename=resume.filename,
        file_path="",
        job_description=job_description,
        match_score=analysis.get('match_score', 0),
        analysis_data=json.dumps(analysis, ensure_ascii=False)
    )
    db.add(analysis_record)
    db.commit()
    
    return RedirectResponse(f"/result/{analysis_record.id}", status_code=303)

@app.get("/result/{analysis_id}", response_class=HTMLResponse)
async def result_page(analysis_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id, Analysis.user_id == user.id).first()
    if not analysis:
        raise HTTPException(status_code=404)
    
    data = json.loads(analysis.analysis_data)
    score = int(data.get('match_score', 0))
    color = "var(--success)" if score >= 70 else "var(--warning)" if score >= 50 else "var(--danger)"
    
    pros_html = "".join([f"<li>{p}</li>" for p in data.get('pros', [])])
    cons_html = "".join([f"<li>{c}</li>" for c in data.get('cons', [])])
    recs_html = "".join([f"<li>{r}</li>" for r in data.get('recommendations', [])])
    
    skills_match = data.get('skills_match', {})
    matched_html = ", ".join(skills_match.get('matched', [])) or "Не указано"
    missing_html = ", ".join(skills_match.get('missing', [])) or "Не указано"
    
    content = f"""
    <div class="container">
        <h1>Результат анализа</h1>
        <p class="text-muted">{analysis.filename} • {analysis.created_at.strftime('%d.%m.%Y %H:%M')}</p>
        
        <div class="card" style="text-align: center;">
            <div style="font-size: 96px; font-weight: 700; color: {color}; margin: 24px 0;">{score}%</div>
            <p class="text-muted">Соответствие вакансии</p>
        </div>
        
        <div class="card">
            <h3 style="color: var(--success);">✓ Сильные стороны</h3>
            <ul style="margin-left: 20px; margin-top: 16px;">{pros_html}</ul>
        </div>
        
        <div class="card">
            <h3 style="color: var(--danger);">✗ Слабые стороны</h3>
            <ul style="margin-left: 20px; margin-top: 16px;">{cons_html}</ul>
        </div>
        
        <div class="card">
            <h3>Навыки</h3>
            <p style="margin-top: 16px;"><strong>Есть:</strong> {matched_html}</p>
            <p style="margin-top: 8px;"><strong>Не хватает:</strong> {missing_html}</p>
        </div>
        
        <div class="card">
            <h3>Анализ опыта</h3>
            <p style="margin-top: 16px;">{data.get('experience_match', '')}</p>
        </div>
        
        <div class="card">
            <h3>Образование</h3>
            <p style="margin-top: 16px;">{data.get('education_match', '')}</p>
        </div>
        
        <div class="card">
            <h3>💡 Рекомендации</h3>
            <ul style="margin-left: 20px; margin-top: 16px;">{recs_html}</ul>
        </div>
        
        <div class="card">
            <h3>Итог</h3>
            <p style="margin-top: 16px;">{data.get('summary', '')}</p>
        </div>
        
        <a href="/dashboard" class="btn btn-outline">Назад к панели</a>
    </div>
    """
    return get_base_html("Результат анализа", content, user)

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(user: User = Depends(require_auth)):
    content = f"""
    <div class="container-sm">
        <h1>Профиль</h1>
        <div class="card">
            <h3>{user.full_name}</h3>
            <p class="text-muted">{user.email}</p>
            <p class="text-muted" style="margin-top: 8px;">Навыки: {user.skills or 'Не указано'}</p>
            <a href="/profile/edit" class="btn" style="margin-top: 16px;">Редактировать</a>
        </div>
    </div>
    """
    return get_base_html("Профиль", content, user)

@app.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_page(user: User = Depends(require_auth)):
    content = f"""
    <div class="container-sm">
        <h1>Редактировать профиль</h1>
        <form method="POST" action="/profile/edit">
            <div class="card">
                <div class="form-group">
                    <label class="form-label">Имя</label>
                    <input type="text" name="full_name" class="form-control" value="{user.full_name}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Навыки</label>
                    <textarea name="skills" class="form-control" placeholder="Python, JavaScript, React...">{user.skills}</textarea>
                    <p class="text-muted text-xs" style="margin-top: 8px;">Эти навыки будут использоваться при анализе</p>
                </div>
                <button type="submit" class="btn btn-large">Сохранить</button>
            </div>
        </form>
    </div>
    """
    return get_base_html("Редактирование", content, user)

@app.post("/profile/edit")
async def edit_profile_post(
    full_name: str = Form(...),
    skills: str = Form(""),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    user.full_name = full_name
    user.skills = skills
    db.commit()
    return RedirectResponse("/profile", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("urbanc:app", host="0.0.0.0", port=8000, reload=True)
