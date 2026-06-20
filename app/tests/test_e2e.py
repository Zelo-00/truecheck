"""E2E через FastAPI TestClient. ИИ выключен (AI_ENABLE=false). Проверка асинхронна:
/check отдаёт страницу прогресса → опрос /status → готовый отчёт по /report/{id}."""
import re
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DOC = (
    'Автор пишет «вода кипит при ста градусах» [1]. Жизнь занесена из космоса [2].\n\n'
    'Список литературы\n'
    '1. Иванов И.И. Физика. — М., 2010.\n'
    '2. Петров П.П. Химия. — СПб., 2012.\n'
)


def _run_check(data, files=None, timeout=10.0):
    """POST /check → дождаться завершения задания → вернуть job_id."""
    r = client.post("/check", data=data, files=files)
    assert r.status_code == 200, r.text
    m = re.search(r'data-job="([0-9a-f]+)"', r.text)
    assert m, "на странице прогресса нет job_id"
    jid = m.group(1)
    deadline = time.time() + timeout
    state = "queued"
    while time.time() < deadline:
        s = client.get(f"/status/{jid}").json()
        state = s["state"]
        if state in ("done", "error"):
            break
        time.sleep(0.05)
    assert state == "done", f"задание не завершилось: {state}"
    return jid


def test_index_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert "TrueCheck" in r.text


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_check_async_produces_report():
    jid = _run_check(
        {"doc_text": DOC, "use_ai": "off"},
        files=[("source_files", ("1.txt",
                "вода кипит при ста градусах при нормальном давлении".encode(), "text/plain"))],
    )
    rh = client.get(f"/report/{jid}")
    assert rh.status_code == 200
    assert "Отчёт" in rh.text and "Эпизод" in rh.text


def test_check_requires_input():
    r = client.post("/check", data={"doc_text": "", "use_ai": "off"})
    assert r.status_code == 400


def test_status_not_found():
    assert client.get("/status/deadbeef0000").status_code == 404


def test_report_json_and_exports():
    jid = _run_check({"doc_text": DOC, "use_ai": "off"})
    data = client.get(f"/api/report/{jid}.json").json()
    assert data["job_id"] == jid
    assert len(data["episodes"]) == 2          # покрыты ВСЕ эпизоды
    assert data["episodes"][0]["verdict"]["explanation"]  # объяснение есть
    md = client.get(f"/api/report/{jid}.md")
    assert md.status_code == 200
    assert "attachment" in md.headers.get("content-disposition", "")
    docx = client.get(f"/api/report/{jid}.docx")
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"           # docx — это zip


def test_history_session_scoped_e2e():
    jid = _run_check({"doc_text": DOC, "use_ai": "off"})
    h = client.get("/history")
    assert h.status_code == 200
    assert jid in h.text                       # своя проверка видна в истории


def test_md_export_missing():
    assert client.get("/api/report/doesnotexist.md").status_code == 404
