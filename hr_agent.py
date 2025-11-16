"""
HR Agent — single-file FastAPI приложение

Возможности текущего этапа:
1. Лендинг в корпоративных цветах (чёрный/белый + акцент #2563eb)
2. Регистрация / вход
3. Кабинет кандидата:
   - Загрузка резюме (PDF/DOCX/PNG/JPG)
   - Анализ резюме vs описания вакансии
   - Подтягивание контекста вакансий через DuckDuckGo
   - Использование Ollama Cloud (gpt-oss:20b-cloud) для точного JSON-анализа
   - История анализов + выгрузка JSON/DOCX/XLSX
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from duckduckgo_search import DDGS
from docx import Document
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from starlette.middleware.sessions import SessionMiddleware

try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:  # pragma: no cover
    pdf_extract_text = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


# --- БАЗА ДАННЫХ ----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "hr_agent.db"
PASSWORD_SALT = os.getenv("HR_AGENT_PASSWORD_SALT", "hr-agent-salt")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resume_excerpt TEXT NOT NULL,
            vacancy_description TEXT NOT NULL,
            result_json TEXT NOT NULL,
            sources_json TEXT,
            engine TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


# --- СЕРВИСНЫЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------------------------------------

def hash_password(password: str) -> str:
    import hashlib

    return hashlib.sha256(f"{PASSWORD_SALT}:{password}".encode("utf-8")).hexdigest()


def increment_counter(key: str, amount: int = 1) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO analytics (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = value + ?
        """,
        (key, amount, amount),
    )
    conn.commit()
    conn.close()


def get_counter(key: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM analytics WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def create_user(name: str, email: str, password: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ?", (normalized_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Пользователь уже зарегистрирован.")
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (name.strip(), normalized_email, hash_password(password), datetime.utcnow().isoformat()),
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    increment_counter("registrations")
    return int(user_id)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(int(user_id))


# --- ПАРСИНГ ФАЙЛОВ ------------------------------------------------------------

async def read_upload(upload: UploadFile | None) -> str:
    if upload is None:
        return ""
    data = await upload.read()
    if not data:
        return ""
    filename = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    if filename.endswith(".pdf") or "pdf" in content_type:
        return extract_pdf(data)
    if filename.endswith(".docx") or "wordprocessingml" in content_type:
        return extract_docx(data)
    if filename.endswith((".png", ".jpg", ".jpeg")) or "image" in content_type:
        return extract_image(data)
    return data.decode("utf-8", errors="ignore")


def extract_pdf(data: bytes) -> str:
    if pdf_extract_text is None:
        return ""
    try:
        return pdf_extract_text(io.BytesIO(data)).strip()
    except Exception:
        return ""


def extract_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()
    except Exception:
        return ""


def extract_image(data: bytes) -> str:
    if pytesseract is None or Image is None:
        return ""
    try:
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image, lang="eng+rus").strip()
    except Exception:
        return ""


# --- КОНТЕКСТ ВАКАНСИЙ ---------------------------------------------------------

