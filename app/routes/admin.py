from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.analytics import get_counter

router = APIRouter(prefix="/admin", tags=["admin"])


ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Admin — HR Agent</title>
    <style>
        body {{ font-family:'Inter',system-ui,sans-serif; background:#0f0f0f; color:#fff; margin:0; }}
        .page {{ max-width:900px; margin:0 auto; padding:40px 20px; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:18px; }}
        .card {{ background:#141414; padding:24px; border-radius:20px; border:1px solid rgba(255,255,255,0.08); }}
        .card span {{ display:block; color:rgba(255,255,255,0.6); margin-bottom:6px; }}
        a {{ color:#2563eb; text-decoration:none; }}
    </style>
</head>
<body>
    <div class="page">
        <h1>Админ-панель</h1>
        <div class="grid">
            <div class="card">
                <span>Визитов</span>
                <strong>{{ visits }}</strong>
            </div>
            <div class="card">
                <span>Регистраций</span>
                <strong>{{ registrations }}</strong>
            </div>
            <div class="card">
                <span>Всего анализов</span>
                <strong>{{ analyses }}</strong>
            </div>
        </div>
        <p style="margin-top:24px;"><a href="/">На сайт</a></p>
    </div>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    if not request.session.get("admin_authenticated"):
        return HTMLResponse("Доступ запрещён", status_code=403)
    html = ADMIN_TEMPLATE.replace("{{ visits }}", str(get_counter("visits"))).replace(
        "{{ registrations }}", str(get_counter("registrations"))
    ).replace("{{ analyses }}", str(get_counter("analyses")))
    return HTMLResponse(html)
