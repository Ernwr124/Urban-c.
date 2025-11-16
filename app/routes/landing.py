from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.analytics import increment_counter
from app.utils.session import current_user

router = APIRouter()


def render_landing(user: dict | None) -> str:
    auth_block = (
        '<a class="btn secondary" href="/candidate/dashboard">Кабинет</a>'
        '<a class="btn secondary" href="/logout">Выйти</a>'
    )
    if not user:
        auth_block = (
            '<a class="btn secondary" href="/login">Войти</a>'
            '<a class="btn primary" href="/register">Регистрация</a>'
        )
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>HR Agent</title>
        <style>
            :root {{
                --black: #0f0f0f;
                --white: #ffffff;
                --accent: #2563eb;
                --gray: #1f1f1f;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: 'Inter', system-ui, sans-serif;
                background: var(--black);
                color: var(--white);
            }}
            .page {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 40px 20px 80px;
            }}
            .top-nav {{
                display:flex;
                justify-content:space-between;
                align-items:center;
                margin-bottom:30px;
            }}
            .logo {{ letter-spacing:0.08em; font-weight:600; }}
            .btn {{
                border:none;
                padding:10px 20px;
                border-radius:999px;
                cursor:pointer;
                text-decoration:none;
                font-weight:500;
            }}
            .btn.primary {{ background:var(--accent); color:var(--white); }}
            .btn.secondary {{
                background:transparent;
                border:1px solid rgba(255,255,255,0.2);
                color:var(--white);
            }}
            section {{
                background:var(--gray);
                padding:30px;
                border-radius:24px;
                border:1px solid rgba(255,255,255,0.1);
                margin-bottom:24px;
            }}
            h1 {{ font-size:clamp(2.2rem,4vw,3.4rem); margin-bottom:16px; }}
            p {{ color:rgba(255,255,255,0.7); line-height:1.6; }}
            .grid {{
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
                gap:18px;
            }}
            .card {{
                background:#111;
                border:1px solid rgba(255,255,255,0.08);
                padding:18px;
                border-radius:18px;
            }}
            ul {{ padding-left:18px; color:rgba(255,255,255,0.8); }}
        </style>
    </head>
    <body>
        <div class="page">
            <nav class="top-nav">
                <div class="logo">HR AGENT</div>
                <div>{auth_block}</div>
            </nav>
            <section>
                <h1>Платформа анализа резюме и вакансий</h1>
                <p>HR Agent помогает IT-специалистам сравнивать своё резюме с реальными вакансиями. Загружайте PDF/DOCX/PNG/JPG,
                подключайте Ollama Cloud и получайте план развития, рекомендации и готовые отчёты.</p>
                <div style="margin-top:20px;">
                    <a class="btn primary" href="/register">Начать бесплатно</a>
                    <a class="btn secondary" href="#features">Узнать подробнее</a>
                </div>
            </section>
            <section id="features">
                <h2>Возможности</h2>
                <div class="grid">
                    <div class="card">
                        <h3>Глубокий парсинг</h3>
                        <p>Поддержка PDF, DOCX и изображений. Текст очищается и готовится для AI-сравнения.</p>
                    </div>
                    <div class="card">
                        <h3>Ollama Cloud</h3>
                        <p>Модель gpt-oss:20b-cloud анализирует навыки, опыт и образование без галлюцинаций.</p>
                    </div>
                    <div class="card">
                        <h3>Внешние источники</h3>
                        <p>Через DuckDuckGo подтягиваем свежие вакансии и требования рынка.</p>
                    </div>
                    <div class="card">
                        <h3>Планы развития</h3>
                        <p>Авто-рекомендации курсов и шаги для роста, если совпадение ниже 70%.</p>
                    </div>
                </div>
            </section>
            <section>
                <h2>Быстрый старт</h2>
                <ul>
                    <li>Зарегистрируйтесь и загрузите резюме</li>
                    <li>Вставьте описание вакансии мечты</li>
                    <li>Получите match score и полный отчёт</li>
                    <li>Скачайте выводы в JSON, DOCX или XLSX</li>
                </ul>
            </section>
        </div>
    </body>
    </html>
    """


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request) -> HTMLResponse:
    increment_counter("visits")
    user = current_user(request)
    return HTMLResponse(render_landing(user))
