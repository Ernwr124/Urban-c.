"""
Candidate-first HR Agent FastAPI application.

Features:
- Landing page and auth with SQLite storage
- Candidate dashboard with resume upload (PDF/DOC/DOCX) + vacancy description
- Analysis pipeline: parses resume, calls gpt-oss:20b-cloud when available, fetches vacancy context via DuckDuckGo, produces scores/strengths/gaps/courses
- History with downloads (JSON, DOCX, XLSX)
- Profile editing & simple admin analytics (visits, registrations, analyses)
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from duckduckgo_search import DDGS
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from jinja2 import BaseLoader, Environment
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:
    pdf_extract_text = None
from openpyxl import Workbook
from pydantic import BaseModel, EmailStr, Field, validator
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

APP_TITLE = "HR Agent — карьерный помощник"
DB_PATH = Path(__file__).with_name("hr_agent.db")
OLLAMA_MODEL = "gpt-oss:20b-cloud"
SESSION_SECRET = os.getenv("HR_AGENT_SESSION_SECRET", secrets.token_hex(32))
PASSWORD_SALT = os.getenv("HR_AGENT_PASSWORD_SALT", "hr-agent-salt")
ADMIN_USERNAME = os.getenv("HR_AGENT_ADMIN_LOGIN", "founder")
ADMIN_PASSWORD_HASH_ENV = os.getenv("HR_AGENT_ADMIN_PASSWORD_HASH")
ADMIN_PASSWORD_PLAIN = os.getenv("HR_AGENT_ADMIN_PASSWORD")


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
        CREATE TABLE IF NOT EXISTS candidate_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resume_excerpt TEXT NOT NULL,
            job_description TEXT NOT NULL,
            skills_json TEXT,
            strengths_json TEXT,
            gaps_json TEXT,
            sources_json TEXT,
            courses_json TEXT,
            score INTEGER NOT NULL,
            engine TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{PASSWORD_SALT}:{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def admin_hash(password: str) -> str:
    return hashlib.sha256(f"admin-salt:{password}".encode("utf-8")).hexdigest()


def get_admin_password_hash() -> str:
    if ADMIN_PASSWORD_HASH_ENV:
        return ADMIN_PASSWORD_HASH_ENV
    if ADMIN_PASSWORD_PLAIN:
        return admin_hash(ADMIN_PASSWORD_PLAIN)
    return admin_hash("hragent123")


def verify_admin(password: str) -> bool:
    return admin_hash(password) == get_admin_password_hash()


def create_user(name: str, email: str, password: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ?", (normalized_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Пользователь с такой почтой уже зарегистрирован.")
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


def update_user_profile(user_id: int, *, name: str, email: str, new_password: Optional[str]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ? AND id <> ?", (normalized_email, user_id))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Эта почта уже используется.")
    fields = ["name = ?", "email = ?"]
    params: List[Any] = [name.strip(), normalized_email]
    if new_password:
        fields.append("password_hash = ?")
        params.append(hash_password(new_password))
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated


def increment_counter(key: str, amount: int = 1) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO analytics_counters (key, value)
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
    cursor.execute("SELECT value FROM analytics_counters WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def store_analysis(
    user_id: int,
    resume_excerpt: str,
    job_description: str,
    skills: List[str],
    strengths: List[str],
    gaps: List[str],
    sources: List[Dict[str, str]],
    courses: List[Dict[str, str]],
    score: int,
    engine: str,
) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO candidate_submissions (
            user_id, resume_excerpt, job_description,
            skills_json, strengths_json, gaps_json,
            sources_json, courses_json,
            score, engine, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            resume_excerpt[:1200],
            job_description[:1200],
            json.dumps(skills, ensure_ascii=False),
            json.dumps(strengths, ensure_ascii=False),
            json.dumps(gaps, ensure_ascii=False),
            json.dumps(sources, ensure_ascii=False),
            json.dumps(courses, ensure_ascii=False),
            score,
            engine,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    analysis_id = cursor.lastrowid
    conn.close()
    increment_counter("analyses")
    if engine == "llm":
        increment_counter("llm_analyses")
    return int(analysis_id)


def get_analysis_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, score, engine, created_at, job_description
        FROM candidate_submissions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_analysis_record(user_id: int, analysis_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM candidate_submissions
        WHERE user_id = ? AND id = ?
        """,
        (user_id, analysis_id),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    for key in ("skills_json", "strengths_json", "gaps_json", "sources_json", "courses_json"):
        item[key] = json.loads(item.get(key) or "[]")
    return item


