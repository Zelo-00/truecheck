"""Сериализация отчёта: JSON / Markdown + сохранение на диск."""
from __future__ import annotations

import json
import os

from . import config
from .models import Report, Status


def to_dict(rep: Report) -> dict:
    d = rep.to_dict()
    # Enum → строковое значение для чистого JSON
    for ep in d["episodes"]:
        v = ep.get("verdict")
        if v and isinstance(v.get("status"), Status):
            v["status"] = v["status"].value
    return d


def to_json(rep: Report) -> str:
    return json.dumps(to_dict(rep), ensure_ascii=False, indent=2, default=str)


def to_markdown(rep: Report) -> str:
    lines = [f"# Отчёт сверки: {rep.doc_name}", "",
             f"- Дата: {rep.created_at}",
             f"- Соответствие источникам: **{rep.score}%**",
             f"- Вероятность «ИИ-генерация / литература не соответствует»: **{rep.ai_generated_likelihood}%**",
             f"- ИИ-сверка: {'включена' if rep.ai_used else 'выключена'}",
             "", f"**Вердикт.** {rep.verdict_text}", "", "## Эпизоды", ""]
    for ep in rep.episodes:
        v = ep.verdict
        lines.append(f"### Эпизод {ep.index + 1} — {v.status.ru}")
        lines.append(f"> {ep.text}")
        refs = ", ".join(c.raw for c in ep.citations)
        lines.append(f"- Ссылки: {refs}")
        if v.quote:
            lines.append(f"- Цитата из источника: «{v.quote}»")
        if v.reasons:
            lines.append(f"- Признаки: {', '.join(v.reasons)}")
        lines.append("")
    lines.append("## Источники")
    for s in rep.sources:
        lines.append(f"- [{s.key}] {s.bib_text}  — {s.origin} ({s.note})")
    return "\n".join(lines)


def save(rep: Report) -> dict:
    """Сохраняет JSON и Markdown в REPORTS_DIR и заносит в индекс. Возвращает пути."""
    config.ensure_dirs()
    base = os.path.join(config.REPORTS_DIR, rep.job_id)
    with open(base + ".json", "w", encoding="utf-8") as f:
        f.write(to_json(rep))
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(to_markdown(rep))
    append_index(rep)
    return {"json": base + ".json", "md": base + ".md"}


def _index_path() -> str:
    return os.path.join(config.REPORTS_DIR, "index.jsonl")


def append_index(rep: Report) -> None:
    """Добавляет компактную запись об отчёте в журнал истории (index.jsonl)."""
    entry = {"job_id": rep.job_id, "doc_name": rep.doc_name,
             "created_at": rep.created_at, "score": rep.score,
             "risk": rep.ai_generated_likelihood, "episodes": len(rep.episodes),
             "ai_used": rep.ai_used}
    with open(_index_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_index(limit: int = 100) -> list[dict]:
    """Читает историю проверок, новые — первыми."""
    p = _index_path()
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    out.reverse()
    return out[:limit]
