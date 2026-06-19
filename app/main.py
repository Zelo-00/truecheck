"""FastAPI-приложение «Сверка»: веб-платформа проверки текста по источникам."""
from __future__ import annotations

import hashlib
import logging
import os
import uuid

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import (APP_NAME, APP_TAGLINE, AUTHOR, AUTHOR_YEAR, __version__,
               config, llm, report as report_mod)
from .extract import SUPPORTED_EXTS, analyze_document, read_document
from .grader import build_report
from .sources import attach_sources, fetch_text_from_url

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("check.main")

config.ensure_dirs()
_HERE = os.path.dirname(__file__)
app = FastAPI(title=f"{APP_NAME} — проверка текста по источникам", version=__version__)
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))

_STATUS_CLASS = {
    "SUPPORTED": "ok", "PARTIAL": "warn", "NOT_SUPPORTED": "bad",
    "SOURCE_MISSING": "missing", "FABRICATED": "fab",
}
def _asset_version() -> str:
    """Хэш от mtime/размера статики → сброс кэша браузера при каждом изменении."""
    h = hashlib.md5()
    for rel in ("static/app.css", "static/app.js"):
        try:
            st = os.stat(os.path.join(_HERE, rel))
            h.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}".encode())
        except OSError:
            pass
    return h.hexdigest()[:10]


ASSET_V = _asset_version()
templates.env.globals.update(status_class=_STATUS_CLASS, app_name=APP_NAME,
                             app_tagline=APP_TAGLINE, author=AUTHOR,
                             author_year=AUTHOR_YEAR, asset_v=ASSET_V)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "ai_available": llm.available(),
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS),
    })


@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request):
    return templates.TemplateResponse(request, "faq.html", {
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS),
    })


@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    return templates.TemplateResponse(request, "history.html", {
        "entries": report_mod.read_index(200),
    })


@app.get("/health")
def health():
    return {"status": "ok", "ai": llm.available(), "version": __version__}


@app.post("/check", response_class=HTMLResponse)
async def check(
    request: Request,
    doc_file: UploadFile | None = File(default=None),
    doc_text: str = Form(default=""),
    doc_url: str = Form(default=""),
    source_files: list[UploadFile] = File(default=[]),
    use_ai: str = Form(default="on"),
):
    # --- 1. получаем проверяемый текст: файл | вставка | ссылка ---
    doc_name, text = "", ""
    if doc_file is not None and doc_file.filename:
        raw = await doc_file.read()
        _guard_size(raw)
        doc_name = doc_file.filename
        text = read_document(raw, doc_name)
    elif doc_url.strip():
        text, name = fetch_text_from_url(doc_url.strip())
        doc_name = name or doc_url.strip()
    elif doc_text.strip():
        doc_name = "Вставленный текст"
        text = doc_text

    if not text.strip():
        return _error(request, "Не удалось получить текст: загрузите файл, вставьте текст или дайте рабочую ссылку.")

    # --- 2. источники, загруженные пользователем ---
    uploads: dict[str, bytes] = {}
    for sf in source_files or []:
        if sf and sf.filename:
            b = await sf.read()
            _guard_size(b)
            uploads[sf.filename] = b

    # --- 3. разбор → привязка источников → грейдинг ---
    episodes, sources = analyze_document(text)
    log.info("проверка '%s': %d симв., эпизодов=%d, источников=%d, файлов-источников=%d",
             doc_name, len(text), len(episodes), len(sources), len(uploads))
    attach_sources(sources, uploads)
    want_ai = use_ai == "on" and llm.available()
    job_id = uuid.uuid4().hex[:12]
    rep = build_report(job_id, doc_name, episodes, sources, use_ai=want_ai)

    # --- 4. рендер + сохранение ---
    report_mod.save(rep)
    html = templates.get_template("report.html").render(request=request, rep=rep,
                                                        status_class=_STATUS_CLASS,
                                                        app_name=APP_NAME)
    with open(os.path.join(config.REPORTS_DIR, job_id + ".html"), "w", encoding="utf-8") as f:
        f.write(html)
    return HTMLResponse(html)


@app.get("/report/{job_id}", response_class=HTMLResponse)
def get_report(job_id: str):
    path = os.path.join(config.REPORTS_DIR, _safe(job_id) + ".html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>Отчёт не найден</h1>", status_code=404)
    with open(path, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/report/{job_id}.json")
def get_report_json(job_id: str):
    path = os.path.join(config.REPORTS_DIR, _safe(job_id) + ".json")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="application/json")


@app.get("/api/report/{job_id}.md")
def get_report_md(job_id: str):
    jid = _safe(job_id)
    path = os.path.join(config.REPORTS_DIR, jid + ".md")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(path, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="truecheck-{jid}.md"'})


# --- helpers ---

def _guard_size(b: bytes) -> None:
    if len(b) > config.MAX_UPLOAD_MB * 1024 * 1024:
        from fastapi import HTTPException
        raise HTTPException(status_code=413, detail="Файл слишком большой")


def _safe(job_id: str) -> str:
    return "".join(ch for ch in job_id if ch.isalnum())[:32]


def _error(request: Request, msg: str) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {
        "ai_available": llm.available(),
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS), "error": msg,
    }, status_code=400)
