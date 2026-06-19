"""Грейдинг: объединяет эвристики и ИИ в статус эпизода и сводный вердикт.

Правило §6.5 AI_RULES.md: итоговый статус = ХУДШИЙ из (эвристики, ИИ). ИИ может
лишь понизить статус, но не поднять его выше детерминированных подтверждений.
Если ИИ недоступен — опираемся на эвристики (без ложного занижения).
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Optional

from . import config, llm, verifier
from .heuristics import score_episode
from .models import Episode, EpisodeVerdict, Report, SourceRef, Status, worst
from .verifier import relevant_window

_AI_TO_STATUS = {
    "SUPPORTED": Status.SUPPORTED,
    "PARTIAL": Status.PARTIAL,
    "NOT_SUPPORTED": Status.NOT_SUPPORTED,
    "SOURCE_MISSING": Status.SOURCE_MISSING,
}


def _best_excerpt(ep: Episode, by_key: dict[str, SourceRef]) -> str:
    """Релевантное окно текста лучшего привязанного источника (для ИИ)."""
    best, best_len = "", -1
    for c in ep.citations:
        s = by_key.get(c.ref_key)
        if s and s.has_content and len(s.content) > best_len:
            best, best_len = s.content, len(s.content)
    return relevant_window(ep.text, best) if best else ""


def grade_episode(ep: Episode, by_key: dict[str, SourceRef], use_ai: bool,
                  chat_fn: Optional[Callable] = None) -> EpisodeVerdict:
    h = score_episode(ep, by_key)
    reasons = list(h.flags)
    quote = h.quote
    ai_judgement = None
    final = h.status

    excerpt = _best_excerpt(ep, by_key)
    if use_ai and excerpt:
        aj = verifier.judge(ep.text, excerpt, chat_fn=chat_fn)
        ai_judgement = aj
        reasons += [f"ai:{f}" for f in aj.flags]
        if "ai_unavailable" not in aj.flags:           # есть реальный сигнал ИИ
            ai_status = _AI_TO_STATUS.get(aj.status, Status.NOT_SUPPORTED)
            final = worst(h.status, ai_status)          # ИИ только понижает
            if aj.quote:
                quote = aj.quote

    # защитный инвариант: «подтверждён» без единой дословной цитаты невозможен
    if final == Status.SUPPORTED and not quote:
        final = Status.PARTIAL
        reasons.append("no_quote_downgrade")

    return EpisodeVerdict(status=final, heuristic_score=h.score, ai=ai_judgement,
                          quote=quote, reasons=reasons)


_WEIGHT = {Status.SUPPORTED: 1.0, Status.PARTIAL: 0.5, Status.SOURCE_MISSING: 0.0,
           Status.NOT_SUPPORTED: 0.0, Status.FABRICATED: 0.0}
# вклад в «литература не соответствует / ИИ-генерация»
_RISK = {Status.SUPPORTED: 0.0, Status.PARTIAL: 0.2, Status.SOURCE_MISSING: 0.5,
         Status.NOT_SUPPORTED: 0.85, Status.FABRICATED: 1.0}


def build_report(job_id: str, doc_name: str, episodes: list[Episode],
                 sources: list[SourceRef], use_ai: Optional[bool] = None,
                 chat_fn: Optional[Callable] = None) -> Report:
    """Грейдит все эпизоды и собирает сводку. Покрываются ВСЕ эпизоды."""
    ai_on = (config.VERIFY_AI and llm.available()) if use_ai is None else use_ai
    by_key = {s.key: s for s in sources}
    for s in sources:  # альт-ключ author_year
        if s.author and s.year:
            by_key.setdefault(f"{s.author.split()[0]} {s.year}", s)

    counts = {st.value: 0 for st in Status}
    for ep in episodes:
        ep.verdict = grade_episode(ep, by_key, ai_on, chat_fn=chat_fn)
        counts[ep.verdict.status.value] += 1

    n = len(episodes)
    score = round(100 * sum(_WEIGHT[e.verdict.status] for e in episodes) / n) if n else 0
    risk = round(100 * sum(_RISK[e.verdict.status] for e in episodes) / n) if n else 0

    rep = Report(job_id=job_id, doc_name=doc_name,
                 created_at=_dt.datetime.now().isoformat(timespec="seconds"),
                 episodes=episodes, sources=sources, score=score, counts=counts,
                 ai_generated_likelihood=risk, ai_used=ai_on)
    rep.verdict_text = _verdict_text(rep)
    return rep


def _verdict_text(rep: Report) -> str:
    n = len(rep.episodes)
    if n == 0:
        return ("Не найдено ни одного эпизода со ссылкой на источник. "
                "Текст либо без ссылок, либо ссылки не распознаны.")
    c = rep.counts
    bad = c["FABRICATED"] + c["NOT_SUPPORTED"]
    parts = [f"Проверено эпизодов: {n}. Соответствие тексту источникам: {rep.score}%."]
    if c["FABRICATED"]:
        parts.append(f"Выдуманных/несуществующих ссылок: {c['FABRICATED']}.")
    if c["NOT_SUPPORTED"]:
        parts.append(f"Источник не подтверждает текст: {c['NOT_SUPPORTED']}.")
    if c["SOURCE_MISSING"]:
        parts.append(f"Источник недоступен для сверки: {c['SOURCE_MISSING']}.")
    if rep.ai_generated_likelihood >= 60:
        parts.append("ВЫВОД: высокая вероятность, что текст сгенерирован ИИ, "
                     "а литература не соответствует содержанию.")
    elif rep.ai_generated_likelihood >= 30 or bad:
        parts.append("ВЫВОД: есть несоответствия — ссылки частично не подтверждают текст.")
    else:
        parts.append("ВЫВОД: текст в целом соответствует приведённым источникам.")
    return " ".join(parts)
