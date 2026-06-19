"""Грейдинг: объединяет эвристики и ИИ в статус эпизода и сводный вердикт.

Правило §6.5 AI_RULES.md: итоговый статус = ХУДШИЙ из (эвристики, ИИ). ИИ может
лишь понизить статус, но не поднять его выше детерминированных подтверждений.
Если ИИ недоступен — опираемся на эвристики (без ложного занижения).
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Callable, Optional

from . import config, llm, verifier
from .heuristics import score_episode, term_overlap
from .models import Episode, EpisodeVerdict, Report, SourceRef, Status, worst
from .verifier import relevant_window

log = logging.getLogger("check.grader")

# флаги ИИ, означающие ОТСУТСТВИЕ реального сигнала → опираемся на эвристики
_AI_NO_SIGNAL = {"ai_unavailable", "ai_invalid", "ai_invalid_status"}

_AI_TO_STATUS = {
    "SUPPORTED": Status.SUPPORTED,
    "PARTIAL": Status.PARTIAL,
    "NOT_SUPPORTED": Status.NOT_SUPPORTED,
    "SOURCE_MISSING": Status.SOURCE_MISSING,
}


def _best_excerpt(ep: Episode, by_key: dict[str, SourceRef]) -> str:
    """Окно текста НАИБОЛЕЕ РЕЛЕВАНТНОГО источника (по пересечению терминов, не по длине)."""
    best, best_ov = None, -1.0
    for c in ep.citations:
        s = by_key.get(c.ref_key)
        if s and s.has_content:
            ov = term_overlap(ep.text, s.content)
            if ov > best_ov:
                best_ov, best = ov, s
    return relevant_window(ep.text, best.content) if best else ""


def grade_episode(ep: Episode, by_key: dict[str, SourceRef], use_ai: bool,
                  chat_fn: Optional[Callable] = None) -> EpisodeVerdict:
    h = score_episode(ep, by_key)
    reasons = list(h.flags)
    quote = h.quote
    ai_judgement = None
    final = h.status

    excerpt = _best_excerpt(ep, by_key)
    ai_no_signal = True
    if use_ai and excerpt:
        aj = verifier.judge(ep.text, excerpt, chat_fn=chat_fn)
        ai_judgement = aj
        reasons += [f"ai:{f}" for f in aj.flags]
        if not (_AI_NO_SIGNAL & set(aj.flags)):         # есть РЕАЛЬНЫЙ сигнал ИИ
            ai_no_signal = False
            ai_status = _AI_TO_STATUS.get(aj.status, Status.NOT_SUPPORTED)
            final = worst(h.status, ai_status)          # ИИ только понижает
            if aj.quote:
                quote = aj.quote

    # защитный инвариант: «подтверждён» без единой дословной цитаты невозможен
    if final == Status.SUPPORTED and not quote:
        final = Status.PARTIAL
        reasons.append("no_quote_downgrade")

    explanation = _explain(final, h, ai_judgement, ep, quote, ai_no_signal)

    ai_dbg = (f"ai={ai_judgement.status}/q={len(ai_judgement.quote)}/{ai_judgement.flags}"
              if ai_judgement else "ai=off")
    log.info("эпизод #%d: heur=%s(%.2f) %s -> ИТОГ=%s | excerpt=%d симв | claim=%r",
             ep.index, h.status.value, h.score, ai_dbg, final.value,
             len(excerpt), ep.text[:90])

    return EpisodeVerdict(status=final, heuristic_score=h.score, ai=ai_judgement,
                          quote=quote, explanation=explanation, reasons=reasons)


def _explain(final: Status, h, ai, ep: Episode, quote: str, ai_no_signal: bool) -> str:
    """Человекочитаемое «почему» — чтобы вердикт вызывал доверие, а не загадку."""
    refs = ", ".join(c.raw for c in ep.citations) or "—"
    flags = set(h.flags) | (set(ai.flags) if ai else set())
    parts: list[str] = []

    if final == Status.FABRICATED:
        parts.append(f"Ссылка {refs} не найдена в списке литературы — источник, "
                     f"вероятно, выдуман или неверно пронумерован.")
    elif final == Status.SOURCE_MISSING:
        parts.append(f"Источник {refs} недоступен для сверки: файл не загружен и "
                     f"не удалось скачать из сети. Проверить соответствие невозможно.")
    elif final == Status.SUPPORTED:
        parts.append("Источник прямо подтверждает утверждение — найдено дословное совпадение.")
    elif final == Status.PARTIAL:
        parts.append("Источник подтверждает утверждение лишь частично или с расхождением "
                     "(нет точной дословной опоры на весь тезис).")
    elif final == Status.NOT_SUPPORTED:
        if ai and "quote_not_in_source" in ai.flags:
            parts.append("ИИ не смог привести из источника дословную цитату в подтверждение — "
                         "источник не содержит этого утверждения.")
        else:
            parts.append("Источник найден, но не содержит данного утверждения "
                         "(низкое пересечение по смыслу).")

    if any(str(f).startswith("author_year_mismatch") for f in flags):
        parts.append("Год в ссылке не совпадает с годом источника.")
    if ai_no_signal and final not in (Status.FABRICATED, Status.SOURCE_MISSING):
        parts.append("ИИ-сверка недоступна — решение по детерминированным эвристикам.")
    return " ".join(parts)


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
