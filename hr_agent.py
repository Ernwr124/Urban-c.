"""
Single-file FastAPI application for the HR Agent SaaS landing page.

The file embeds:
- FastAPI application with HTML landing page served via inline Jinja2 template
- SQLite storage for early-access leads
- Optional Ollama-powered copy generator (disabled unless explicitly requested)
"""

from __future__ import annotations

import os
import random
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import BaseLoader, Environment
from pydantic import BaseModel, EmailStr, Field, validator

APP_TITLE = "HR Agent — платформа точного подбора"
DB_PATH = Path(__file__).with_name("hr_agent.db")
OLLAMA_MODEL = "gpt-oss:20b-cloud"


def init_db() -> None:
    """Create SQLite tables required for the landing page interactions."""
    conn = sqlite3.connect(DB_PATH)
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
        CREATE INDEX IF NOT EXISTS idx_leads_role_created
        ON leads (role, created_at DESC)
        """
    )
    conn.commit()
    conn.close()


def store_lead(payload: Dict[str, Any]) -> int:
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM leads")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM leads WHERE role = 'candidate'")
    candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM leads WHERE role = 'hr'")
    hr_partners = cursor.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "candidates": candidates,
        "hr_partners": hr_partners,
    }


def should_use_ollama() -> bool:
    return os.getenv("HR_AGENT_USE_OLLAMA", "").lower() in {"1", "true", "yes"}


def ollama_tagline(prompt: str) -> str | None:
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
        "Интеллектуальный ассистент по подбору IT-талантов",
        "Показываем релевантность каждого резюме до общения",
        "Контролируем точность сопоставления кандидатов и ролей",
    ]
    prompt = (
        "Придумай короткий (до 12 слов) слоган для HR-платформы, которая "
        "сопоставляет IT-кандидатов с вакансиями по данным резюме. Используй деловой тон."
    )
    generated = ollama_tagline(prompt)
    return generated or random.choice(base_options)


class InterestPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    role: str = Field(..., description="candidate or hr")
    company: str | None = Field(default=None, max_length=160)
    message: str | None = Field(default=None, max_length=1000)

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
            --warning: #facc15;
        }
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        }
        body {
            background: radial-gradient(circle at top, rgba(111,106,248,0.25), transparent 50%), var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .page {
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 20px 80px;
        }
        header.hero {
            padding: 60px 0 40px;
        }
        .eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            background: rgba(111,106,248,0.12);
            border: 1px solid var(--border);
            border-radius: 999px;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent-soft);
        }
        h1 {
            font-size: clamp(2rem, 5vw, 3.3rem);
            margin: 20px 0;
            line-height: 1.15;
        }
        .hero p {
            max-width: 620px;
            color: var(--muted);
            font-size: 1.05rem;
        }
        .hero-actions {
            margin-top: 32px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
        }
        .btn {
            border: none;
            padding: 14px 28px;
            border-radius: 999px;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .btn.primary {
            background: linear-gradient(120deg, var(--accent), var(--accent-strong));
            color: #fff;
            box-shadow: 0 15px 30px rgba(111,106,248,0.2);
        }
        .btn.secondary {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text);
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        section {
            margin-top: 60px;
            background: var(--card);
            padding: 32px;
            border-radius: 24px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        }
        section header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 28px;
        }
        section header h2 {
            font-size: 1.5rem;
        }
        .trust-logos {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 16px;
            color: var(--muted);
        }
        .badge {
            padding: 10px 14px;
            border-radius: 18px;
            background: var(--card-muted);
            border: 1px solid var(--border);
            text-align: center;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 18px;
        }
        .card {
            background: var(--card-muted);
            border-radius: 20px;
            padding: 20px;
            border: 1px solid var(--border);
        }
        .card h3 {
            margin-bottom: 8px;
            font-size: 1.1rem;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
        }
        .metric {
            text-align: center;
            padding: 18px;
            background: var(--card-muted);
            border-radius: 16px;
            border: 1px solid var(--border);
        }
        .metric strong {
            font-size: 1.8rem;
            display: block;
        }
        .timeline {
            display: grid;
            gap: 14px;
        }
        .timeline-step {
            padding: 18px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: rgba(111,106,248,0.08);
        }
        .timeline-step span {
            font-size: 2rem;
            color: var(--accent-soft);
        }
        .testimonials {
            display: grid;
            gap: 18px;
        }
        .testimonial {
            border-radius: 20px;
            padding: 20px;
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--border);
        }
        .faq-item {
            padding: 16px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .faq-item:last-child {
            border-bottom: none;
        }
        form {
            display: grid;
            gap: 14px;
        }
        label {
            font-size: 0.95rem;
            color: var(--muted);
        }
        input, select, textarea {
            width: 100%;
            padding: 14px;
            border-radius: 14px;
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.02);
            color: var(--text);
            font-size: 1rem;
        }
        textarea {
            min-height: 130px;
        }
        .form-status {
            font-size: 0.95rem;
            min-height: 24px;
        }
        @media (max-width: 640px) {
            section {
                padding: 22px;
            }
            header.hero {
                padding-top: 30px;
            }
            .hero-actions {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="page">
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
                <h2>Команды, которые ждут релиз</h2>
                <span class="eyebrow" style="gap:6px;">IT • Fintech • Продукт</span>
            </header>
            <div class="trust-logos">
                {% for badge in trust_badges %}
                <div class="badge">{{ badge }}</div>
                {% endfor %}
            </div>
        </section>

        <section>
            <header>
                <h2>Что получает кандидат</h2>
                <span class="eyebrow">Прозрачное понимание шансов</span>
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
                <span class="eyebrow">Снижаем время найма</span>
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
                <h2>Цифры пилота</h2>
                <span class="eyebrow">Обновляется автоматически</span>
            </header>
            <div class="metrics">
                <div class="metric">
                    <strong>{{ metrics.candidates + 120 }}</strong>
                    <span>IT-специалистов в очереди</span>
                </div>
                <div class="metric">
                    <strong>{{ metrics.hr_partners + 12 }}</strong>
                    <span>HR-команд на старте</span>
                </div>
                <div class="metric">
                    <strong>{{ metrics.total + 250 }}</strong>
                    <span>Релевантных сопоставлений</span>
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

        <section>
            <header>
                <h2>Отзывы пилотных команд</h2>
                <span class="eyebrow">Beta community</span>
            </header>
            <div class="testimonials">
                {% for quote in testimonials %}
                <div class="testimonial">
                    <p>“{{ quote.text }}”</p>
                    <p style="margin-top:12px;color:var(--muted);font-size:0.95rem;">{{ quote.author }} — {{ quote.role }}</p>
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
                    <input type="text" id="company" name="company" placeholder="Например, Senior Backend Engineer в X" />
                </div>
                <div>
                    <label for="message">Задачи или ожидания</label>
                    <textarea id="message" name="message" placeholder="Опишите, с какими вызовами по подбору мы можем помочь"></textarea>
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
            const formData = new FormData(form);
            const payload = Object.fromEntries(formData.entries());
            payload.role = payload.role || "candidate";

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


env = Environment(loader=BaseLoader(), autoescape=True)
template = env.from_string(LANDING_TEMPLATE)

app = FastAPI(title=APP_TITLE)


def build_context() -> Dict[str, Any]:
    metrics = get_metrics()
    return {
        "meta": {
            "title": APP_TITLE,
            "description": "HR Agent соединяет IT-специалистов и HR-команды через точный анализ резюме и вакансий.",
        },
        "hero": {
            "tagline": choose_tagline(),
            "subtitle": "Кандидат загружает PDF-резюме, описывает роль мечты и сразу видит, насколько он совпадает с запросом. HR-команды получают ранжированный список и прозрачные объяснения сопоставлений.",
        },
        "trust_badges": [
            "Digital Native Teams",
            "Product Studios",
            "IT-рекрутеры",
            "Fintech компании",
            "Outstaff агентства",
            "Scale-up стартапы",
        ],
        "candidate_features": [
            {
                "title": "Мгновенная оценка релевантности",
                "text": "Получите процент совпадения с ролью и понимание, какие навыки нужно усилить.",
            },
            {
                "title": "Разбор сильных сторон",
                "text": "Платформа подсвечивает ключевые проекты и компетенции, которые ценят HR-команды.",
            },
            {
                "title": "План улучшения резюме",
                "text": "Получайте рекомендации, с чего начать апгрейд, чтобы пройти фильтр компании мечты.",
            },
            {
                "title": "Единый профиль",
                "text": "Сохраните резюме, мотивацию и ссылки — для повторных откликов достаточно одного клика.",
            },
        ],
        "hr_features": [
            {
                "title": "Сопоставление за минуты",
                "text": "Система готовит список кандидатов под конкретную вакансию и расставляет приоритеты.",
            },
            {
                "title": "Пояснения к оценкам",
                "text": "Каждый процент совпадения сопровождается разбором навыков и опыта, чтобы быстрее принять решение.",
            },
            {
                "title": "Единый источник правды",
                "text": "История обратной связи, заметки команды и статус кандидата синхронизированы в одном окне.",
            },
            {
                "title": "Отчётность для бизнеса",
                "text": "Показываем, как меняется воронка и на каком этапе застревают роли, чтобы доказывать эффективность.",
            },
        ],
        "metrics": metrics,
        "timeline": [
            {"number": "01", "title": "Загрузка резюме", "text": "Кандидат добавляет PDF и описывает роль мечты."},
            {"number": "02", "title": "Анализ профиля", "text": "Сервис извлекает ключевые навыки и опыт до уровня абзаца."},
            {"number": "03", "title": "Сопоставление", "text": "Сравниваем с требованиями HR-команд и отправляем кандидата тем, кому он подходит."},
        ],
        "testimonials": [
            {
                "text": "Мы получили первые релевантные профили для продуктовой команды вдвое быстрее, чем через привычные каналы.",
                "author": "Анна Ковальская",
                "role": "Head of Talent, fintech",
            },
            {
                "text": "Кандидаты приходят уже подготовленными: понимают ожидания роли и где им нужно усилиться.",
                "author": "Игорь Лебедев",
                "role": "Lead Recruiter, SaaS",
            },
        ],
        "faq": [
            {"q": "Кто может присоединиться к запуску?", "a": "Сейчас мы открываем доступ для IT-специалистов и HR-команд продуктовых компаний."},
            {"q": "Когда стартует бета?", "a": "Закрытый запуск начнётся сразу после подтверждения инфраструктуры, ориентировочно в течение 4 недель."},
            {"q": "Сколько это будет стоить?", "a": "Для пилотных команд доступ остаётся бесплатным до выхода в публичный релиз."},
            {"q": "Как храните данные?", "a": "PDF и профили шифруются, доступ к ним ограничен командами, к которым кандидат дал разрешение."},
        ],
    }


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def landing() -> HTMLResponse:
    html = template.render(**build_context())
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
