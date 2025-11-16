from __future__ import annotations

import io
import json
from typing import List

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.services import analysis as analysis_service
from app.services import auth
from app.services.files import read_upload
from app.utils.session import current_user

router = APIRouter(prefix="/candidate", tags=["candidate"])


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Кабинет кандидата</title>
    <style>
        body {{ font-family:'Inter',system-ui,sans-serif; background:#0f0f0f; color:#fff; margin:0; }}
        .page {{ max-width:1100px; margin:0 auto; padding:30px 20px 80px; }}
        .top-nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }}
        .btn {{
            padding:10px 18px; border-radius:999px; border:1px solid rgba(255,255,255,0.2);
            color:#fff; text-decoration:none; background:transparent; margin-left:8px;
        }}
        .btn.primary {{ background:#2563eb; border:none; }}
        section {{ background:#131313; border:1px solid rgba(255,255,255,0.08); border-radius:24px; padding:26px; margin-bottom:24px; }}
        label {{ display:block; margin-bottom:6px; color:rgba(255,255,255,0.7); font-size:0.9rem; }}
        input[type="file"], textarea {{ width:100%; padding:14px; border-radius:16px; border:1px solid rgba(255,255,255,0.2); background:#0f0f0f; color:#fff; margin-bottom:14px; }}
        textarea {{ min-height:150px; }}
        button {{ width:100%; padding:12px; border:none; border-radius:16px; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }}
        .error {{ color:#f87171; margin-bottom:12px; }}
        .result-card {{ background:#181818; border:1px solid rgba(255,255,255,0.08); border-radius:20px; padding:20px; margin-top:16px; }}
        .chips {{ display:flex; flex-wrap:wrap; gap:10px; margin:12px 0; }}
        .chip {{ padding:6px 14px; border-radius:999px; background:rgba(37,99,235,0.15); border:1px solid rgba(37,99,235,0.5); }}
        table {{ width:100%; border-collapse:collapse; }}
        th, td {{ padding:12px; border-bottom:1px solid rgba(255,255,255,0.08); text-align:left; font-size:0.9rem; }}
        a.link {{ color:#2563eb; text-decoration:none; margin-right:8px; }}
    </style>
</head>
<body>
    <div class="page">
        <div class="top-nav">
            <div>HR Agent · {user_name}</div>
            <div>
                <a class="btn" href="/">Лендинг</a>
                <a class="btn" href="/profile">Профиль</a>
                <a class="btn primary" href="/logout">Выйти</a>
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


def render_analysis_block(result: dict | None, sources: List[dict]) -> str:
    if not result:
        return ""
    chips = "".join(f'<div class="chip">{skill}</div>' for skill in result.get("skills_match", []))
    strengths = "".join(f"<li>{item}</li>" for item in result.get("strengths", []))
    weaknesses = "".join(f"<li>{item}</li>" for item in result.get("weaknesses", []))
    dev_plan = "".join(f"<li>{item}</li>" for item in result.get("development_plan", []))
    recs = "".join(f"<li>{item}</li>" for item in result.get("recommendations", []))
    sources_list = "".join(f'<li><a class="link" href="{src.get("href")}" target="_blank">{src.get("title")}</a></li>' for src in sources)
    return f"""
    <section class="result-card">
        <h2>Результат: {result.get("match_score", 0)}%</h2>
        <p>Источник: {"LLM gpt-oss:20b-cloud" if result.get("engine") == "llm" else "эвристический анализ"}</p>
        <div class="chips">{chips}</div>
        <h3>Сильные стороны</h3>
        <ul>{strengths}</ul>
        <h3>Зоны роста</h3>
        <ul>{weaknesses}</ul>
        <h3>План развития</h3>
        <ul>{dev_plan}</ul>
        <h3>Рекомендации</h3>
        <ul>{recs}</ul>
        <h3>Источники вакансий</h3>
        <ul>{sources_list}</ul>
        <p>{result.get("summary","")}</p>
    </section>
    """


def render_history(history: List[dict]) -> str:
    if not history:
        return "<p>Анализов пока нет.</p>"
    rows = ""
    for item in history:
        rows += f"""
        <tr>
            <td>{item['created_at']}</td>
            <td>{item['match_score']}%</td>
            <td>{item['engine']}</td>
            <td>
                <a class="link" href="/candidate/analysis/{item['id']}/download?format=json">JSON</a>
                <a class="link" href="/candidate/analysis/{item['id']}/download?format=docx">DOCX</a>
                <a class="link" href="/candidate/analysis/{item['id']}/download?format=xlsx">XLSX</a>
            </td>
        </tr>
        """
    return f"<table><thead><tr><th>Дата</th><th>Match</th><th>Движок</th><th>Выгрузка</th></tr></thead><tbody>{rows}</tbody></table>"


@router.get("/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    history = analysis_service.list_analyses(user["id"])
    html = DASHBOARD_TEMPLATE.format(
        user_name=user["name"],
        error_block="",
        vacancy_text="",
        analysis_block="",
        history_block=render_history(history),
    )
    return HTMLResponse(html)


@router.post("/analyze", response_class=HTMLResponse)
async def analyze_resume(
    request: Request,
    resume_file: UploadFile = File(...),
    vacancy_text: str = Form(...),
) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    resume_text = (await read_upload(resume_file)).strip()
    vacancy_text = vacancy_text.strip()
    error_block = ""
    analysis_block = ""
    result = None
    sources: List[dict] = []
    if not resume_text or not vacancy_text:
        error_block = '<div class="error">Добавьте корректный файл резюме и описание вакансии.</div>'
    else:
        sources = analysis_service.ddg_sources(f"{vacancy_text[:60]} вакансия требования", max_results=5)
        llm_result = analysis_service.call_llm(resume_text, vacancy_text, sources)
        result = llm_result or analysis_service.heuristic_analysis(resume_text, vacancy_text)
        analysis_service.store_analysis(
            user_id=user["id"],
            resume_excerpt=resume_text[:800],
            vacancy=vacancy_text,
            result=result,
            sources=sources,
        )
        analysis_block = render_analysis_block(
            {**result, "skills_match": result.get("skills_match", [])}, sources
        )
        error_block = ""
    history = analysis_service.list_analyses(user["id"])
    html = DASHBOARD_TEMPLATE.format(
        user_name=user["name"],
        error_block=error_block,
        vacancy_text=vacancy_text,
        analysis_block=analysis_block,
        history_block=render_history(history),
    )
    return HTMLResponse(html, status_code=400 if error_block else 200)


@router.get("/analysis/{analysis_id}/download")
async def download_analysis(request: Request, analysis_id: int, format: str = "json"):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    record = analysis_service.fetch_analysis(user["id"], analysis_id)
    if not record:
        return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
    result = record["result_json"]
    data = {
        "match_score": result.get("match_score"),
        "strengths": result.get("strengths"),
        "weaknesses": result.get("weaknesses"),
        "skills_match": result.get("skills_match"),
        "experience_assessment": result.get("experience_assessment"),
        "education_assessment": result.get("education_assessment"),
        "development_plan": result.get("development_plan"),
        "recommendations": result.get("recommendations"),
        "summary": result.get("summary"),
        "vacancy": record["vacancy_description"],
        "resume_excerpt": record["resume_excerpt"],
        "sources": record["sources_json"],
        "engine": record["engine"],
        "created_at": record["created_at"],
    }
    if format == "json":
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.json"'},
        )
    if format == "docx":
        document = analysis_service.analysis_to_docx(data)
        return StreamingResponse(
            io.BytesIO(document),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.docx"'},
        )
    if format == "xlsx":
        workbook = analysis_service.analysis_to_xlsx(data)
        return StreamingResponse(
            io.BytesIO(workbook),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.xlsx"'},
        )
    return RedirectResponse("/candidate/dashboard", status_code=HTTP_303_SEE_OTHER)