def get_admin_stats() -> Dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidate_submissions")
    total_analyses = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidate_submissions WHERE engine = 'llm'")
    llm_analyses = cursor.fetchone()[0]
    conn.close()
    return {
        "visits": get_counter("visits"),
        "registrations": total_users,
        "total_analyses": total_analyses,
        "llm_analyses": llm_analyses,
    }


def extract_docx_text(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs if p.text).strip()
    except Exception:
        return ""


def extract_pdf_text(data: bytes) -> str:
    if pdf_extract_text is None:
        return ""
    try:
        return pdf_extract_text(io.BytesIO(data)).strip()
    except Exception:
        return ""


async def upload_to_text(upload: UploadFile | None) -> str:
    if not upload:
        return ""
    data = await upload.read()
    if not data:
        return ""
    filename = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    if filename.endswith(".pdf") or "pdf" in content_type:
        return extract_pdf_text(data)
    if filename.endswith(".docx") or "wordprocessingml" in content_type:
        return extract_docx_text(data)
    return data.decode("utf-8", errors="ignore")


def ddg_links(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            return [{"title": r.get("title", "Результат"), "href": r.get("href", "")} for r in results if r.get("href")]
    except Exception:
        return []


def should_use_ollama() -> bool:
    return os.getenv("HR_AGENT_USE_OLLAMA", "").lower() in {"1", "true", "yes"}


def run_llm_analysis(resume_text: str, job_description: str, context_snippets: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not should_use_ollama():
        return None
    context_block = "\n".join(f"- {item['title']}: {item['href']}" for item in context_snippets[:4])
    prompt = (
        "You are an ATS-quality analyst. Compare the candidate resume with the vacancy requirements.\n"
        "Resume:\n"
        f"{resume_text}\n\n"
        "Vacancy description:\n"
        f"{job_description}\n\n"
        "Additional vacancy context:\n"
        f"{context_block or 'none'}\n\n"
        "Return STRICT JSON with keys:\n"
        "{\n"
        '  "score": int 0-100,\n'
        '  "skills": ["skill"...],\n'
        '  "strengths": ["text"...],\n'
        '  "gaps": ["text"...]\n'
        "}\n"
        "Do not add commentary."
    )
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        raw = (result.stdout or "").strip()
        json_match = json.loads(raw if raw.startswith("{") else raw[raw.find("{") : raw.rfind("}") + 1])
        score = int(json_match.get("score", 0))
        skills = json_match.get("skills", [])
        strengths = json_match.get("strengths", [])
        gaps = json_match.get("gaps", [])
        return {
            "score": max(0, min(100, score)),
            "skills": skills if isinstance(skills, list) else [],
            "strengths": strengths if isinstance(strengths, list) else [],
            "gaps": gaps if isinstance(gaps, list) else [],
            "engine": "llm",
        }
    except Exception:
        return None


def heuristic_analysis(resume_text: str, job_description: str) -> Dict[str, Any]:
    resume_tokens = {token.lower() for token in resume_text.split() if len(token) > 3}
    job_tokens = {token.lower() for token in job_description.split() if len(token) > 3}
    overlap = sorted(job_tokens & resume_tokens)
    missing = sorted(job_tokens - resume_tokens)
    score = int((len(overlap) / max(1, len(job_tokens))) * 100)
    score = max(15, min(95, score))
    strengths = [f"Есть опыт с «{token}»" for token in overlap[:5]]
    gaps = [f"Нет подтверждения навыка «{token}»" for token in missing[:5]]
    return {
        "score": score,
        "skills": overlap[:10],
        "strengths": strengths or ["Резюме содержит релевантные ключевые слова."],
        "gaps": gaps or ["Добавьте больше конкретики о недостающих технологиях."],
        "engine": "heuristic",
    }


def build_course_links(gaps: List[str]) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for gap in gaps[:3]:
        query = f"онлайн курс {gap}"
        links.extend(ddg_links(query, max_results=2))
    return links


def build_download_payload(analysis: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "score": analysis["score"],
        "engine": analysis["engine"],
        "skills": analysis["skills_json"],
        "strengths": analysis["strengths_json"],
        "gaps": analysis["gaps_json"],
        "sources": analysis["sources_json"],
        "courses": analysis["courses_json"],
        "created_at": analysis["created_at"],
        "job_description": analysis["job_description"],
        "resume_excerpt": analysis["resume_excerpt"],
    }


def analysis_to_docx(payload: Dict[str, Any]) -> bytes:
    doc = Document()
    doc.add_heading("HR Agent — отчёт анализа", level=1)
    doc.add_paragraph(f"Дата: {payload['created_at']}")
    doc.add_paragraph(f"Совпадение: {payload['score']}% ({payload['engine']})")
    doc.add_heading("Сильные стороны", level=2)
    for item in payload["strengths"]:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Зоны роста", level=2)
    for item in payload["gaps"]:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("Навыки", level=2)
    doc.add_paragraph(", ".join(payload["skills"]) or "—")
    doc.add_heading("Источники вакансий", level=2)
    for src in payload["sources"]:
        doc.add_paragraph(f"{src.get('title', 'Источник')}: {src.get('href', '')}")
    if payload["courses"]:
        doc.add_heading("Рекомендованные курсы", level=2)
        for course in payload["courses"]:
            doc.add_paragraph(f"{course.get('title', 'Курс')}: {course.get('href', '')}")
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def analysis_to_xlsx(payload: Dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Analysis"
    ws.append(["Поле", "Значение"])
    ws.append(["Дата", payload["created_at"]])
    ws.append(["Совпадение", f"{payload['score']}% ({payload['engine']})"])
    ws.append(["Навыки", ", ".join(payload["skills"])])
    ws.append(["Сильные стороны", "; ".join(payload["strengths"])])
    ws.append(["Зоны роста", "; ".join(payload["gaps"])])
    ws.append(["Источники", "; ".join(src.get("href", "") for src in payload["sources"])])
    ws.append(["Курсы", "; ".join(course.get("href", "") for course in payload["courses"])])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


class InterestPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    message: Optional[str] = Field(default=None, max_length=1000)


LANDING_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ meta.title }}</title>
    <meta name="description" content="{{ meta.description }}" />
    <style>
        :root {
            --bg: #05060a;
            --card: #0f1326;
            --accent: #7f7bff;
            --accent-soft: #b0abff;
            --text: #f5f6fb;
            --muted: #9aa0bd;
            --border: rgba(255,255,255,0.08);
        }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; margin: 0; }
        .page { max-width: 1100px; margin: 0 auto; padding: 40px 20px 80px; }
        .top-nav { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .logo { font-weight:700; letter-spacing:0.08em; color:var(--accent-soft); }
        .nav-actions { display:flex; gap:12px; align-items:center; }
        .btn { border:none; padding:10px 20px; border-radius:999px; cursor:pointer; font-size:0.95rem; }
        .btn.primary { background:linear-gradient(120deg,#6f6af8,#b388ff); color:#fff; }
        .btn.secondary { border:1px solid var(--border); background:transparent; color:var(--text); }
        .profile-button {
            width:38px; height:38px; border-radius:50%; border:1px solid var(--border);
            display:inline-flex; align-items:center; justify-content:center; text-decoration:none; color:var(--accent-soft);
        }
        .hero { padding:60px 0 30px; }
        h1 { font-size: clamp(2rem, 5vw, 3.5rem); margin-bottom:18px; }
        p { color: var(--muted); }
        section { background: var(--card); border-radius:24px; padding:30px; border:1px solid var(--border); margin-bottom:30px; }
        .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(230px,1fr)); gap:18px; }
        .card { background: rgba(255,255,255,0.02); border-radius:18px; padding:18px; border:1px solid var(--border); }
        form { display:grid; gap:14px; }
        input, textarea {
            width:100%; padding:14px; border-radius:14px; border:1px solid var(--border);
            background:rgba(255,255,255,0.03); color:#fff;
        }
    </style>
</head>
<body>
    <div class="page">
        <nav class="top-nav">
            <div class="logo">HR Agent</div>
            <div class="nav-actions">
                {% if user %}
                    <a class="btn secondary" href="/candidate/dashboard">Мой кабинет</a>
                    <a class="profile-button" href="/profile">{{ user.name[:1]|upper }}</a>
                    <a class="btn secondary" href="/logout">Выйти</a>
                {% else %}
                    <a class="btn secondary" href="/login">Войти</a>
                    <a class="btn primary" href="/register">Регистрация</a>
                {% endif %}
            </div>
        </nav>
        <section class="hero">
            <h1>Анализ резюме против вакансии с реальными данными</h1>
            <p>Загрузи PDF или DOCX, опиши вакансию и получи точный процент совпадения, список сильных сторон, пробелы и курсы для закрытия гэпов. Без HR-команд — только ты и прозрачные данные.</p>
            <div style="margin-top:18px;">
                <a class="btn primary" href="/candidate/dashboard">Попробовать сейчас</a>
                <a class="btn secondary" href="#faq">Как это работает</a>
            </div>
        </section>
        <section>
            <h2>Что делает платформа</h2>
            <div class="grid">
                {% for item in features %}
                <div class="card">
                    <h3>{{ item.title }}</h3>
                    <p>{{ item.text }}</p>
                </div>
                {% endfor %}
            </div>
        </section>
        <section id="faq">
            <h2>FAQ</h2>
            <div class="grid">
                {% for item in faq %}
                <div class="card">
                    <h3>{{ item.q }}</h3>
                    <p>{{ item.a }}</p>
                </div>
                {% endfor %}
            </div>
        </section>
    </div>
</body>
</html>
"""


AUTH_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{ title }}</title>
    <style>
        body { font-family:'Inter',system-ui,sans-serif; background:radial-gradient(circle at top, rgba(127,123,255,0.25), #05060a); color:#f5f6fb; min-height:100vh; display:flex; justify-content:center; align-items:center; margin:0; }
        .card { width:min(420px,90%); background:rgba(10,12,25,0.95); border-radius:24px; padding:32px; border:1px solid rgba(255,255,255,0.08); box-shadow:0 30px 60px rgba(0,0,0,0.45); }
        h1 { margin-bottom:8px; }
        p { color:#a8aecb; }
        label { color:#a8aecb; font-size:0.9rem; }
        input { width:100%; padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); color:#fff; margin-top:6px; }
        form { display:grid; gap:16px; margin-top:16px; }
        button { border:none; padding:12px; border-radius:14px; background:linear-gradient(120deg,#6f6af8,#b389ff); color:#fff; cursor:pointer; }
        .error { color:#f87171; min-height:20px; margin-top:12px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>{{ heading }}</h1>
        <p>{{ subtitle }}</p>
        <div class="error">{{ error or "" }}</div>
        <form method="post">
            <div>
                <label for="name">Имя</label>
                <input type="text" id="name" name="name" value="{{ form_data.name }}" required />
            </div>
            <div>
                <label for="email">Почта</label>
                <input type="email" id="email" name="email" value="{{ form_data.email }}" required />
            </div>
            <div>
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" required minlength="6" />
            </div>
            <button type="submit">{{ submit_label }}</button>
        </form>
        <p style="margin-top:12px;">
            {% if mode == 'register' %}
            Уже есть аккаунт? <a href="/login">Войти</a>
            {% else %}
            Нет аккаунта? <a href="/register">Создать</a>
            {% endif %}
        </p>
    </div>
</body>
</html>
"""


CANDIDATE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Кабинет кандидата</title>
    <style>
        body { font-family:'Inter',system-ui,sans-serif; background:#05060a; color:#f5f6fb; margin:0; }
        .page { max-width:1000px; margin:0 auto; padding:30px 20px 80px; }
        .top-nav { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .btn { border:none; padding:10px 18px; border-radius:999px; cursor:pointer; background:linear-gradient(120deg,#6f6af8,#8f83ff); color:#fff; }
        section { background:rgba(16,18,38,0.95); border-radius:24px; padding:26px; border:1px solid rgba(255,255,255,0.06); margin-bottom:24px; }
        label { color:#a8aecb; font-size:0.9rem; }
        input[type="file"], textarea {
            width:100%; padding:14px; border-radius:16px; border:1px solid rgba(255,255,255,0.08);
            background:rgba(255,255,255,0.03); color:#fff; margin-top:6px;
        }
        textarea { min-height:150px; }
        .error { color:#f87171; margin-bottom:10px; }
        .result-card { background:rgba(79,70,229,0.2); border-radius:20px; padding:20px; border:1px solid rgba(123,114,255,0.4); margin-top:16px; }
        .chips { display:flex; flex-wrap:wrap; gap:10px; margin:12px 0; }
        .chip { background:rgba(255,255,255,0.1); border-radius:999px; padding:6px 14px; font-size:0.9rem; }
        table { width:100%; border-collapse:collapse; margin-top:12px; }
        th, td { border-bottom:1px solid rgba(255,255,255,0.08); padding:10px; text-align:left; }
        a.download { color:#c5c8ff; text-decoration:none; margin-right:10px; }
    </style>
</head>
<body>
    <div class="page">
        <div class="top-nav">
            <div>HR Agent · {{ user.name }}</div>
            <div>
                <a class="btn" href="/">Лендинг</a>
                <a class="btn" style="margin-left:8px;background:#2f3146;" href="/logout">Выйти</a>
            </div>
        </div>
        <section>
            <h2>Запустить новый анализ</h2>
            {% if form_error %}
            <div class="error">{{ form_error }}</div>
            {% endif %}
            <form method="post" action="/candidate/analyze" enctype="multipart/form-data">
                <div>
                    <label for="resume_file">Резюме (PDF/DOCX)</label>
                    <input type="file" id="resume_file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required />
                </div>
                <div style="margin-top:16px;">
                    <label for="job_text">Описание вакансии</label>
                    <textarea id="job_text" name="job_text" placeholder="Вставьте полное описание роли">{{ form_data.job_text }}</textarea>
                </div>
                <button class="btn" type="submit" style="margin-top:18px;">Анализировать</button>
            </form>
        </section>
        {% if analysis %}
        <section class="result-card">
            <h2>Результат: {{ analysis.score }}%</h2>
            <p>Источник: {{ 'LLM gpt-oss:20b-cloud' if analysis.engine == 'llm' else 'эвристический анализ' }}</p>
            <div class="chips">
                {% for skill in analysis.skills %}
                <div class="chip">{{ skill }}</div>
                {% endfor %}
            </div>
            <h3>Сильные стороны</h3>
            <ul>
                {% for item in analysis.strengths %}
                <li>{{ item }}</li>
                {% endfor %}
            </ul>
            <h3>Зоны роста</h3>
            <ul>
                {% for item in analysis.gaps %}
                <li>{{ item }}</li>
                {% endfor %}
            </ul>
            <h3>Источники вакансии</h3>
            <ul>
                {% for src in analysis.sources %}
                <li><a href="{{ src.href }}" target="_blank">{{ src.title }}</a></li>
                {% endfor %}
            </ul>
            {% if analysis.courses %}
            <h3>Рекомендованные курсы</h3>
            <ul>
                {% for course in analysis.courses %}
                <li><a href="{{ course.href }}" target="_blank">{{ course.title }}</a></li>
                {% endfor %}
            </ul>
            {% endif %}
        </section>
        {% endif %}
        <section>
            <h2>История анализов</h2>
            <p style="color:#a8aecb;">После каждого анализа профиль автоматически появляется в выдаче отчётов.</p>
            {% if history %}
            <table>
                <thead>
                    <tr>
                        <th>Дата</th>
                        <th>Совпадение</th>
                        <th>Источник</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in history %}
                    <tr>
                        <td>{{ item.created_at }}</td>
                        <td>{{ item.score }}%</td>
                        <td>{{ item.engine }}</td>
                        <td>
                            <a class="download" href="/candidate/analysis/{{ item.id }}/download?format=json">JSON</a>
                            <a class="download" href="/candidate/analysis/{{ item.id }}/download?format=docx">DOCX</a>
                            <a class="download" href="/candidate/analysis/{{ item.id }}/download?format=xlsx">XLSX</a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p>Запустите первый анализ, чтобы увидеть историю.</p>
            {% endif %}
        </section>
    </div>
</body>
</html>
"""


PROFILE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Профиль</title>
    <style>
        body { font-family:'Inter',system-ui,sans-serif; background:#05060a; color:#f5f6fb; margin:0; display:flex; justify-content:center; align-items:center; min-height:100vh; }
        .card { width:min(500px,90%); background:rgba(10,12,27,0.95); border-radius:24px; padding:32px; border:1px solid rgba(255,255,255,0.08); }
        label { color:#a8aecb; font-size:0.9rem; display:block; margin-bottom:6px; }
        input { width:100%; padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); color:#fff; margin-bottom:14px; }
        button { border:none; padding:12px; border-radius:14px; background:linear-gradient(120deg,#6f6af8,#8f83ff); color:#fff; cursor:pointer; width:100%; }
        .status { color:#4ade80; margin-bottom:12px; }
        .error { color:#f87171; margin-bottom:12px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Профиль</h1>
        {% if status %}<div class="status">{{ status }}</div>{% endif %}
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="post">
            <div>
                <label for="name">Имя</label>
                <input type="text" id="name" name="name" value="{{ user.name }}" required />
            </div>
            <div>
                <label for="email">Почта</label>
                <input type="email" id="email" name="email" value="{{ user.email }}" required />
            </div>
            <div>
                <label for="new_password">Новый пароль (опционально)</label>
                <input type="password" id="new_password" name="new_password" minlength="6" />
            </div>
            <button type="submit">Сохранить</button>
        </form>
        <p style="margin-top:16px;"><a href="/candidate/dashboard" style="color:#a8aecb;">← В кабинет</a></p>
    </div>
</body>
</html>
"""


ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Вход администратора — HR Agent</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #05060a; color: #f5f6fb; margin: 0; display:flex; justify-content:center; align-items:center; min-height:100vh; }
        .card { width: min(420px, 90%); background: rgba(17,20,37,0.95); border-radius: 24px; padding: 32px; border: 1px solid rgba(255,255,255,0.08); }
        label { display:block; margin-bottom:6px; color:#a8aecb; }
        input { width:100%; padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.04); color:#fff; }
        form { display:grid; gap:18px; margin-top:16px; }
        .btn { border:none; padding:12px 22px; border-radius:999px; background:linear-gradient(120deg,#6f6af8,#8f83ff); color:#fff; cursor:pointer; }
        .error { color:#f87171; min-height:18px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Admin панель</h1>
        <div class="error">{{ error or "" }}</div>
        <form method="post">
            <div>
                <label for="username">Логин</label>
                <input type="text" id="username" name="username" required />
            </div>
            <div>
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" required />
            </div>
            <button class="btn" type="submit">Войти</button>
        </form>
    </div>
</body>
</html>
"""


ADMIN_DASH_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Админ-аналитика — HR Agent</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #05060a; color: #f5f6fb; margin: 0; }
        .page { max-width: 900px; margin: 0 auto; padding: 40px 20px 80px; }
        .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
        .btn { border:none; padding:10px 18px; border-radius:999px; cursor:pointer; background:linear-gradient(120deg,#6f6af8,#8f83ff); color:#fff; text-decoration:none; }
        .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:18px; }
        .card { background:rgba(17,20,37,0.95); border-radius:20px; padding:24px; border:1px solid rgba(255,255,255,0.08); }
        .card span { display:block; color:#a8aecb; margin-bottom:6px; }
        .card strong { font-size:2rem; }
    </style>
</head>
<body>
    <div class="page">
        <div class="top">
            <h1>Админ-аналитика</h1>
            <div>
                <a class="btn" href="/">Главная</a>
                <a class="btn" style="margin-left:8px;background:#2f3146;" href="/admin/logout">Выйти</a>
            </div>
        </div>
        <div class="grid">
            <div class="card">
                <span>Визитов</span>
                <strong>{{ stats.visits }}</strong>
            </div>
            <div class="card">
                <span>Регистраций</span>
                <strong>{{ stats.registrations }}</strong>
            </div>
            <div class="card">
                <span>Анализов</span>
                <strong>{{ stats.total_analyses }}</strong>
            </div>
            <div class="card">
                <span>LLM-анализов</span>
                <strong>{{ stats.llm_analyses }}</strong>
            </div>
        </div>
    </div>
</body>
</html>
"""


env = Environment(loader=BaseLoader(), autoescape=True)
templates = {
    "landing": env.from_string(LANDING_TEMPLATE),
    "auth": env.from_string(AUTH_TEMPLATE),
    "candidate": env.from_string(CANDIDATE_TEMPLATE),
    "profile": env.from_string(PROFILE_TEMPLATE),
    "admin_login": env.from_string(ADMIN_LOGIN_TEMPLATE),
    "admin_dashboard": env.from_string(ADMIN_DASH_TEMPLATE),
}


def render_template(name: str, **context: Any) -> str:
    return templates[name].render(**context)


app = FastAPI(title=APP_TITLE)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="hragent_session")


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(int(user_id))


def landing_context(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "meta": {"title": APP_TITLE, "description": "Прозрачный анализ резюме против вакансии."},
        "user": user,
        "features": [
            {"title": "Парсинг резюме", "text": "Поддерживаем PDF и DOCX с аккуратным извлечением текста."},
            {"title": "Контекст из сети", "text": "Ищем анонимные источники и актуальные вакансии через DuckDuckGo."},
            {"title": "LLM-анализ", "text": "Используем gpt-oss:20b-cloud для точных выводов без галлюцинаций."},
            {"title": "Рекомендации", "text": "При низком совпадении предложим курсы и шаги для усиления профиля."},
        ],
        "faq": [
            {"q": "Нужны ли HR-права?", "a": "Нет, платформа работает для кандидатов без участия компаний."},
            {"q": "Что нужно подготовить?", "a": "PDF или DOCX резюме и текст желаемой вакансии."},
            {"q": "Данные передаются кому-то ещё?", "a": "Нет, они остаются на сервере, а доступ контролирует только пользователь."},
            {"q": "Можно ли выгружать отчёт?", "a": "Да, доступны JSON, DOCX и XLSX отчёты для каждого анализа."},
        ],
    }


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    increment_counter("visits")
    html = render_template("landing", **landing_context(user))
    return HTMLResponse(content=html)


def auth_response(mode: str, error: Optional[str], form_data: Dict[str, str]) -> HTMLResponse:
    return HTMLResponse(
        content=render_template(
            "auth",
            title="Регистрация" if mode == "register" else "Вход",
            heading="Создать аккаунт" if mode == "register" else "Войти",
            subtitle="Доступ к персональному анализу.",
            mode=mode,
            error=error,
            submit_label="Зарегистрироваться" if mode == "register" else "Войти",
            form_data=form_data,
        ),
        status_code=400 if error else 200,
    )


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    return auth_response("register", None, {"name": "", "email": ""})


@app.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    if len(name) < 2:
        return auth_response("register", "Имя слишком короткое.", {"name": name, "email": email})
    if len(password) < 6:
        return auth_response("register", "Пароль минимум 6 символов.", {"name": name, "email": email})
    try:
        user_id = create_user(name, email, password)
    except ValueError as exc:
        return auth_response("register", str(exc), {"name": name, "email": email})
    request.session["user_id"] = user_id
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    if get_current_user(request):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    return auth_response("login", None, {"name": "", "email": ""})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request) -> HTMLResponse:
    form = await request.form()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return auth_response("login", "Неверная почта или пароль.", {"name": "", "email": email})
    request.session["user_id"] = user["id"]
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/profile", status_code=HTTP_303_SEE_OTHER)
    html = render_template("profile", user=user, error=None, status=None)
    return HTMLResponse(content=html)


@app.post("/profile", response_class=HTMLResponse)
async def profile_update(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/profile", status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    new_password = form.get("new_password", "").strip()
    if len(name) < 2 or not email:
        html = render_template("profile", user=user, error="Проверьте имя и почту.", status=None)
        return HTMLResponse(content=html, status_code=400)
    try:
        updated = update_user_profile(
            user["id"],
            name=name,
            email=email,
            new_password=new_password if new_password else None,
        )
    except ValueError as exc:
        html = render_template("profile", user=user, error=str(exc), status=None)
        return HTMLResponse(content=html, status_code=400)
    request.session["user_id"] = updated["id"]
    html = render_template("profile", user=updated, error=None, status="Профиль обновлён.")
    return HTMLResponse(content=html)


@app.get("/candidate/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    history = get_analysis_history(user["id"])
    html = render_template(
        "candidate",
        user=user,
        analysis=None,
        history=history,
        form_data={"job_text": ""},
        form_error=None,
    )
    return HTMLResponse(content=html)


@app.post("/candidate/analyze", response_class=HTMLResponse)
async def candidate_analyze(
    request: Request,
    resume_file: UploadFile = File(...),
    job_text: str = Form(...),
) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    resume_text = (await upload_to_text(resume_file)).strip()
    job_text = job_text.strip()
    form_error = None
    if not resume_text:
        form_error = "Не удалось прочитать резюме. Убедитесь, что формат поддерживается."
    elif not job_text:
        form_error = "Добавьте описание вакансии."
    if form_error:
        history = get_analysis_history(user["id"])
        html = render_template(
            "candidate",
            user=user,
            analysis=None,
            history=history,
            form_data={"job_text": job_text},
            form_error=form_error,
        )
        return HTMLResponse(content=html, status_code=400)

    context_sources = ddg_links(f"{job_text[:80]} вакансии требования", max_results=5)
    llm_result = run_llm_analysis(resume_text, job_text, context_sources)
    analysis_result = llm_result or heuristic_analysis(resume_text, job_text)
    courses: List[Dict[str, str]] = []
    if analysis_result["score"] < 70 and analysis_result["gaps"]:
        courses = build_course_links(analysis_result["gaps"])
    analysis_id = store_analysis(
        user_id=user["id"],
        resume_excerpt=resume_text[:800],
        job_description=job_text,
        skills=analysis_result["skills"],
        strengths=analysis_result["strengths"],
        gaps=analysis_result["gaps"],
        sources=context_sources,
        courses=courses,
        score=analysis_result["score"],
        engine=analysis_result["engine"],
    )
    history = get_analysis_history(user["id"])
    html = render_template(
        "candidate",
        user=user,
        analysis={
            "score": analysis_result["score"],
            "engine": analysis_result["engine"],
            "skills": analysis_result["skills"],
            "strengths": analysis_result["strengths"],
            "gaps": analysis_result["gaps"],
            "sources": context_sources,
            "courses": courses,
        },
        history=history,
        form_data={"job_text": ""},
        form_error=None,
    )
    return HTMLResponse(content=html)


@app.get("/candidate/analysis/{analysis_id}/download")
async def download_analysis(request: Request, analysis_id: int, format: str = "json") -> StreamingResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login?next=/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    record = get_analysis_record(user["id"], analysis_id)
    if not record:
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    payload = build_download_payload(record)
    if format == "json":
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.json"'},
        )
    if format == "docx":
        data = analysis_to_docx(payload)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.docx"'},
        )
    if format == "xlsx":
        data = analysis_to_xlsx(payload)
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.xlsx"'},
        )
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)


@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request) -> HTMLResponse:
    if request.session.get("admin_authenticated"):
        return RedirectResponse("/admin/dashboard", status_code=HTTP_303_SEE_OTHER)
    return HTMLResponse(render_template("admin_login", error=None))


@app.post("/admin", response_class=HTMLResponse)
async def admin_login_submit(request: Request) -> HTMLResponse:
    if request.session.get("admin_authenticated"):
        return RedirectResponse("/admin/dashboard", status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    if username != ADMIN_USERNAME or not verify_admin(password):
        return HTMLResponse(render_template("admin_login", error="Неверные данные."), status_code=401)
    request.session["admin_authenticated"] = True
    return RedirectResponse("/admin/dashboard", status_code=HTTP_303_SEE_OTHER)


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request) -> HTMLResponse:
    if not request.session.get("admin_authenticated"):
        return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)
    stats = get_admin_stats()
    html = render_template("admin_dashboard", stats=stats)
    return HTMLResponse(content=html)


@app.get("/admin/logout")
async def admin_logout(request: Request) -> RedirectResponse:
    request.session.pop("admin_authenticated", None)
    return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)


@app.post("/api/interest")
async def collect_interest(payload: InterestPayload) -> JSONResponse:
    increment_counter("interest")
    return JSONResponse({"status": "ok", "message": "Спасибо! Мы пригласим вас в первую волну."})


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("hr_agent:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
