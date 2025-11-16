"""
HR Agent single-file FastAPI app.

Содержит лендинг, регистрацию, вход и раздельные кабинеты для кандидатов и HR,
а также хранит данные в SQLite и использует встроенные HTML/CSS/JS шаблоны.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import secrets
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import BaseLoader, Environment
try:
    from pdfminer.high_level import extract_text as pdf_extract_text
except ImportError:  # fallback when pdfminer.six отсутствует
    pdf_extract_text = None
from pydantic import BaseModel, EmailStr, Field, validator
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

APP_TITLE = "HR Agent — платформа точного подбора"
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
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            company TEXT,
            message TEXT,
            interest_score INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('candidate','hr')),
            org_type TEXT,
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
            job_focus TEXT NOT NULL,
            matched_keywords TEXT,
            missing_keywords TEXT,
            score INTEGER NOT NULL,
            engine TEXT DEFAULT 'heuristic',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_leads_role_created
        ON leads (role, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_candidate_submissions_user_created
        ON candidate_submissions (user_id, created_at DESC)
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
    # ensure engine column exists if база создана ранее
    cursor.execute("PRAGMA table_info(candidate_submissions)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if "engine" not in existing_columns:
        cursor.execute("ALTER TABLE candidate_submissions ADD COLUMN engine TEXT DEFAULT 'heuristic'")
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


def create_user(name: str, email: str, password: str, role: str, org_type: Optional[str]) -> int:
    normalized_email = email.strip().lower()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (normalized_email,))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Пользователь с такой почтой уже зарегистрирован.")
    if role == "hr" and not org_type:
        conn.close()
        raise ValueError("Укажите тип организации.")
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, role, org_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name.strip(),
            normalized_email,
            hash_password(password),
            role,
            org_type if role == "hr" else None,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return int(new_id)


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


def store_lead(payload: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO leads (name, email, role, company, message, interest_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["name"],
            payload["email"].lower(),
            payload["role"],
            payload.get("company"),
            payload.get("message"),
            payload.get("interest_score", 0),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return int(new_id)


def get_metrics() -> Dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM leads")
    leads = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'candidate'")
    registered_candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'hr'")
    hr_partners = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidate_submissions")
    analyses = cursor.fetchone()[0]
    conn.close()
    return {
        "leads": leads,
        "registered_candidates": registered_candidates,
        "hr_partners": hr_partners,
        "analyses": analyses,
    }


def save_candidate_submission(
    user_id: int,
    resume_text: str,
    job_text: str,
    matched: List[str],
    missing: List[str],
    score: int,
    engine: str,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO candidate_submissions (
            user_id, resume_excerpt, job_focus, matched_keywords, missing_keywords, score, engine, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            resume_text[:800],
            job_text[:800],
            ", ".join(matched) if matched else "",
            ", ".join(missing) if missing else "",
            score,
            engine,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_candidate_history(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT resume_excerpt, job_focus, matched_keywords, missing_keywords, score, engine, created_at
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


def search_candidate_submissions(keyword: Optional[str], name: Optional[str]) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT cs.resume_excerpt, cs.job_focus, cs.matched_keywords, cs.missing_keywords,
               cs.score, cs.engine, cs.created_at, u.name AS user_name, u.email
        FROM candidate_submissions cs
        JOIN users u ON cs.user_id = u.id
    """
    conditions = []
    params: List[Any] = []
    if keyword:
        like = f"%{keyword.lower()}%"
        conditions.append(
            "(LOWER(cs.resume_excerpt) LIKE ? OR LOWER(cs.job_focus) LIKE ? OR LOWER(cs.matched_keywords) LIKE ?)"
        )
        params.extend([like, like, like])
    if name:
        like_name = f"%{name.lower()}%"
        conditions.append("LOWER(u.name) LIKE ?")
        params.append(like_name)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY cs.created_at DESC LIMIT 25"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


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


def get_admin_stats() -> Dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'candidate'")
    total_candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'hr'")
    total_hr = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidate_submissions")
    total_analyses = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidate_submissions WHERE engine = 'llm'")
    llm_analyses = cursor.fetchone()[0]
    conn.close()
    return {
        "visits": get_counter("visits"),
        "total_users": total_users,
        "total_candidates": total_candidates,
        "total_hr": total_hr,
        "total_analyses": total_analyses,
        "llm_analyses": llm_analyses,
    }


def update_user_profile(
    user_id: int,
    *,
    name: str,
    email: str,
    org_type: Optional[str],
    new_password: Optional[str],
) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    normalized_email = email.strip().lower()
    cursor.execute("SELECT id FROM users WHERE email = ? AND id <> ?", (normalized_email, user_id))
    if cursor.fetchone():
        conn.close()
        raise ValueError("Эта почта уже используется.")
    fields = ["name = ?", "email = ?"]
    params: List[Any] = [name.strip(), normalized_email]
    if org_type is not None:
        fields.append("org_type = ?")
        params.append(org_type)
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


async def upload_to_text(upload: StarletteUploadFile | None) -> str:
    if not upload or not getattr(upload, "filename", None):
        return ""
    content = await upload.read()
    if not content:
        return ""
    filename = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    if filename.endswith(".pdf") or "pdf" in content_type:
        text = extract_pdf_text(content)
    elif filename.endswith(".docx") or "wordprocessingml" in content_type:
        text = extract_docx_text(content)
    elif filename.endswith(".doc"):
        text = extract_docx_text(content)
    else:
        text = content.decode("utf-8", errors="ignore")
    return text.strip()