def ddg_sources(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            cleaned = []
            for item in results:
                href = item.get("href", "")
                if not href or href.lower().endswith(".pdf"):
                    continue
                cleaned.append(
                    {
                        "title": item.get("title", "Vacancy"),
                        "href": href,
                        "snippet": item.get("body", "")[:280],
                    }
                )
            return cleaned
    except Exception:
        return []


# --- АНАЛИТИКА (LLM / эвристика) -----------------------------------------------

def should_use_ollama() -> bool:
    return os.getenv("HR_AGENT_USE_OLLAMA", "").lower() in {"1", "true", "yes"}


def run_llm_analysis(resume_text: str, vacancy_text: str, context: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not should_use_ollama():
        return None
    context_block = "\n".join(f"- {c['title']}: {c['snippet']}" for c in context[:5])
    prompt = (
        "You are a senior HR analyst. Compare resume vs job description with external context.\n"
        "Return STRICT JSON with keys:\n"
        "{\n"
        '  "match_score": int 0-100,\n'
        '  "strengths": ["..."],\n'
        '  "weaknesses": ["..."],\n'
        '  "skills_match": ["skill: assessment"],\n'
        '  "experience_assessment": "text",\n'
        '  "education_assessment": "text",\n'
        '  "development_plan": ["step"...],\n'
        '  "recommendations": ["..."],\n'
        '  "summary": "text"\n'
        "}\n"
        "Resume:\n"
        f"{resume_text}\n\n"
        "Vacancy:\n"
        f"{vacancy_text}\n\n"
        "Additional context:\n"
        f"{context_block or 'none'}\n"
        "Return JSON only."
    )
    try:
        result = subprocess.run(
            ["ollama", "run", "gpt-oss:20b-cloud"],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        raw = (result.stdout or "").strip()
        parsed = json.loads(raw if raw.startswith("{") else raw[raw.find("{") : raw.rfind("}") + 1])
        parsed["match_score"] = max(0, min(100, int(parsed.get("match_score", 0))))
        parsed["engine"] = "llm"
        return parsed
    except Exception:
        return None


def heuristic_analysis(resume_text: str, vacancy_text: str) -> Dict[str, Any]:
    resume_tokens = {token.lower() for token in resume_text.split() if len(token) > 3}
    vacancy_tokens = {token.lower() for token in vacancy_text.split() if len(token) > 3}
    overlap = sorted(vacancy_tokens & resume_tokens)
    missing = sorted(vacancy_tokens - resume_tokens)
    score = int((len(overlap) / max(1, len(vacancy_tokens))) * 100)
    score = max(10, min(90, score))
    return {
        "match_score": score,
        "strengths": [f"Упоминается «{token}»" for token in overlap[:5]] or ["В резюме есть часть ключевых слов."],
        "weaknesses": [f"Нет подтверждения навыка «{token}»" for token in missing[:5]] or ["Добавьте конкретные результаты."],
        "skills_match": [f"{token}: strong fit" for token in overlap[:5]],
        "experience_assessment": "Опыт частично совпадает с требованиями.",
        "education_assessment": "Рекомендуется детализировать образование.",
        "development_plan": ["Расширить описание проектов", "Добавить метрики успеха"],
        "recommendations": ["Обновить резюме под вакансию", "Уточнить ключевые компетенции"],
        "summary": "Рекомендуется усилить резюме для повышения совпадения.",
        "engine": "heuristic",
    }


def store_analysis(user_id: int, resume_excerpt: str, vacancy: str, result: Dict[str, Any], sources: List[Dict[str, str]]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO analyses (user_id, resume_excerpt, vacancy_description, result_json, sources_json, engine, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            resume_excerpt[:1200],
            vacancy[:1200],
            json.dumps(result, ensure_ascii=False),
            json.dumps(sources, ensure_ascii=False),
            result["engine"],
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    analysis_id = cursor.lastrowid
    conn.close()
    increment_counter("analyses")
    if result["engine"] == "llm":
        increment_counter("llm_analyses")
    return int(analysis_id)


def list_analyses(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id,
               json_extract(result_json, '$.match_score') AS match_score,
               engine,
               created_at
        FROM analyses
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": row["id"], "match_score": int(row["match_score"] or 0), "engine": row["engine"], "created_at": row["created_at"]}
        for row in rows
    ]


def fetch_analysis(user_id: int, analysis_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, user_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    record = dict(row)
    record["result_json"] = json.loads(record["result_json"])
    record["sources_json"] = json.loads(record.get("sources_json") or "[]")
    return record


def analysis_to_docx(payload: Dict[str, Any]) -> bytes:
    doc = Document()
    doc.add_heading("HR Agent — отчёт анализа", level=1)
    doc.add_paragraph(f"Дата: {payload.get('created_at')}")
    doc.add_paragraph(f"Совпадение: {payload.get('match_score')}% ({payload.get('engine')})")
    doc.add_heading("Сильные стороны", level=2)
    for item in payload.get("strengths", []):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Зоны роста", level=2)
    for item in payload.get("weaknesses", []):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Навыки", level=2)
    doc.add_paragraph(", ".join(payload.get("skills_match", [])))
    doc.add_heading("План развития", level=2)
    for step in payload.get("development_plan", []):
        doc.add_paragraph(step, style="List Bullet")
    doc.add_heading("Рекомендации", level=2)
    for rec in payload.get("recommendations", []):
        doc.add_paragraph(rec, style="List Bullet")
    doc.add_paragraph(f"Сводка: {payload.get('summary','')}")
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def analysis_to_xlsx(payload: Dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Analysis"
    ws.append(["Поле", "Значение"])
    ws.append(["Дата", payload.get("created_at")])
    ws.append(["Совпадение", f"{payload.get('match_score')}% ({payload.get('engine')})"])
    ws.append(["Сильные стороны", "; ".join(payload.get("strengths", []))])
    ws.append(["Зоны роста", "; ".join(payload.get("weaknesses", []))])
    ws.append(["Навыки", "; ".join(payload.get("skills_match", []))])
    ws.append(["План развития", "; ".join(payload.get("development_plan", []))])
    ws.append(["Рекомендации", "; ".join(payload.get("recommendations", []))])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


# --- HTML ШАБЛОНЫ --------------------------------------------------------------

LANDING_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HR Agent</title>
    <style>
        :root {{ --black:#0f0f0f; --white:#ffffff; --accent:#2563eb; --gray:#1f1f1f; }}
        * {{ box-sizing: border-box; }}
        body {{ margin:0; background:var(--black); color:var(--white); font-family:'Inter',system-ui,sans-serif; }}
        .page {{ max-width:1200px; margin:0 auto; padding:40px 20px 80px; }}
        .top-nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:30px; }}
        .btn {{ border:1px solid rgba(255,255,255,0.2); color:var(--white); padding:10px 18px; border-radius:999px; text-decoration:none; margin-left:8px; }}
        .btn.primary {{ background:var(--accent); border-color:var(--accent); }}
        section {{ background:var(--gray); padding:32px; border-radius:24px; border:1px solid rgba(255,255,255,0.12); margin-bottom:24px; }}
        h1 {{ font-size:clamp(2rem,4vw,3.5rem); margin-bottom:14px; }}
        p {{ color:rgba(255,255,255,0.75); line-height:1.6; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:18px; }}
        .card {{ background:#121212; border:1px solid rgba(255,255,255,0.08); padding:18px; border-radius:18px; }}
    </style>
</head>
<body>
    <div class="page">
        <nav class="top-nav">
            <div style="letter-spacing:0.08em;font-weight:600;">HR AGENT</div>
            <div>
                {auth_block}
            </div>
        </nav>
        <section>
            <h1>Анализ резюме против вакансии</h1>
            <p>Загружайте PDF/DOCX/PNG/JPG, подключайте Ollama Cloud и получайте честный match score, план развития и рекомендации.</p>
            <div style="margin-top:20px;">
                <a class="btn primary" href="/register">Начать бесплатно</a>
                <a class="btn" href="#features">Подробнее</a>
            </div>
        </section>
        <section id="features">
            <h2>Возможности</h2>
            <div class="grid">
                <div class="card"><h3>Глубокий парсинг</h3><p>Поддержка PDF, DOCX, изображений. Текст очищается перед анализом.</p></div>
                <div class="card"><h3>Ollama Cloud</h3><p>Модель gpt-oss:20b-cloud выдаёт точный JSON без галлюцинаций.</p></div>
                <div class="card"><h3>Внешний контекст</h3><p>DuckDuckGo подбирает реальные вакансии и требования для сравнения.</p></div>
                <div class="card"><h3>План развития</h3><p>Если match < 70%, предлагаем курсы и шаги для роста.</p></div>
            </div>
        </section>
    </div>
</body>
</html>
"""


# --- РЕНДЕРИНГ КАБИНЕТА -------------------------------------------------------

def dashboard_html(user: Dict[str, Any], error: str, vacancy_text: str, analysis_block: str, history_block: str) -> str:
    error_block = f'<div class="error">{error}</div>' if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Кабинет кандидата</title>
        <style>
            body {{ background:#0f0f0f; color:#fff; margin:0; font-family:'Inter',system-ui,sans-serif; }}
            .page {{ max-width:1100px; margin:0 auto; padding:30px 20px 80px; }}
            .top-nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }}
            .btn {{ border:1px solid rgba(255,255,255,0.2); color:#fff; padding:8px 16px; border-radius:999px; text-decoration:none; margin-left:8px; }}
            .btn.primary {{ background:#2563eb; border:none; }}
            section {{ background:#141414; border-radius:24px; border:1px solid rgba(255,255,255,0.08); padding:26px; margin-bottom:24px; }}
            label {{ display:block; margin-bottom:6px; color:rgba(255,255,255,0.7); }}
            input[type="file"], textarea {{ width:100%; padding:14px; border-radius:16px; border:1px solid rgba(255,255,255,0.2); background:#0f0f0f; color:#fff; margin-bottom:14px; }}
            textarea {{ min-height:150px; }}
            button {{ width:100%; padding:12px; border:none; border-radius:16px; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }}
            .error {{ color:#f87171; margin-bottom:12px; }}
            .result-card {{ background:#181818; border:1px solid rgba(255,255,255,0.08); border-radius:20px; padding:20px; }}
            .chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }}
            .chip {{ padding:6px 14px; border-radius:999px; background:rgba(37,99,235,0.15); border:1px solid rgba(37,99,235,0.5); }}
            table {{ width:100%; border-collapse:collapse; font-size:0.9rem; }}
            th, td {{ padding:12px; border-bottom:1px solid rgba(255,255,255,0.08); text-align:left; }}
            a.link {{ color:#2563eb; text-decoration:none; margin-right:8px; }}
        </style>
    </head>
    <body>
        <div class="page">
            <div class="top-nav">
                <div>HR Agent · {user['name']}</div>
                <div>
                    <a class="btn" href="/">Лендинг</a>
                    <a class="btn" href="/logout">Выйти</a>
                </div>
            </div>
            <section>
                <h2>Запуск анализа</h2>
                {error_block}
                <form method="post" action="/candidate/analyze" enctype="multipart/form-data">
                    <label for="resume_file">Резюме (PDF/DOCX/PNG/JPG)</label>
                    <input type="file" id="resume_file" name="resume_file" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg" required />
                    <label for="vacancy_text">Описание вакансии</label>
                    <textarea id="vacancy_text" name="vacancy_text" placeholder="Вставьте полное описание роли">{vacancy_text}</textarea>
                    <button type="submit">Анализировать</button>
                </form>
            </section>
            {analysis_block}
            <section>
                <h2>История анализов</h2>
                {history_block}
            </section>
        </div>
    </body>
    </html>
    """


def analysis_block_html(result: Dict[str, Any], sources: List[Dict[str, str]]) -> str:
    chips = "".join(f'<div class="chip">{skill}</div>' for skill in result.get("skills_match", []))
    strengths = "".join(f"<li>{item}</li>" for item in result.get("strengths", []))
    weaknesses = "".join(f"<li>{item}</li>" for item in result.get("weaknesses", []))
    dev_plan = "".join(f"<li>{item}</li>" for item in result.get("development_plan", []))
    recs = "".join(f"<li>{item}</li>" for item in result.get("recommendations", []))
    sources_list = "".join(f'<li><a class="link" href="{src["href"]}" target="_blank">{src["title"]}</a></li>' for src in sources)
    return f"""
    <section class="result-card">
        <h2>Результат: {result.get("match_score", 0)}%</h2>
        <p>Источник: {"LLM gpt-oss:20b-cloud" if result.get("engine") == "llm" else "эвристический анализ"}</p>
        <div class="chips">{chips}</div>
        <h3>Сильные стороны</h3><ul>{strengths}</ul>
        <h3>Зоны роста</h3><ul>{weaknesses}</ul>
        <h3>План развития</h3><ul>{dev_plan}</ul>
        <h3>Рекомендации</h3><ul>{recs}</ul>
        <h3>Источники вакансий</h3><ul>{sources_list}</ul>
        <p>{result.get("summary","")}</p>
    </section>
    """


def history_html(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "<p>Пока нет анализов.</p>"
    rows = ""
    for row in history:
        rows += f"""
        <tr>
            <td>{row['created_at']}</td>
            <td>{row['match_score']}%</td>
            <td>{row['engine']}</td>
            <td>
                <a class="link" href="/candidate/analysis/{row['id']}/download?format=json">JSON</a>
                <a class="link" href="/candidate/analysis/{row['id']}/download?format=docx">DOCX</a>
                <a class="link" href="/candidate/analysis/{row['id']}/download?format=xlsx">XLSX</a>
            </td>
        </tr>
        """
    return f"<table><thead><tr><th>Дата</th><th>Match</th><th>Источник</th><th>Отчёты</th></tr></thead><tbody>{rows}</tbody></table>"


# --- FASTAPI И МАРШРУТЫ --------------------------------------------------------

app = FastAPI(title="HR Agent")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("HR_AGENT_SESSION_SECRET", "hr-agent-session"))


@app.on_event("startup")
async def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    increment_counter("visits")
    user = current_user(request)
    if user:
        auth_block = '<a class="btn" href="/candidate/dashboard">Кабинет</a><a class="btn" href="/logout">Выйти</a>'
    else:
        auth_block = '<a class="btn" href="/login">Войти</a><a class="btn primary" href="/register">Регистрация</a>'
    return HTMLResponse(LANDING_TEMPLATE.format(auth_block=auth_block))


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/candidate/dashboard", status_code=303)
    return HTMLResponse(render_auth_template(mode="register"))


@app.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if len(name.strip()) < 2 or len(password) < 6:
        return HTMLResponse(render_auth_template("register", "Проверьте имя и пароль.", name, email), status_code=400)
    try:
        user_id = create_user(name, email, password)
    except ValueError as exc:
        return HTMLResponse(render_auth_template("register", str(exc), name, email), status_code=400)
    request.session["user_id"] = user_id
    return RedirectResponse("/candidate/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/candidate/dashboard", status_code=303)
    return HTMLResponse(render_auth_template("login"))


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return HTMLResponse(render_auth_template("login", "Неверная почта или пароль.", email=email), status_code=401)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/candidate/dashboard", status_code=303)


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)


def render_auth_template(mode: str, error: str = "", name: str = "", email: str = "") -> str:
    title = "Регистрация — HR Agent" if mode == "register" else "Вход — HR Agent"
    heading = "Создать аккаунт" if mode == "register" else "Войти"
    subtitle = "Получите доступ к анализам."
    footer = 'Уже есть аккаунт? <a href="/login">Войти</a>' if mode == "register" else 'Нет аккаунта? <a href="/register">Регистрация</a>'
    extra_field = ""
    if mode == "register":
        extra_field = (
            '<label for="name">Имя</label>'
            f'<input type="text" id="name" name="name" value="{name}" required />'
        )
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>{title}</title>
        <style>
            body {{ background:#0f0f0f; color:#fff; margin:0; font-family:'Inter',system-ui,sans-serif; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
            .card {{ width:min(420px,90%); background:#141414; border:1px solid rgba(255,255,255,0.1); border-radius:24px; padding:32px; }}
            label {{ display:block; margin-bottom:6px; color:rgba(255,255,255,0.7); }}
            input {{ width:100%; padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,0.2); background:#0f0f0f; color:#fff; margin-bottom:14px; }}
            button {{ width:100%; padding:12px; border:none; border-radius:16px; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }}
            .error {{ color:#f87171; margin-bottom:12px; min-height:18px; }}
            a {{ color:#2563eb; text-decoration:none; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>{heading}</h1>
            <p>{subtitle}</p>
            <div class="error">{error}</div>
            <form method="post">
                {extra_field}
                <label for="email">Почта</label>
                <input type="email" id="email" name="email" value="{email}" required />
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" minlength="6" required />
                <button type="submit">{ "Зарегистрироваться" if mode == "register" else "Войти" }</button>
            </form>
            <p style="margin-top:12px;">{footer}</p>
        </div>
    </body>
    </html>
    """


@app.get("/candidate/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    history = history_html(list_analyses(user["id"]))
    html = dashboard_html(user, "", "", "", history)
    return HTMLResponse(html)


@app.post("/candidate/analyze", response_class=HTMLResponse)
async def candidate_analyze(
    request: Request,
    resume_file: UploadFile = File(...),
    vacancy_text: str = Form(...),
) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    resume_text = (await read_upload(resume_file)).strip()
    vacancy_text = vacancy_text.strip()
    error = ""
    analysis_html_block = ""
    sources: List[Dict[str, str]] = []
    if not resume_text or not vacancy_text:
        error = "Загрузите корректное резюме и описание вакансии."
    else:
        sources = ddg_sources(f"{vacancy_text[:80]} вакансия требования", max_results=5)
        llm_result = run_llm_analysis(resume_text, vacancy_text, sources)
        result = llm_result or heuristic_analysis(resume_text, vacancy_text)
        store_analysis(user["id"], resume_text[:800], vacancy_text, result, sources)
        analysis_html_block = analysis_block_html(result, sources)
    history = history_html(list_analyses(user["id"]))
    html = dashboard_html(user, error, vacancy_text, analysis_html_block, history)
    return HTMLResponse(html, status_code=400 if error else 200)


@app.get("/candidate/analysis/{analysis_id}/download")
async def download_analysis(request: Request, analysis_id: int, format: str = "json"):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    record = fetch_analysis(user["id"], analysis_id)
    if not record:
        return RedirectResponse("/candidate/dashboard", status_code=303)
    payload = {
        "match_score": record["result_json"].get("match_score"),
        "strengths": record["result_json"].get("strengths", []),
        "weaknesses": record["result_json"].get("weaknesses", []),
        "skills_match": record["result_json"].get("skills_match", []),
        "experience_assessment": record["result_json"].get("experience_assessment", ""),
        "education_assessment": record["result_json"].get("education_assessment", ""),
        "development_plan": record["result_json"].get("development_plan", []),
        "recommendations": record["result_json"].get("recommendations", []),
        "summary": record["result_json"].get("summary", ""),
        "vacancy": record["vacancy_description"],
        "resume_excerpt": record["resume_excerpt"],
        "sources": record["sources_json"],
        "engine": record["engine"],
        "created_at": record["created_at"],
    }
    if format == "json":
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(io.BytesIO(data), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.json"'})
    if format == "docx":
        data = analysis_to_docx(payload)
        return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.docx"'})
    if format == "xlsx":
        data = analysis_to_xlsx(payload)
        return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.xlsx"'})
    return RedirectResponse("/candidate/dashboard", status_code=303)


# --- Минимальная админ-инфо ----------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_summary(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Админ — HR Agent</title>
        <style>
            body {{ background:#0f0f0f; color:#fff; margin:0; font-family:'Inter',system-ui,sans-serif; }}
            .page {{ max-width:800px; margin:0 auto; padding:40px 20px; }}
            .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:18px; }}
            .card {{ background:#151515; border:1px solid rgba(255,255,255,0.08); border-radius:18px; padding:24px; }}
            span {{ display:block; color:rgba(255,255,255,0.6); margin-bottom:6px; }}
        </style>
    </head>
    <body>
        <div class="page">
            <h1>Сводка</h1>
            <div class="grid">
                <div class="card"><span>Визитов</span><strong>{get_counter("visits")}</strong></div>
                <div class="card"><span>Регистраций</span><strong>{get_counter("registrations")}</strong></div>
                <div class="card"><span>Анализов</span><strong>{get_counter("analyses")}</strong></div>
                <div class="card"><span>LLM анализов</span><strong>{get_counter("llm_analyses")}</strong></div>
            </div>
            <p style="margin-top:24px;"><a style="color:#2563eb;" href="/">На главную</a></p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/api/interest")
async def collect_interest() -> Dict[str, str]:
    increment_counter("interest")
    return {"status": "ok", "message": "Спасибо! Мы свяжемся при запуске новых функций."}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("hr_agent:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
