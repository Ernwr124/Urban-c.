from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import auth
from app.services.analytics import increment_counter

router = APIRouter()


AUTH_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
        body {{
            font-family:'Inter',system-ui,sans-serif;
            background:#0f0f0f;
            color:#ffffff;
            margin:0;
            display:flex;
            justify-content:center;
            align-items:center;
            min-height:100vh;
        }}
        .card {{
            width:min(420px,90%);
            background:#141414;
            border:1px solid rgba(255,255,255,0.1);
            border-radius:24px;
            padding:32px;
        }}
        label {{ display:block; margin-bottom:6px; color:rgba(255,255,255,0.7); }}
        input {{
            width:100%; padding:14px; border-radius:14px;
            border:1px solid rgba(255,255,255,0.2);
            background:#0f0f0f; color:#fff; margin-bottom:16px;
        }}
        button {{
            width:100%; padding:12px; border:none; border-radius:14px;
            background:#2563eb; color:#fff; font-weight:600; cursor:pointer;
        }}
        .error {{ color:#f87171; min-height:20px; margin-bottom:10px; }}
        a {{ color:#2563eb; text-decoration:none; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{heading}</h1>
        <p>{subtitle}</p>
        <div class="error">{error}</div>
        <form method="post">
            {extra_fields}
            <label for="email">Почта</label>
            <input type="email" id="email" name="email" value="{email}" required />
            <label for="password">Пароль</label>
            <input type="password" id="password" name="password" minlength="6" required />
            <button type="submit">{button}</button>
        </form>
        <p style="margin-top:12px;">{footer}</p>
    </div>
</body>
</html>
"""


def render_auth(mode: str, error: str = "", name: str = "", email: str = "") -> HTMLResponse:
    if mode == "register":
        extra = (
            '<label for="name">Имя</label>'
            f'<input type="text" id="name" name="name" value="{name}" required />'
        )
        footer = 'Уже есть аккаунт? <a href="/login">Войти</a>'
        html = AUTH_TEMPLATE.format(
            title="Регистрация — HR Agent",
            heading="Создать аккаунт",
            subtitle="Получайте честный анализ резюме.",
            error=error,
            extra_fields=extra,
            email=email,
            button="Зарегистрироваться",
            footer=footer,
        )
        return HTMLResponse(html, status_code=400 if error else 200)
    extra = ""
    footer = 'Нет аккаунта? <a href="/register">Зарегистрироваться</a>'
    html = AUTH_TEMPLATE.format(
        title="Вход — HR Agent",
        heading="Войти",
        subtitle="Продолжайте работу с анализами.",
        error=error,
        extra_fields=extra,
        email=email,
        button="Войти",
        footer=footer,
    )
    return HTMLResponse(html, status_code=400 if error else 200)


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    return render_auth("register")


@router.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    if len(password) < 6 or len(name.strip()) < 2:
        return render_auth("register", "Проверьте имя и пароль.", name=name, email=email)
    try:
        user_id = auth.create_user(name, email, password)
    except ValueError as exc:
        return render_auth("register", str(exc), name=name, email=email)
    request.session["user_id"] = user_id
    increment_counter("registrations")
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    if request.session.get("user_id"):
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    return render_auth("login")


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    user = auth.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return render_auth("login", "Неверная почта или пароль.", email=email)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