def analyze_with_llm(resume_text: str, job_text: str) -> Optional[Dict[str, Any]]:
    if not should_use_ollama():
        return None
    prompt = (
        "You are an AI HR analyst. Compare the candidate resume with the vacancy requirements. "
        "Return JSON with keys: score (0-100 integer), matched_keywords (list of up to 8 short skills), "
        "missing_keywords (list of up to 8 skills), summary (string <= 220 characters explaining fit). "
        "Resume:\n"
        f"{resume_text}\n\nVacancy:\n{job_text}"
    )
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        raw_text = (result.stdout or "").strip()
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        payload = json.loads(json_match.group() if json_match else raw_text)
        score = int(payload.get("score", 0))
        matched = payload.get("matched_keywords", [])
        missing = payload.get("missing_keywords", [])
        if isinstance(matched, str):
            matched = [item.strip() for item in matched.split(",") if item.strip()]
        if isinstance(missing, str):
            missing = [item.strip() for item in missing.split(",") if item.strip()]
        return {
            "score": max(0, min(100, score)),
            "matched": matched or [],
            "missing": missing or [],
            "summary": payload.get("summary", "Анализ выполнен LLM-моделью."),
            "engine": "llm",
        }
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


def should_use_ollama() -> bool:
    return os.getenv("HR_AGENT_USE_OLLAMA", "").lower() in {"1", "true", "yes"}


def ollama_tagline(prompt: str) -> Optional[str]:
    if not should_use_ollama():
        return None
    try:
        result = subprocess.run(
            ["ollama", "run", OLLAMA_MODEL],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=12,
            check=False,
        )
        text = (result.stdout or "").strip()
        return text[:160] if text else None
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None


def choose_tagline() -> str:
    base_options = [
        "Соединяем сильных кандидатов и HR-команды быстрее рынка",
        "Интеллектуальный помощник по подбору IT-талантов",
        "Релевантность резюме видна до первого созвона",
        "Контролируем точность сопоставления кандидатов и ролей",
    ]
    prompt = (
        "Придумай короткий (до 12 слов) слоган для HR-платформы, которая "
        "сопоставляет IT-кандидатов с вакансиями по данным резюме. Используй деловой тон."
    )
    generated = ollama_tagline(prompt)
    return generated or random.choice(base_options)


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-Я0-9+#]+", text.lower())
    return [token for token in tokens if len(token) > 2]


def simple_resume_analysis(resume_text: str, job_text: str) -> Dict[str, Any]:
    resume_tokens = set(tokenize(resume_text))
    job_tokens = set(tokenize(job_text))
    matched = sorted(job_tokens & resume_tokens)
    missing = sorted(job_tokens - resume_tokens)
    overlap_ratio = len(matched) / max(len(job_tokens), 1)
    score = int(min(1.0, overlap_ratio) * 100)
    if not job_tokens:
        score = min(40, len(resume_tokens))
    score = max(20, min(98, score + min(len(matched) * 3, 25)))
    summary = (
        f"Совпало {len(matched)} ключевых навыков из {max(len(job_tokens), 1)} "
        f"заявленных в описании роли."
    )
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "summary": summary,
        "engine": "heuristic",
    }


class InterestPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    role: str = Field(..., description="candidate or hr")
    company: Optional[str] = Field(default=None, max_length=160)
    message: Optional[str] = Field(default=None, max_length=1000)

    @validator("role")
    def validate_role(cls, v: str) -> str:
        normalized = v.lower()
        if normalized not in {"candidate", "hr"}:
            raise ValueError("role must be candidate or hr")
        return normalized


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
            --card: #10121a;
            --card-muted: #151926;
            --accent: #6f6af8;
            --accent-strong: #8f83ff;
            --accent-soft: #b4b0ff;
            --text: #f5f6fb;
            --muted: #9aa0bd;
            --border: rgba(255,255,255,0.08);
            --success: #4ade80;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', system-ui, sans-serif; }
        body {
            background: radial-gradient(circle at top, rgba(111,106,248,0.25), transparent 50%), var(--bg);
            color: var(--text);
        }
        .page { max-width: 1100px; margin: 0 auto; padding: 40px 20px 80px; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .logo { font-weight: 600; letter-spacing: 0.05em; color: var(--accent-soft); }
        .nav-actions { display: flex; gap: 12px; align-items: center; }
        .profile-button {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            border: 1px solid var(--border);
            background: var(--card-muted);
            color: var(--accent-soft);
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
        }
        .ghost-link { color: var(--muted); text-decoration: none; font-size: 0.95rem; }
        header.hero { padding: 40px 0 30px; }
        .eyebrow {
            display: inline-flex; gap: 8px; padding: 6px 14px; background: rgba(111,106,248,0.12);
            border: 1px solid var(--border); border-radius: 999px; font-size: 0.85rem; letter-spacing: 0.08em;
        }
        h1 { font-size: clamp(2rem, 5vw, 3.3rem); margin: 18px 0; line-height: 1.15; }
        .hero p { max-width: 640px; color: var(--muted); font-size: 1.05rem; }
        .hero-actions { margin-top: 28px; display: flex; flex-wrap: wrap; gap: 14px; }
        .btn {
            border: none; padding: 12px 24px; border-radius: 999px; font-size: 0.95rem;
            cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .btn.primary { background: linear-gradient(120deg, var(--accent), var(--accent-strong)); color: #fff; }
        .btn.secondary { background: transparent; border: 1px solid var(--border); color: var(--text); }
        .btn.small { padding: 8px 18px; font-size: 0.9rem; }
        section {
            margin-top: 50px; background: var(--card); padding: 30px; border-radius: 24px;
            border: 1px solid var(--border); box-shadow: 0 20px 60px rgba(0,0,0,0.16);
        }
        section header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 18px; }
        .card { background: var(--card-muted); border-radius: 20px; padding: 20px; border: 1px solid var(--border); }
        .card h3 { margin-bottom: 8px; font-size: 1.1rem; }
        .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
        .metric { padding: 18px; background: var(--card-muted); border-radius: 16px; border: 1px solid var(--border); }
        .metric strong { font-size: 1.8rem; display: block; margin-bottom: 6px; }
        .timeline { display: grid; gap: 14px; }
        .timeline-step { padding: 18px; border-radius: 16px; border: 1px solid var(--border); background: rgba(111,106,248,0.08); }
        .faq-item { padding: 16px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        form { display: grid; gap: 14px; }
        input, select, textarea {
            width: 100%; padding: 14px; border-radius: 14px; border: 1px solid var(--border);
            background: rgba(255,255,255,0.02); color: var(--text); font-size: 1rem;
        }
        textarea { min-height: 120px; }
        .form-status { font-size: 0.95rem; min-height: 24px; }
        @media (max-width: 640px) {
            section { padding: 22px; }
            .hero-actions { flex-direction: column; align-items: flex-start; }
            .top-nav { flex-direction: column; align-items: flex-start; gap: 10px; }
        }
    </style>
</head>
<body>
    <div class="page">
        <nav class="top-nav">
            <div class="logo">HR Agent</div>
            <div class="nav-actions">
                {% if user %}
                    <a class="ghost-link" href="{{ '/candidate/dashboard' if user.role == 'candidate' else '/hr/dashboard' }}">Мой кабинет</a>
                    <a class="profile-button" href="/profile">{{ user.name[:1]|upper }}</a>
                    <a class="btn secondary small" href="/logout">Выйти</a>
                {% else %}
                    <a class="ghost-link" href="/login">Войти</a>
                    <a class="btn primary small" href="/register">Регистрация</a>
                {% endif %}
            </div>
        </nav>
        <header class="hero">
            <div class="eyebrow">IT-рекрутинг без хаоса</div>
            <h1>{{ hero.tagline }}</h1>
            <p>{{ hero.subtitle }}</p>
            <div class="hero-actions">
                <button class="btn primary" onclick="document.getElementById('interest').scrollIntoView({ behavior: 'smooth' })">Стать ранним пользователем</button>
                <button class="btn secondary" onclick="document.getElementById('faq').scrollIntoView({ behavior: 'smooth' })">Посмотреть как работает</button>
            </div>
        </header>

        <section>
            <header>
                <h2>Что получает кандидат</h2>
                <span class="eyebrow">Прозрачная оценка профиля</span>
            </header>
            <div class="grid">
                {% for feature in candidate_features %}
                <div class="card">
                    <h3>{{ feature.title }}</h3>
                    <p>{{ feature.text }}</p>
                </div>
                {% endfor %}
            </div>
        </section>

        <section>
            <header>
                <h2>Функции для HR-команд</h2>
                <span class="eyebrow">Сокращаем время найма</span>
            </header>
            <div class="grid">
                {% for feature in hr_features %}
                <div class="card">
                    <h3>{{ feature.title }}</h3>
                    <p>{{ feature.text }}</p>
                </div>
                {% endfor %}
            </div>
        </section>

        <section>
            <header>
                <h2>Цифры закрытого запуска</h2>
                <span class="eyebrow">Живые данные</span>
            </header>
            <div class="metrics">
                <div class="metric">
                    <strong>{{ metrics.registered_candidates }}</strong>
                    <span>Зарегистрированных кандидатов</span>
                </div>
                <div class="metric">
                    <strong>{{ metrics.hr_partners }}</strong>
                    <span>HR-команд в очереди</span>
                </div>
                <div class="metric">
                    <strong>{{ metrics.analyses }}</strong>
                    <span>Проведённых анализов профиля</span>
                </div>
                <div class="metric">
                    <strong>{{ metrics.leads }}</strong>
                    <span>Заявок на ранний доступ</span>
                </div>
            </div>
        </section>

        <section>
            <header>
                <h2>Путь кандидата</h2>
                <span class="eyebrow">Три шага до отклика</span>
            </header>
            <div class="timeline">
                {% for step in timeline %}
                <div class="timeline-step">
                    <span>{{ step.number }}</span>
                    <h3>{{ step.title }}</h3>
                    <p>{{ step.text }}</p>
                </div>
                {% endfor %}
            </div>
        </section>

        <section id="faq">
            <header>
                <h2>FAQ</h2>
                <span class="eyebrow">Прозрачные ответы</span>
            </header>
            <div>
                {% for item in faq %}
                <div class="faq-item">
                    <h3>{{ item.q }}</h3>
                    <p>{{ item.a }}</p>
                </div>
                {% endfor %}
            </div>
        </section>

        <section id="interest">
            <header>
                <h2>Присоединиться к закрытому запуску</h2>
                <span class="eyebrow">Места ограничены</span>
            </header>
            <form id="interest-form">
                <div>
                    <label for="name">Имя и фамилия</label>
                    <input type="text" id="name" name="name" required minlength="2" />
                </div>
                <div>
                    <label for="email">Рабочая почта</label>
                    <input type="email" id="email" name="email" required />
                </div>
                <div>
                    <label for="role">Я —</label>
                    <select id="role" name="role" required>
                        <option value="candidate">Кандидат</option>
                        <option value="hr">HR / Tech рекрутер</option>
                    </select>
                </div>
                <div>
                    <label for="company">Компания или роль</label>
                    <input type="text" id="company" name="company" placeholder="Например, Senior Backend Engineer" />
                </div>
                <div>
                    <label for="message">Задачи или ожидания</label>
                    <textarea id="message" name="message" placeholder="Опишите, как можем помочь."></textarea>
                </div>
                <button class="btn primary" type="submit">Получить доступ первым</button>
                <div class="form-status" id="form-status"></div>
            </form>
        </section>
    </div>

    <script>
        const form = document.getElementById("interest-form");
        const statusBox = document.getElementById("form-status");
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            statusBox.textContent = "Отправляем заявку...";
            statusBox.style.color = "#f5f6fb";
            const formData = new FormData(form);
            const payload = Object.fromEntries(formData.entries());
            try {
                const response = await fetch("/api/interest", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) {
                    throw new Error("Ошибка сервера");
                }
                const result = await response.json();
                statusBox.style.color = "#4ade80";
                statusBox.textContent = result.message;
                form.reset();
            } catch (error) {
                statusBox.style.color = "#f87171";
                statusBox.textContent = "Не удалось сохранить заявку. Попробуйте снова.";
            }
        });
    </script>
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
        body {
            font-family: 'Inter', system-ui, sans-serif;
            background: radial-gradient(circle at top, rgba(111,106,248,0.25), #05060a);
            color: #f5f6fb;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .auth-card {
            width: min(420px, 100%);
            background: rgba(13,16,32,0.9);
            border-radius: 24px;
            padding: 32px;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 25px 60px rgba(0,0,0,0.4);
        }
        h1 { margin-bottom: 8px; }
        p.subtitle { color: #a8aecb; margin-bottom: 24px; }
        form { display: grid; gap: 16px; }
        label { font-size: 0.9rem; color: #c7cbe2; }
        input, select {
            width: 100%; padding: 14px; border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.04);
            color: #fff; font-size: 1rem;
        }
        button {
            border: none; padding: 14px; border-radius: 14px;
            font-size: 1rem;
            background: linear-gradient(120deg, #6f6af8, #8f83ff);
            color: #fff;
            cursor: pointer;
        }
        .error { color: #f87171; min-height: 20px; }
        .success { color: #4ade80; min-height: 20px; }
        .alt-link { margin-top: 14px; text-align: center; }
        a { color: #8f83ff; }
        .org-type { display: none; }
    </style>
</head>
<body>
    <div class="auth-card">
        <h1>{{ heading }}</h1>
        <p class="subtitle">{{ subtitle }}</p>
        <div class="error">{{ error or "" }}</div>
        <div class="success">{{ success or "" }}</div>
        <form method="post">
            {% if mode == 'register' %}
            <div>
                <label for="role">Роль</label>
                <select id="role" name="role" required>
                    <option value="candidate" {% if form_data.role == 'candidate' %}selected{% endif %}>Кандидат</option>
                    <option value="hr" {% if form_data.role == 'hr' %}selected{% endif %}>HR специалист</option>
                </select>
            </div>
            {% endif %}
            <div>
                <label for="name">Имя</label>
                <input type="text" id="name" name="name" required value="{{ form_data.name }}" />
            </div>
            <div>
                <label for="email">Google аккаунт</label>
                <input type="email" id="email" name="email" required value="{{ form_data.email }}" />
            </div>
            <div>
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" required minlength="6" />
            </div>
            {% if mode == 'register' %}
            <div class="org-type" id="org-wrapper">
                <label for="org_type">Тип организации</label>
                <select id="org_type" name="org_type">
                    <option value="">Выберите</option>
                    <option value="startup" {% if form_data.org_type == 'startup' %}selected{% endif %}>Стартап</option>
                    <option value="company" {% if form_data.org_type == 'company' %}selected{% endif %}>Компания</option>
                </select>
            </div>
            {% endif %}
            <button type="submit">{{ submit_label }}</button>
        </form>
        <div class="alt-link">
            {% if mode == 'register' %}
            Уже есть аккаунт? <a href="/login">Войти</a>
            {% else %}
            Нет аккаунта? <a href="/register">Создать</a>
            {% endif %}
        </div>
    </div>
    {% if mode == 'register' %}
    <script>
        const roleSelect = document.getElementById("role");
        const orgWrapper = document.getElementById("org-wrapper");
        function toggleOrgField() {
            if (roleSelect.value === "hr") {
                orgWrapper.style.display = "block";
            } else {
                orgWrapper.style.display = "none";
            }
        }
        toggleOrgField();
        roleSelect.addEventListener("change", toggleOrgField);
    </script>
    {% endif %}
</body>
</html>
"""


CANDIDATE_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Кабинет кандидата — HR Agent</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #05060a; color: #f5f6fb; margin: 0; }
        .page { max-width: 980px; margin: 0 auto; padding: 30px 20px 60px; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .btn { border: none; padding: 10px 18px; border-radius: 999px; cursor: pointer; background: linear-gradient(120deg, #6f6af8, #8f83ff); color: #fff; }
        h1 { margin-bottom: 10px; }
        .subtitle { color: #a8aecb; margin-bottom: 24px; }
        section { background: rgba(17,20,37,0.95); border-radius: 20px; padding: 24px; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 24px; }
        textarea {
            width: 100%; border-radius: 16px; border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03); color: #fff; padding: 14px; min-height: 140px; font-size: 1rem;
        }
        label { display: block; margin-bottom: 8px; color: #a8aecb; }
        .result-card {
            margin-top: 14px; padding: 20px; border-radius: 18px;
            background: rgba(79,70,229,0.18); border: 1px solid rgba(123,114,255,0.4);
        }
        .history-item { border-top: 1px solid rgba(255,255,255,0.05); padding: 14px 0; }
        .history-item:first-child { border-top: none; }
        .badge { display: inline-flex; padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,0.08); font-size: 0.85rem; }
        .profile-button {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            border: 1px solid rgba(255,255,255,0.15);
            background: #2f3146;
            color: #c5c8ff;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
        }
        .hint { color: #9fa5c7; font-size: 0.9rem; margin-top: 6px; }
        .error { color: #f87171; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="page">
        <div class="top-nav">
            <div>HR Agent · {{ user.name }}</div>
            <div>
                <a class="btn" href="/">На лендинг</a>
                <a class="profile-button" style="margin-left:8px;" href="/profile">{{ user.name[:1]|upper }}</a>
                <a class="btn" style="margin-left:8px;background:#2f3146;" href="/logout">Выйти</a>
            </div>
        </div>
        <h1>Кабинет кандидата</h1>
        <p class="subtitle">Короткий лендинг со статусом аккаунта и инструментом анализа резюме.</p>

        <section>
            <h2>Анализ своего резюме</h2>
            <form method="post" action="/candidate/analyze" enctype="multipart/form-data">
                {% if form_error %}
                <div class="error">{{ form_error }}</div>
                {% endif %}
                <div>
                    <label for="resume_file">Загрузите резюме (PDF или DOCX)</label>
                    <input type="file" id="resume_file" name="resume_file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required />
                    <p class="hint">Файл хранится локально и используется только для анализа.</p>
                </div>
                <div style="margin-top:16px;">
                    <label for="job_text">Опишите вакансию мечты</label>
                    <textarea id="job_text" name="job_text" required>{{ form_data.job_text }}</textarea>
                    <p class="hint">Укажите ключевые обязанности и стек — это увидят HR и модель.</p>
                </div>
                <button class="btn" type="submit" style="margin-top:18px;">Получить анализ</button>
                <p class="hint" style="margin-top:10px;">Анализ выполняется реальной моделью gpt-oss:20b-cloud при доступности, иначе используем локальный алгоритм.</p>
            </form>
            {% if analysis %}
            <div class="result-card">
                <h3>Результат: {{ analysis.score }}%</h3>
                <p>{{ analysis.summary }}</p>
                <p class="badge">Совпадения: {{ analysis.matched|length }}</p>
                {% if analysis.matched %}
                <p>Ключевые совпадения: {{ analysis.matched|join(', ') }}</p>
                {% endif %}
                {% if analysis.missing %}
                <p>Стоит добавить: {{ analysis.missing|join(', ') }}</p>
                {% endif %}
                <p class="hint">Источник: {{ 'LLM gpt-oss:20b-cloud' if analysis.engine == 'llm' else 'эвристический поиск по резюме' }}.</p>
            </div>
            {% endif %}
        </section>

        <section>
            <h2>История последних анализов</h2>
            <p class="hint">После первого успешного анализа профиль появится в поиске HR.</p>
            {% if history %}
                {% for item in history %}
                <div class="history-item">
                    <strong>{{ item.score }}%</strong> · {{ item.created_at }}
                    <p style="color:#a8aecb;">{{ item.job_focus[:180] }}{% if item.job_focus|length > 180 %}...{% endif %}</p>
                    <p class="hint">Источник анализа: {{ 'LLM' if item.engine == 'llm' else 'heuristic' }}</p>
                </div>
                {% endfor %}
            {% else %}
                <p>Вы ещё не запускали анализ профиля.</p>
            {% endif %}
        </section>
    </div>
</body>
</html>
"""


HR_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Кабинет HR — HR Agent</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #05060a; color: #f5f6fb; margin: 0; }
        .page { max-width: 1080px; margin: 0 auto; padding: 30px 20px 60px; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .btn { border: none; padding: 10px 18px; border-radius: 999px; cursor: pointer; background: linear-gradient(120deg, #6f6af8, #8f83ff); color: #fff; }
        section { background: rgba(17,20,37,0.95); border-radius: 20px; padding: 24px; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 24px; }
        input {
            width: 100%; padding: 12px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03); color: #fff;
        }
        label { font-size: 0.9rem; color: #a8aecb; }
        form { display: grid; gap: 14px; margin-bottom: 16px; }
        .candidate-card { border-top: 1px solid rgba(255,255,255,0.08); padding: 16px 0; }
        .candidate-card:first-child { border-top: none; }
        .score { font-size: 1.4rem; color: #4ade80; }
        .muted { color: #a8aecb; font-size: 0.95rem; }
        .profile-button {
            width: 38px;
            height: 38px;
            border-radius: 50%;
            border: 1px solid rgba(255,255,255,0.15);
            background: #2f3146;
            color: #c5c8ff;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="page">
        <div class="top-nav">
            <div>HR Agent · {{ user.name }} ({{ user.org_type or 'HR' }})</div>
            <div>
                <a class="btn" href="/">На лендинг</a>
                <a class="profile-button" style="margin-left:8px;" href="/profile">{{ user.name[:1]|upper }}</a>
                <a class="btn" style="margin-left:8px;background:#2f3146;" href="/logout">Выйти</a>
            </div>
        </div>
        <h1>Кабинет HR специалиста</h1>
        <p class="muted" style="margin-bottom:20px;">Поиск и сравнение кандидатов по данным анализа.</p>

        <section>
            <h2>Поиск кандидатов</h2>
            <form method="get" action="/hr/dashboard">
                <div>
                    <label for="keyword">Ключевые навыки или стек</label>
                    <input type="text" id="keyword" name="keyword" value="{{ keyword }}" placeholder="Go, Python, product..." />
                </div>
                <div>
                    <label for="name">Имя кандидата</label>
                    <input type="text" id="name" name="name" value="{{ search_name }}" placeholder="Введите имя" />
                </div>
                <button class="btn" type="submit" style="margin-top:10px;">Найти</button>
            </form>

            {% if results %}
                {% for item in results %}
                <div class="candidate-card">
                    <div class="score">{{ item.score }}%</div>
                    <strong>{{ item.user_name }}</strong> · {{ item.email }}
                    <p class="muted">Фокус роли: {{ item.job_focus[:200] }}{% if item.job_focus|length > 200 %}...{% endif %}</p>
                    {% if item.matched_keywords %}
                    <p>Совпадения: {{ item.matched_keywords }}</p>
                    {% endif %}
                    {% if item.missing_keywords %}
                    <p class="muted">Нужно усилить: {{ item.missing_keywords }}</p>
                    {% endif %}
                    <p class="muted">Источник: {{ 'LLM' if item.engine == 'llm' else 'heuristic' }}</p>
                    <p class="muted">Создано: {{ item.created_at }}</p>
                </div>
                {% endfor %}
            {% else %}
                <p>Нет результатов. Попробуйте изменить фильтры.</p>
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
    <title>Профиль — HR Agent</title>
    <style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #05060a; color: #f5f6fb; margin: 0; }
        .page { max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }
        .card { background: rgba(17,20,37,0.95); border-radius: 24px; padding: 28px; border: 1px solid rgba(255,255,255,0.08); box-shadow: 0 25px 60px rgba(0,0,0,0.35); }
        label { display: block; margin-bottom: 6px; color: #a8aecb; font-size: 0.9rem; }
        input, select {
            width: 100%; padding: 14px; border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.04); color: #fff;
        }
        form { display: grid; gap: 18px; }
        .btn {
            border: none; padding: 12px 22px; border-radius: 999px;
            background: linear-gradient(120deg, #6f6af8, #8f83ff); color: #fff; cursor: pointer;
        }
        .status { color: #4ade80; margin-bottom: 16px; }
        .error { color: #f87171; margin-bottom: 16px; }
        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        .profile-button {
            width: 38px; height: 38px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.15);
            display: inline-flex; align-items: center; justify-content: center; color: #c5c8ff; background: #2f3146;
            text-decoration: none; font-weight: 600;
        }
        .links a { color: #a8aecb; text-decoration: none; margin-right: 16px; font-size: 0.95rem; }
    </style>
</head>
<body>
    <div class="page">
        <div class="top-nav">
            <div class="links">
                <a href="{{ '/candidate/dashboard' if user.role == 'candidate' else '/hr/dashboard' }}">Вернуться в кабинет</a>
                <a href="/">Лендинг</a>
            </div>
            <a class="profile-button" href="/profile">{{ user.name[:1]|upper }}</a>
        </div>
        <div class="card">
            <h1 style="margin-bottom:6px;">Профиль пользователя</h1>
            <p style="color:#a8aecb;margin-bottom:18px;">Роль: {{ 'Кандидат' if user.role == 'candidate' else 'HR специалист' }}</p>
            {% if status %}
            <div class="status">{{ status }}</div>
            {% endif %}
            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}
            <form method="post">
                <div>
                    <label for="name">Имя</label>
                    <input type="text" id="name" name="name" value="{{ user.name }}" required />
                </div>
                <div>
                    <label for="email">Рабочая почта</label>
                    <input type="email" id="email" name="email" value="{{ user.email }}" required />
                </div>
                {% if user.role == 'hr' %}
                <div>
                    <label for="org_type">Тип организации</label>
                    <select id="org_type" name="org_type">
                        <option value="" {% if not user.org_type %}selected{% endif %}>—</option>
                        <option value="startup" {% if user.org_type == 'startup' %}selected{% endif %}>Стартап</option>
                        <option value="company" {% if user.org_type == 'company' %}selected{% endif %}>Компания</option>
                    </select>
                </div>
                {% endif %}
                <div>
                    <label for="new_password">Новый пароль (по желанию)</label>
                    <input type="password" id="new_password" name="new_password" minlength="6" />
                </div>
                <div>
                    <label for="confirm_password">Подтверждение пароля</label>
                    <input type="password" id="confirm_password" name="confirm_password" minlength="6" />
                </div>
                <button class="btn" type="submit">Сохранить</button>
            </form>
        </div>
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
        form { display:grid; gap:18px; }
        .btn { border:none; padding:12px 22px; border-radius:999px; background:linear-gradient(120deg,#6f6af8,#8f83ff); color:#fff; cursor:pointer; }
        .error { color:#f87171; min-height:18px; }
    </style>
</head>
<body>
    <div class="card">
        <h1 style="margin-bottom:6px;">Admin панель</h1>
        <p style="color:#a8aecb;margin-bottom:18px;">Войдите, чтобы посмотреть аналитику.</p>
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
        a { color:#c5c8ff; text-decoration:none; }
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
                <span>Всего посещений</span>
                <strong>{{ stats.visits }}</strong>
            </div>
            <div class="card">
                <span>Регистраций всего</span>
                <strong>{{ stats.total_users }}</strong>
            </div>
            <div class="card">
                <span>Кандидатов</span>
                <strong>{{ stats.total_candidates }}</strong>
            </div>
            <div class="card">
                <span>HR специалистов</span>
                <strong>{{ stats.total_hr }}</strong>
            </div>
            <div class="card">
                <span>Анализов профиля</span>
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
    "hr": env.from_string(HR_TEMPLATE),
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


def build_context(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metrics = get_metrics()
    return {
        "meta": {
            "title": APP_TITLE,
            "description": "HR Agent соединяет IT-специалистов и HR-команды через точный анализ резюме и вакансий.",
        },
        "hero": {
            "tagline": choose_tagline(),
            "subtitle": "Кандидат загружает PDF-резюме, описывает роль мечты и сразу видит, насколько он совпадает с запросом. HR-команды получают ранжированный список и объяснения сопоставлений.",
        },
        "candidate_features": [
            {"title": "Мгновенная оценка", "text": "Процент совпадения с ролью и подсветка сильных сторон."},
            {"title": "Рекомендации по росту", "text": "Понимайте, какие навыки усилить, чтобы пройти отбор."},
            {"title": "Один профиль для откликов", "text": "Сохраняйте резюме, мотивацию и ссылки в одном месте."},
            {"title": "История анализа", "text": "Возвращайтесь к прошлым результатам и отслеживайте прогресс."},
        ],
        "hr_features": [
            {"title": "Поиск кандидатов по навыкам", "text": "Фильтрация по ключевым словам и проценту совпадения."},
            {"title": "Объяснимые оценки", "text": "Каждый результат сопровождается совпавшими и отсутствующими навыками."},
            {"title": "Контроль воронки", "text": "На каком этапе застревают роли и почему."},
            {"title": "Единая база", "text": "Все заявки и заметки хранятся централизованно в HR Agent."},
        ],
        "metrics": metrics,
        "timeline": [
            {"number": "01", "title": "Загрузка резюме", "text": "Кандидат добавляет PDF или текст и описывает цель."},
            {"number": "02", "title": "Анализ профиля", "text": "Сервис извлекает навыки и сопоставляет с ожиданиями роли."},
            {"number": "03", "title": "Передача HR", "text": "HR получает готовый разбор и рейтинг совпадения."},
        ],
        "faq": [
            {"q": "Кто может присоединиться?", "a": "IT-специалисты и HR-команды продуктовых и сервисных компаний."},
            {"q": "Когда стартует бета?", "a": "Первые приглашения отправим в течение ближайших недель после подтверждения нагрузки."},
            {"q": "Сколько это стоит?", "a": "На этапе раннего доступа сервис бесплатный."},
            {"q": "Как храните данные?", "a": "Резюме и профили шифруются и доступны только командам, которым кандидат дал доступ."},
        ],
        "user": user,
    }


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    increment_counter("visits")
    html = render_template("landing", **build_context(user))
    return HTMLResponse(content=html)


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if user:
        target = "/candidate/dashboard" if user["role"] == "candidate" else "/hr/dashboard"
        return RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)
    html = render_template(
        "auth",
        title="Регистрация — HR Agent",
        heading="Создать аккаунт",
        subtitle="Выберите роль и получите доступ к закрытому запуску.",
        mode="register",
        error=None,
        success=None,
        submit_label="Зарегистрироваться",
        form_data={"name": "", "email": "", "role": "candidate", "org_type": ""},
    )
    return HTMLResponse(content=html)


@app.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if user:
        target = "/candidate/dashboard" if user["role"] == "candidate" else "/hr/dashboard"
        return RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    role = form.get("role", "candidate")
    org_type = form.get("org_type", "").strip() or None
    error = None
    if len(name) < 2:
        error = "Имя слишком короткое."
    elif len(password) < 6:
        error = "Пароль должен быть не короче 6 символов."
    user_id = None
    if not error:
        try:
            user_id = create_user(name, email, password, role, org_type)
        except ValueError as exc:
            error = str(exc)
    if error:
        html = render_template(
            "auth",
            title="Регистрация — HR Agent",
            heading="Создать аккаунт",
            subtitle="Выберите роль и получите доступ к закрытому запуску.",
            mode="register",
            error=error,
            success=None,
            submit_label="Зарегистрироваться",
            form_data={"name": name, "email": email, "role": role, "org_type": org_type or ""},
        )
        return HTMLResponse(content=html, status_code=400)
    request.session["user_id"] = user_id
    request.session["role"] = role
    target = "/candidate/dashboard" if role == "candidate" else "/hr/dashboard"
    return RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    next_url = request.query_params.get("next")
    if user:
        target = next_url or ("/candidate/dashboard" if user["role"] == "candidate" else "/hr/dashboard")
        return RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)
    html = render_template(
        "auth",
        title="Вход — HR Agent",
        heading="Войти в аккаунт",
        subtitle="Используйте почту, с которой регистрировались.",
        mode="login",
        error=None,
        success=None,
        submit_label="Войти",
        form_data={"name": "", "email": ""},
    )
    return HTMLResponse(content=html)


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request) -> HTMLResponse:
    form = await request.form()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    next_url = request.query_params.get("next")
    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        html = render_template(
            "auth",
            title="Вход — HR Agent",
            heading="Войти в аккаунт",
            subtitle="Используйте почту, с которой регистрировались.",
            mode="login",
            error="Неверная почта или пароль.",
            success=None,
            submit_label="Войти",
            form_data={"name": "", "email": email},
        )
        return HTMLResponse(content=html, status_code=401)
    request.session["user_id"] = user["id"]
    request.session["role"] = user["role"]
    target = next_url or ("/candidate/dashboard" if user["role"] == "candidate" else "/hr/dashboard")
    return RedirectResponse(target, status_code=HTTP_303_SEE_OTHER)


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
    name = form.get("name", user["name"]).strip()
    email = form.get("email", user["email"]).strip()
    org_type = form.get("org_type", user.get("org_type")) if user["role"] == "hr" else None
    new_password = form.get("new_password", "").strip()
    confirm_password = form.get("confirm_password", "").strip()
    error = None
    status = None
    if len(name) < 2:
        error = "Имя должно содержать минимум 2 символа."
    elif not email:
        error = "Почта не может быть пустой."
    elif new_password and len(new_password) < 6:
        error = "Пароль должен быть не короче 6 символов."
    elif new_password and new_password != confirm_password:
        error = "Пароли не совпадают."
    if not error:
        try:
            updated = update_user_profile(
                user["id"],
                name=name,
                email=email,
                org_type=org_type if user["role"] == "hr" else None,
                new_password=new_password or None,
            )
            request.session["user_id"] = updated["id"]
            request.session["role"] = updated["role"]
            user = updated
            status = "Профиль обновлён."
        except ValueError as exc:
            error = str(exc)
    html = render_template("profile", user=user, error=error, status=status)
    return HTMLResponse(content=html, status_code=400 if error else 200)


@app.get("/admin", response_class=HTMLResponse)
async def admin_login_page(request: Request) -> HTMLResponse:
    if request.session.get("admin_authenticated"):
        return RedirectResponse("/admin/dashboard", status_code=HTTP_303_SEE_OTHER)
    html = render_template("admin_login", error=None)
    return HTMLResponse(content=html)


@app.post("/admin", response_class=HTMLResponse)
async def admin_login_submit(request: Request) -> HTMLResponse:
    if request.session.get("admin_authenticated"):
        return RedirectResponse("/admin/dashboard", status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    error = None
    if username != ADMIN_USERNAME or not verify_admin(password):
        error = "Неверный логин или пароль."
    if error:
        html = render_template("admin_login", error=error)
        return HTMLResponse(content=html, status_code=401)
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


@app.get("/candidate/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user or user["role"] != "candidate":
        return RedirectResponse("/login?next=/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    history = get_candidate_history(user["id"])
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
async def candidate_analyze(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user or user["role"] != "candidate":
        return RedirectResponse("/login?next=/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    job_text = form.get("job_text", "").strip()
    resume_file = form.get("resume_file")
    resume_text = await upload_to_text(resume_file if isinstance(resume_file, StarletteUploadFile) else None)
    form_error = None
    if not resume_text:
        form_error = "Добавьте файл резюме в формате PDF или DOCX."
    elif not job_text:
        form_error = "Опишите вакансию, чтобы мы могли выполнить сравнение."
    if form_error:
        history = get_candidate_history(user["id"])
        html = render_template(
            "candidate",
            user=user,
            analysis=None,
            history=history,
            form_data={"job_text": job_text},
            form_error=form_error,
        )
        return HTMLResponse(content=html, status_code=400)
    analysis = analyze_with_llm(resume_text, job_text) or simple_resume_analysis(resume_text, job_text)
    save_candidate_submission(
        user["id"],
        resume_text,
        job_text,
        analysis["matched"],
        analysis["missing"],
        analysis["score"],
        analysis.get("engine", "heuristic"),
    )
    history = get_candidate_history(user["id"])
    html = render_template(
        "candidate",
        user=user,
        analysis=analysis,
        history=history,
        form_data={"job_text": ""},
        form_error=None,
    )
    return HTMLResponse(content=html)


@app.get("/hr/dashboard", response_class=HTMLResponse)
async def hr_dashboard(request: Request, keyword: Optional[str] = None, name: Optional[str] = None) -> HTMLResponse:
    user = get_current_user(request)
    if not user or user["role"] != "hr":
        return RedirectResponse("/login?next=/hr/dashboard", status_code=HTTP_303_SEE_OTHER)
    results = search_candidate_submissions(keyword, name)
    html = render_template(
        "hr",
        user=user,
        results=results,
        keyword=keyword or "",
        search_name=name or "",
    )
    return HTMLResponse(content=html)


@app.post("/api/interest")
async def collect_interest(payload: InterestPayload) -> JSONResponse:
    lead_data = payload.dict()
    lead_data["interest_score"] = 90 if payload.role == "candidate" else 80
    lead_id = store_lead(lead_data)
    return JSONResponse(
        {
            "status": "ok",
            "lead_id": lead_id,
            "message": "Спасибо! Мы напишем, как только стартует доступ.",
        }
    )


@app.get("/api/metrics")
async def metrics_endpoint() -> Dict[str, int]:
    return get_metrics()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("hr_agent:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
