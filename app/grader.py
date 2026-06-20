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
from .heuristics import term_overlap, verbatim_quotes
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


def _heur_one(text: str, src: SourceRef) -> tuple[Status, float, str]:
    """Эвристический вердикт по ОДНОМУ источнику."""
    ov = term_overlap(text, src.content)
    qs = verbatim_quotes(text, src.content)
    quote = qs[0] if qs else ""
    score = max(ov, 0.85) if quote else ov
    if quote and ov >= 0.3:
        st = Status.SUPPORTED
    elif ov >= 0.3:
        st = Status.PARTIAL
    else:
        st = Status.NOT_SUPPORTED
    return st, round(min(score, 1.0), 3), quote


def _grade_against_source(text: str, src: SourceRef, use_ai: bool, chat_fn):
    """Сверка утверждения с одним источником: эвристики + ИИ (итог = худший)."""
    h_st, score, quote = _heur_one(text, src)
    flags: list[str] = []
    ai = None
    ai_no_signal = True
    final = h_st
    if use_ai:
        excerpt = relevant_window(text, src.content)
        if excerpt:
            ai = verifier.judge(text, excerpt, chat_fn=chat_fn)
            flags += [f"ai:{f}" for f in ai.flags]
            if not (_AI_NO_SIGNAL & set(ai.flags)):
                ai_no_signal = False
                final = worst(h_st, _AI_TO_STATUS.get(ai.status, Status.NOT_SUPPORTED))
                if ai.quote:
                    quote = ai.quote
    if final == Status.SUPPORTED and not quote:
        final = Status.PARTIAL
        flags.append("no_quote_downgrade")
    return final, score, quote, ai, flags, ai_no_signal


def grade_episode(ep: Episode, by_key: dict[str, SourceRef], use_ai: bool,
                  chat_fn: Optional[Callable] = None) -> EpisodeVerdict:
    # 1. разрешаем ссылки эпизода в источники
    resolved: list[SourceRef] = []
    fab_refs: list[str] = []
    seen: set[int] = set()
    for c in ep.citations:
        s = by_key.get(c.ref_key)
        if s is None:
            fab_refs.append(c.ref_key)
        elif id(s) not in seen:
            seen.add(id(s))
            resolved.append(s)

    if not resolved:                                    # все ссылки выдуманы
        v = EpisodeVerdict(status=Status.FABRICATED,
                           reasons=[f"ref_not_in_bibliography:{k}" for k in fab_refs])
        v.explanation = _explain(Status.FABRICATED, ep, "", None, True, None, fab_refs, [])
        log.info("эпизод #%d: ИТОГ=FABRICATED (нет источника) | claim=%r", ep.index, ep.text[:90])
        return v

    with_content = [s for s in resolved if s.has_content]
    if not with_content:                                # источники в списке есть, текста нет
        v = EpisodeVerdict(status=Status.SOURCE_MISSING, reasons=["no_source_content"])
        v.explanation = _explain(Status.SOURCE_MISSING, ep, "", None, True, None, fab_refs, [])
        log.info("эпизод #%d: ИТОГ=SOURCE_MISSING | claim=%r", ep.index, ep.text[:90])
        return v

    # 2. ПО-ЦИТАТНО: сверяем с каждым источником, берём ЛУЧШИЙ результат
    best = None
    for s in with_content:
        fin, score, quote, ai, flags, ai_ns = _grade_against_source(ep.text, s, use_ai, chat_fn)
        if (best is None or fin.severity < best[0].severity
                or (fin.severity == best[0].severity and score > best[1])):
            best = (fin, score, quote, ai, flags, ai_ns, s)

    final, score, quote, ai, flags, ai_no_signal, src = best
    if fab_refs:
        flags.append("some_refs_fabricated:" + ",".join(fab_refs))
    explanation = _explain(final, ep, quote, ai, ai_no_signal, src.key, fab_refs, flags)
    log.info("эпизод #%d: ИТОГ=%s по источнику [%s] (из %d привязанных) | claim=%r",
             ep.index, final.value, src.key, len(with_content), ep.text[:90])
    return EpisodeVerdict(status=final, heuristic_score=score, ai=ai, quote=quote,
                          explanation=explanation, reasons=flags)


def _explain(final: Status, ep: Episode, quote: str, ai, ai_no_signal: bool,
             support_ref, fab_refs: list[str], flags: list[str]) -> str:
    """Человекочитаемое «почему» — чтобы вердикт вызывал доверие, а не загадку."""
    refs = ", ".join(c.raw for c in ep.citations) or "—"
    parts: list[str] = []

    if final == Status.FABRICATED:
        parts.append(f"Ссылка {refs} не найдена в списке литературы — источник, "
                     f"вероятно, выдуман или неверно пронумерован.")
    elif final == Status.SOURCE_MISSING:
        parts.append(f"Источник {refs} недоступен для сверки: файл не загружен и "
                     f"не удалось скачать из сети. Проверить соответствие невозможно.")
    elif final == Status.SUPPORTED:
        parts.append(f"Источник [{support_ref}] прямо подтверждает утверждение — "
                     f"найдено дословное совпадение.")
    elif final == Status.PARTIAL:
        parts.append(f"Источник [{support_ref}] подтверждает утверждение лишь частично "
                     f"или с расхождением (нет точной дословной опоры на весь тезис).")
    elif final == Status.NOT_SUPPORTED:
        if ai and "quote_not_in_source" in ai.flags:
            parts.append("Ни один из процитированных источников не содержит дословного "
                         "подтверждения этого утверждения.")
        else:
            parts.append("Процитированные источники не содержат данного утверждения "
                         "(низкое пересечение по смыслу).")

    if fab_refs and final not in (Status.FABRICATED,):
        parts.append(f"При этом ссылк(и) {', '.join(fab_refs)} отсутствуют в списке литературы.")
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
                 chat_fn: Optional[Callable] = None,
                 progress_cb: Optional[Callable[[int, int], None]] = None) -> Report:
    """Грейдит все эпизоды и собирает сводку. Покрываются ВСЕ эпизоды.

    progress_cb(done, total) вызывается после каждого эпизода — для async-прогресса.
    """
    ai_on = (config.VERIFY_AI and llm.available()) if use_ai is None else use_ai
    by_key = {s.key: s for s in sources}
    for s in sources:  # альт-ключ author_year
        if s.author and s.year:
            by_key.setdefault(f"{s.author.split()[0]} {s.year}", s)

    counts = {st.value: 0 for st in Status}
    n_total = len(episodes)
    for i, ep in enumerate(episodes):
        ep.verdict = grade_episode(ep, by_key, ai_on, chat_fn=chat_fn)
        counts[ep.verdict.status.value] += 1
        if progress_cb:
            progress_cb(i + 1, n_total)

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
