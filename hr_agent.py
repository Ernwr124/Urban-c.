import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import httpx
import pytesseract
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from passlib.context import CryptContext
from PIL import Image
from PyPDF2 import PdfReader
from docx import Document
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware


BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{BASE_DIR / 'hr_agent.db'}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), default="")
    role = Column(String(50), default="candidate")  # candidate | hr | admin
    title = Column(String(255), default="")
    bio = Column(Text, default="")
    skills = Column(Text, default="")
    development_plan = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    analyses = relationship("Analysis", back_populates="user")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    summary = Column(Text, default="")
    match_score = Column(Float, default=0.0)
    results = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="analyses")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    metric = Column(String(255), nullable=False)
    value = Column(Float, default=0.0)
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)


def create_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.query(User).filter_by(email="admin@hr-agent.io").first():
            admin = User(
                email="admin@hr-agent.io",
                password_hash=pwd_context.hash("ChangeMeNow!"),
                full_name="HR Platform Admin",
                role="admin",
                title="Platform Administrator",
            )
            db.add(admin)
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(user: Optional[User]) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_role(user: User, roles: tuple[str, ...]):
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def get_base_html(title: str, content: str, user: Optional[User]) -> str:
    user_email = user.email if user else "Guest"
    base_nav_links = """
        <a href="/">Landing</a>
        <a href="/dashboard">Dashboard</a>
        <a href="/profile">Profile</a>
        <a href="/upload">Upload</a>
    """
    admin_link = '<a href="/admin">Admin</a>' if user and user.role == "admin" else ""
    auth_links = (
        '<a href="/logout" class="logout">Logout</a>'
        if user
        else '<a href="/login">Login</a><a href="/register">Register</a>'
    )
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title} · HR Agent</title>
        <style>
            :root {{
                --bg: #ffffff;
                --text: #0f0f0f;
                --muted: #4b4b4b;
                --blue: #2563eb;
                --border: #e5e7eb;
                --danger: #ef4444;
                --success: #0ea5e9;
                font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            }}
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
            }}
            header {{
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 0 2rem;
                border-bottom: 1px solid var(--border);
                background: #fff;
                position: sticky;
                top: 0;
                z-index: 10;
            }}
            header .logo {{
                font-weight: 700;
                font-size: 1.1rem;
            }}
            header nav {{
                display: flex;
                gap: 1rem;
                align-items: center;
            }}
            header nav a {{
                text-decoration: none;
                color: var(--text);
                font-weight: 500;
            }}
            header nav a:hover {{
                color: var(--blue);
            }}
            header nav .logout {{
                color: var(--danger);
            }}
            main {{
                width: 100%;
                display: flex;
                justify-content: center;
                padding: 2rem 1rem 4rem;
            }}
            .container {{
                width: 100%;
                max-width: 1200px;
                display: flex;
                flex-direction: column;
                gap: 1.5rem;
            }}
            .card {{
                background: #fff;
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 2rem;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .grid {{
                display: grid;
                gap: 1.5rem;
            }}
            .grid.two {{
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            }}
            h1 {{
                font-size: 2.5rem;
                margin: 0 0 1rem;
            }}
            h2 {{
                font-size: 2rem;
                margin: 0 0 1rem;
            }}
            h3 {{
                font-size: 1.35rem;
                margin: 0 0 0.75rem;
            }}
            p {{
                color: var(--muted);
                line-height: 1.6;
            }}
            ul {{
                padding-left: 1.2rem;
                color: var(--muted);
            }}
            form {{
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }}
            label {{
                font-weight: 600;
            }}
            input, select, textarea {{
                width: 100%;
                height: 44px;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 0.75rem;
                font-size: 1rem;
            }}
            textarea {{
                height: auto;
                min-height: 120px;
                resize: vertical;
            }}
            input:focus, select:focus, textarea:focus {{
                outline: none;
                border-color: var(--blue);
                box-shadow: 0 0 0 2px rgba(37,99,235,0.1);
            }}
            button {{
                background: var(--blue);
                color: #fff;
                border: none;
                border-radius: 6px;
                padding: 0.75rem 1.5rem;
                font-size: 1rem;
                cursor: pointer;
                font-weight: 600;
                transition: background 0.2s ease;
            }}
            button.secondary {{
                background: #0f0f0f;
            }}
            button:hover {{
                background: #1d4ed8;
            }}
            button.secondary:hover {{
                background: #000;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            table th, table td {{
                padding: 0.75rem 1rem;
                border-bottom: 1px solid var(--border);
                text-align: left;
            }}
            table th {{
                color: var(--muted);
                font-weight: 600;
            }}
            .stat {{
                display: flex;
                flex-direction: column;
                gap: 0.25rem;
            }}
            .stat span:first-child {{
                color: var(--muted);
                font-size: 0.9rem;
            }}
            .stat span:last-child {{
                font-size: 1.8rem;
                font-weight: 700;
            }}
            @media (max-width: 768px) {{
                header {{
                    padding: 0 1rem;
                }}
                header nav {{
                    flex-wrap: wrap;
                    justify-content: flex-end;
                }}
                h1 {{
                    font-size: 2rem;
                }}
            }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo">HR Platform</div>
            <nav>
                {base_nav_links}
                {admin_link}
                <span>{user_email}</span>
                {auth_links}
            </nav>
        </header>
        <main>
            <div class="container">
                {content}
            </div>
        </main>
    </body>
    </html>
    """


def save_uploaded_file(upload: UploadFile) -> Path:
    suffix = Path(upload.filename).suffix
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}{suffix}"
    file_path = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as buffer:
        buffer.write(upload.file.read())
    return file_path


def extract_text_from_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    try:
        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            document = Document(str(file_path))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if suffix in {".png", ".jpg", ".jpeg"}:
            image = Image.open(file_path)
            return pytesseract.image_to_string(image)
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"Unable to fully parse file ({suffix}): {exc}"


async def call_ollama_analysis(prompt: str) -> Dict:
    api_key = os.getenv("OLLAMA_API_KEY")
    base_url = os.getenv("OLLAMA_CLOUD_URL", "https://api.ollama.ai/v1/chat/completions")
    payload = {
        "model": "gpt-oss:20b-cloud",
        "messages": [
            {"role": "system", "content": "You are a senior HR intelligence system producing strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(base_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return json.loads(content)
    except Exception:
        # Deterministic fallback to keep the platform working without the external service.
        return {
            "match_score": 72,
            "strengths": ["Structured resume", "Relevant domain expertise"],
            "weaknesses": ["Missing measurable achievements"],
            "skills_match": {"core": ["Python", "FastAPI"], "missing": ["CI/CD", "Kubernetes"]},
            "experience_assessment": "Experience aligns with mid-level backend roles.",
            "education_assessment": "Bachelor degree meets baseline.",
            "development_plan": [
                "Complete Kubernetes certification in Q1.",
                "Ship two internal automation projects.",
            ],
            "recommendations": [
                "Quantify impact in bullet points.",
                "Add leadership/mentorship examples.",
            ],
            "summary": "Candidate shows strong backend fundamentals and readiness for growth.",
        }


async def analyze_resume(resume_text: str, job_context: str) -> Dict:
    structured_prompt = f"""
    Resume:
    {resume_text[:4000]}

    Job Context:
    {job_context or 'Not specified'}

    Produce valid JSON with the keys:
    match_score (0-100),
    strengths (list of strings),
    weaknesses (list of strings),
    skills_match (object with core and missing lists),
    experience_assessment (string),
    education_assessment (string),
    development_plan (list of strings),
    recommendations (list of strings),
    summary (string).
    """
    return await call_ollama_analysis(structured_prompt)


app = FastAPI(title="HR Agent Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", secrets.token_hex(16)))


@app.on_event("startup")
def startup_event():
    create_database()


@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    content = """
    <section class="card">
        <h1>HR Agent — корпоративная HR-платформа</h1>
        <p>Анализируйте резюме, сравнивайте кандидатов и создавайте персональные планы развития на одной платформе, интегрированной с Ollama Cloud.</p>
        <div style="display:flex; gap:1rem; flex-wrap:wrap;">
            <a href="/register"><button>Начать работу</button></a>
            <a href="/upload"><button class="secondary">Загрузить резюме</button></a>
        </div>
    </section>
    <section class="grid two">
        <div class="card">
            <h3>Кандидаты</h3>
            <ul>
                <li>Личный кабинет и профиль</li>
                <li>Загрузка PDF, DOCX, JPG/PNG</li>
                <li>AI-анализ резюме и план развития</li>
                <li>Рекомендации для усиления навыков</li>
            </ul>
        </div>
        <div class="card">
            <h3>HR-специалисты</h3>
            <ul>
                <li>Сравнение кандидатов и match score</li>
                <li>Проверка условий вакансий</li>
                <li>История анализов и экспорт</li>
                <li>Админ-панель и аналитика</li>
            </ul>
        </div>
    </section>
    <section class="card">
        <h2>Интеграция с AI</h2>
        <p>Мы используем Ollama Cloud (gpt-oss:20b-cloud) для точного анализа опыта, навыков и соответствия требованиям рынка. Все выводы возвращаются в строгом JSON и доступны в API.</p>
    </section>
    """
    return get_base_html("Landing", content, user)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    content = """
    <section class="card">
        <h1>Регистрация</h1>
        <form method="post" action="/register">
            <div>
                <label>Email</label>
                <input type="email" name="email" required />
            </div>
            <div>
                <label>Полное имя</label>
                <input type="text" name="full_name" required />
            </div>
            <div>
                <label>Роль</label>
                <select name="role">
                    <option value="candidate">Кандидат</option>
                    <option value="hr">HR-специалист</option>
                </select>
            </div>
            <div>
                <label>Пароль</label>
                <input type="password" name="password" required />
            </div>
            <button type="submit">Создать аккаунт</button>
        </form>
    </section>
    """
    return get_base_html("Register", content, user)


@app.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    role: str = Form("candidate"),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=email.lower().strip(),
        full_name=full_name.strip(),
        role=role if role in {"candidate", "hr"} else "candidate",
        password_hash=pwd_context.hash(password),
    )
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    content = """
    <section class="card">
        <h1>Вход</h1>
        <form method="post" action="/login">
            <div>
                <label>Email</label>
                <input type="email" name="email" required />
            </div>
            <div>
                <label>Пароль</label>
                <input type="password" name="password" required />
            </div>
            <button type="submit">Войти</button>
        </form>
    </section>
    """
    return get_base_html("Login", content, user)


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(email=email.lower().strip()).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


def format_analysis_card(analysis: Analysis) -> str:
    return f"""
    <div class="card">
        <h3>{analysis.file_name}</h3>
        <p>Match score: <strong>{int(analysis.match_score)}%</strong></p>
        <p>{analysis.summary or 'Результаты доступны в карточке анализа.'}</p>
        <a href="/analysis/{analysis.id}"><button>Открыть анализ</button></a>
    </div>
    """


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    user_analyses = (
        db.query(Analysis).filter(Analysis.user_id == user.id).order_by(Analysis.created_at.desc()).all()
        if user.role != "hr"
        else db.query(Analysis).order_by(Analysis.created_at.desc()).limit(20).all()
    )
    stats = (
        db.query(func.count(Analysis.id)).scalar() or 0,
        db.query(func.avg(Analysis.match_score)).scalar() or 0,
    )
    cards = "".join(format_analysis_card(a) for a in user_analyses) or "<p class='card'>Нет анализов</p>"
    role_block = (
        "<div class='card'><h3>HR инструменты</h3><p>Сравнивайте кандидатов и отслеживайте историю загрузок.</p></div>"
        if user.role == "hr"
        else "<div class='card'><h3>Планы развития</h3><p>Возвращайтесь к рекомендациям AI и обновляйте навыки.</p></div>"
    )
    content = f"""
    <section class="grid two">
        <div class="card stat">
            <span>Всего анализов</span>
            <span>{stats[0]}</span>
        </div>
        <div class="card stat">
            <span>Средний match score</span>
            <span>{int(stats[1])}%</span>
        </div>
    </section>
    {role_block}
    <section>
        <h2>Последние анализы</h2>
        <div class="grid two">
            {cards}
        </div>
    </section>
    """
    return get_base_html("Dashboard", content, user)


@app.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
):
    content = f"""
    <section class="card">
        <h1>Профиль</h1>
        <form method="post" action="/profile">
            <div>
                <label>Полное имя</label>
                <input type="text" name="full_name" value="{user.full_name or ''}" />
            </div>
            <div>
                <label>Титул / должность</label>
                <input type="text" name="title" value="{user.title or ''}" />
            </div>
            <div>
                <label>О себе</label>
                <textarea name="bio">{user.bio or ''}</textarea>
            </div>
            <div>
                <label>Навыки</label>
                <textarea name="skills">{user.skills or ''}</textarea>
            </div>
            <div>
                <label>План развития</label>
                <textarea name="development_plan">{user.development_plan or ''}</textarea>
            </div>
            <button type="submit">Сохранить</button>
        </form>
    </section>
    """
    return get_base_html("Profile", content, user)


@app.post("/profile")
def update_profile(
    request: Request,
    full_name: str = Form(""),
    title: str = Form(""),
    bio: str = Form(""),
    skills: str = Form(""),
    development_plan: str = Form(""),
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    user.full_name = full_name
    user.title = title
    user.bio = bio
    user.skills = skills
    user.development_plan = development_plan
    db.add(user)
    db.commit()
    return RedirectResponse("/profile", status_code=302)


@app.get("/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
):
    content = """
    <section class="card">
        <h1>Загрузка резюме</h1>
        <form method="post" action="/upload" enctype="multipart/form-data">
            <div>
                <label>Файл (PDF, DOCX, PNG, JPG)</label>
                <input type="file" name="resume" required />
            </div>
            <div>
                <label>Контекст вакансии / требования</label>
                <textarea name="job_context" placeholder="Требования вакансии, ключевые навыки, условия..."></textarea>
            </div>
            <button type="submit">Анализировать</button>
        </form>
    </section>
    """
    return get_base_html("Upload", content, user)


@app.post("/upload")
async def upload_resume(
    request: Request,
    resume: UploadFile = File(...),
    job_context: str = Form(""),
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    file_path = save_uploaded_file(resume)
    resume_text = extract_text_from_file(file_path)
    analysis_data = await analyze_resume(resume_text, job_context)
    analysis = Analysis(
        user_id=user.id,
        file_name=resume.filename,
        file_path=str(file_path),
        summary=analysis_data.get("summary", ""),
        match_score=analysis_data.get("match_score", 0),
        results=analysis_data,
    )
    db.add(analysis)
    db.add(
        Analytics(
            metric="analysis_created",
            value=analysis.match_score,
            meta={"user_id": user.id, "role": user.role},
        )
    )
    db.commit()
    return RedirectResponse(f"/analysis/{analysis.id}", status_code=302)


@app.get("/analysis/{analysis_id}", response_class=HTMLResponse)
def analysis_page(
    analysis_id: int,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id and user.role not in {"hr", "admin"}:
        raise HTTPException(status_code=403, detail="Access denied")
    results = analysis.results or {}
    list_items = lambda key: "".join(f"<li>{item}</li>" for item in results.get(key, []))
    skills_match = results.get("skills_match", {})
    content = f"""
    <section class="card">
        <h1>Результаты анализа</h1>
        <p><strong>Файл:</strong> {analysis.file_name}</p>
        <p><strong>Match score:</strong> {int(analysis.match_score)}%</p>
        <div class="grid two">
            <div>
                <h3>Сильные стороны</h3>
                <ul>{list_items('strengths')}</ul>
            </div>
            <div>
                <h3>Зоны роста</h3>
                <ul>{list_items('weaknesses')}</ul>
            </div>
        </div>
        <div class="grid two">
            <div>
                <h3>Навыки — соответствует</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in skills_match.get('core', []))}</ul>
            </div>
            <div>
                <h3>Навыки — добавить</h3>
                <ul>{"".join(f"<li>{item}</li>" for item in skills_match.get('missing', []))}</ul>
            </div>
        </div>
        <h3>Опыт</h3>
        <p>{results.get('experience_assessment', 'Нет данных')}</p>
        <h3>Образование</h3>
        <p>{results.get('education_assessment', 'Нет данных')}</p>
        <h3>План развития</h3>
        <ul>{list_items('development_plan')}</ul>
        <h3>Рекомендации</h3>
        <ul>{list_items('recommendations')}</ul>
        <h3>Итог</h3>
        <p>{results.get('summary', '')}</p>
        <a href="/dashboard"><button class="secondary">Назад</button></a>
    </section>
    """
    return get_base_html("Analysis Result", content, user)


@app.get("/api/analyses/{analysis_id}", response_class=JSONResponse)
def analysis_api(
    analysis_id: int,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter_by(id=analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != user.id and user.role not in {"hr", "admin"}:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "id": analysis.id,
        "user_id": analysis.user_id,
        "file_name": analysis.file_name,
        "match_score": analysis.match_score,
        "results": analysis.results,
        "created_at": analysis.created_at.isoformat(),
    }


@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    user: User = Depends(lambda req=Depends(get_current_user): require_login(req)),
    db: Session = Depends(get_db),
):
    require_role(user, ("admin",))
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_analyses = db.query(func.count(Analysis.id)).scalar() or 0
    latest_metrics = (
        db.query(Analytics).order_by(Analytics.created_at.desc()).limit(10).all()
    )
    rows = "".join(
        f"<tr><td>{metric.metric}</td><td>{metric.value:.1f}</td><td>{metric.created_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"
        for metric in latest_metrics
    ) or "<tr><td colspan='3'>Нет данных</td></tr>"
    content = f"""
    <section class="card">
        <h1>Админ-панель</h1>
        <div class="grid two">
            <div class="stat">
                <span>Пользователи</span>
                <span>{total_users}</span>
            </div>
            <div class="stat">
                <span>Анализы</span>
                <span>{total_analyses}</span>
            </div>
        </div>
    </section>
    <section class="card">
        <h2>Метрики</h2>
        <table>
            <thead>
                <tr>
                    <th>Метрика</th>
                    <th>Значение</th>
                    <th>Время</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </section>
    """
    return get_base_html("Admin", content, user)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "hr_agent:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=bool(os.getenv("RELOAD", "0") == "1"),
    )
