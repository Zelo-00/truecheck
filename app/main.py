"""FastAPI-приложение «Сверка»: веб-платформа проверки текста по источникам."""
from __future__ import annotations

import hashlib
import logging
import os
import secrets

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import (APP_NAME, APP_TAGLINE, AUTHOR, AUTHOR_YEAR, __version__,
               config, jobs, llm, report as report_mod)
from .extract import SUPPORTED_EXTS, analyze_document, read_document
from .grader import build_report
from .sources import attach_sources, fetch_text_from_url

config.ensure_dirs()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# реальный лог работы в файл (папка logs/) — для разбора галлюцинаций/границ
from logging.handlers import RotatingFileHandler  # noqa: E402

_fh = RotatingFileHandler(os.path.join(config.LOG_DIR, "app.log"),
                          maxBytes=3_000_000, backupCount=5, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_fh)
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger("check.main")
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


_COOKIE_MAXAGE = 60 * 60 * 24 * 365


def _get_or_set_sid(request: Request, response) -> str:
    """Анонимный идентификатор сессии в cookie — чтобы история была приватной."""
    sid = request.cookies.get("tc_sid")
    if not sid:
        sid = secrets.token_hex(16)
        response.set_cookie("tc_sid", sid, max_age=_COOKIE_MAXAGE,
                            httponly=True, samesite="lax")
    return sid


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    resp = templates.TemplateResponse(request, "index.html", {
        "ai_available": llm.available(),
        "auth_required": bool(config.ACCESS_TOKEN),
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS),
    })
    _get_or_set_sid(request, resp)
    return resp


@app.get("/faq", response_class=HTMLResponse)
def faq(request: Request):
    resp = templates.TemplateResponse(request, "faq.html", {
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS),
    })
    _get_or_set_sid(request, resp)
    return resp


@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    sid = request.cookies.get("tc_sid", "")
    resp = templates.TemplateResponse(request, "history.html", {
        "entries": report_mod.read_index(sid, 200),
    })
    _get_or_set_sid(request, resp)
    return resp


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
    token: str = Form(default=""),
):
    # --- 0. токен доступа (если включён) ---
    if config.ACCESS_TOKEN:
        given = token or request.headers.get("x-access-token", "")
        if not secrets.compare_digest(given, config.ACCESS_TOKEN):
            return _error(request, "Неверный или отсутствует токен доступа.", status=401)

    # --- 1. читаем загруженные байты СИНХРОННО (UploadFile живёт только в запросе) ---
    doc_bytes: bytes | None = None
    doc_filename = ""
    if doc_file is not None and doc_file.filename:
        doc_bytes = await doc_file.read()
        _guard_size(doc_bytes)
        doc_filename = doc_file.filename
    uploads: dict[str, bytes] = {}
    for sf in source_files or []:
        if sf and sf.filename:
            b = await sf.read()
            _guard_size(b)
            uploads[sf.filename] = b
    doc_url = doc_url.strip()

    if doc_bytes is None and not doc_url and not doc_text.strip():
        return _error(request, "Не удалось получить текст: загрузите файл, вставьте текст или дайте рабочую ссылку.")

    want_ai = use_ai == "on" and llm.available()
    sid = request.cookies.get("tc_sid") or secrets.token_hex(16)
    display = doc_filename or ("Вставленный текст" if doc_text.strip() else doc_url)
    job = jobs.create(display)
    report_url = str(request.base_url).rstrip("/") + "/report/" + job.id

    # --- 2. вся тяжёлая работа — в фоне, с прогрессом по эпизодам ---
    def _process(j: jobs.Job) -> None:
        if doc_bytes is not None:
            text = read_document(doc_bytes, doc_filename)
        elif doc_url:
            text, name = fetch_text_from_url(doc_url)
            if name:
                j.doc_name = name
        else:
            text = doc_text
        if not text.strip():
            j.error = "Не удалось извлечь текст из документа/ссылки."
            j.state = "error"
            return
        episodes, sources = analyze_document(text)
        j.total = len(episodes)
        log.info("проверка '%s': %d симв., эпизодов=%d, источников=%d, файлов=%d",
                 j.doc_name, len(text), len(episodes), len(sources), len(uploads))
        attach_sources(sources, uploads)

        def _cb(done: int, total: int) -> None:
            j.done, j.total = done, total

        rep = build_report(j.id, j.doc_name, episodes, sources,
                           use_ai=want_ai, progress_cb=_cb)
        report_mod.save(rep)
        report_mod.append_index(rep, sid)
        html = templates.get_template("report.html").render(
            rep=rep, status_class=_STATUS_CLASS, app_name=APP_NAME, report_url=report_url)
        with open(os.path.join(config.REPORTS_DIR, j.id + ".html"), "w", encoding="utf-8") as f:
            f.write(html)

    jobs.start(job, _process)

    resp = templates.TemplateResponse(request, "progress.html",
                                      {"job_id": job.id, "doc_name": display})
    if not request.cookies.get("tc_sid"):
        resp.set_cookie("tc_sid", sid, max_age=_COOKIE_MAXAGE, httponly=True, samesite="lax")
    return resp


@app.get("/status/{job_id}")
def job_status(job_id: str):
    j = jobs.get(_safe(job_id))
    if not j:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(j.as_dict())


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


@app.get("/api/report/{job_id}.docx")
def get_report_docx(job_id: str):
    jid = _safe(job_id)
    path = os.path.join(config.REPORTS_DIR, jid + ".docx")
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(
        path, filename=f"truecheck-{jid}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# --- helpers ---

def _guard_size(b: bytes) -> None:
    if len(b) > config.MAX_UPLOAD_MB * 1024 * 1024:
        from fastapi import HTTPException
        raise HTTPException(status_code=413, detail="Файл слишком большой")


def _safe(job_id: str) -> str:
    return "".join(ch for ch in job_id if ch.isalnum())[:32]


def _error(request: Request, msg: str, status: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {
        "ai_available": llm.available(),
        "auth_required": bool(config.ACCESS_TOKEN),
        "formats": ", ".join(e.lstrip(".") for e in SUPPORTED_EXTS), "error": msg,
    }, status_code=status)
