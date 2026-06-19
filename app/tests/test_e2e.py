"""E2E через FastAPI TestClient. ИИ принудительно выключен (AI_ENABLE=false в прогоне)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DOC = (
    'Автор пишет «вода кипит при ста градусах» [1]. Жизнь занесена из космоса [2].\n\n'
    'Список литературы\n'
    '1. Иванов И.И. Физика. — М., 2010.\n'
    '2. Петров П.П. Химия. — СПб., 2012.\n'
)


def test_index_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert "TrueCheck" in r.text


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_check_text_produces_report():
    # передаём проверяемый текст и источник [1] файлом, чтобы было содержимое
    r = client.post(
        "/check",
        data={"doc_text": DOC, "use_ai": "off"},
        files=[("source_files", ("1.txt",
                "вода кипит при ста градусах при нормальном давлении".encode(), "text/plain"))],
    )
    assert r.status_code == 200
    assert "Эпизод" in r.text or "эпизод" in r.text.lower()
    assert "Отчёт" in r.text


def test_check_requires_input():
    r = client.post("/check", data={"doc_text": "", "use_ai": "off"})
    assert r.status_code == 400


def test_report_persisted_and_json_api():
    r = client.post("/check", data={"doc_text": DOC, "use_ai": "off"})
    assert r.status_code == 200
    # достаём job_id из ссылки на JSON в отчёте
    import re
    m = re.search(r"/api/report/([0-9a-f]+)\.json", r.text)
    assert m, "в отчёте нет ссылки на JSON"
    jid = m.group(1)
    rj = client.get(f"/api/report/{jid}.json")
    assert rj.status_code == 200
    data = rj.json()
    assert data["job_id"] == jid
    assert len(data["episodes"]) == 2          # покрыты ВСЕ эпизоды
    rh = client.get(f"/report/{jid}")
    assert rh.status_code == 200


def test_md_export_and_history():
    r = client.post("/check", data={"doc_text": DOC, "use_ai": "off"})
    assert r.status_code == 200
    import re
    jid = re.search(r"/api/report/([0-9a-f]+)\.json", r.text).group(1)
    # экспорт .md как вложение
    md = client.get(f"/api/report/{jid}.md")
    assert md.status_code == 200
    assert "attachment" in md.headers.get("content-disposition", "")
    assert "Отчёт сверки" in md.text
    # отчёт попал в историю
    h = client.get("/history")
    assert h.status_code == 200
    assert jid in h.text


def test_md_export_missing():
    assert client.get("/api/report/doesnotexist.md").status_code == 404
