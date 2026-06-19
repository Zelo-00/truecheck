"""Детерминированные эвристики сверки эпизода с источником.

Без сети и ИИ. Дают предварительный статус и числовые сигналы, которые потом
комбинируются с вердиктом ИИ (итог = худший из двух — §6.5 AI_RULES.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Citation, Episode, SourceRef, Status

# крошечный список русских стоп-слов (для пересечения терминов)
_STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если
уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей
может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз
тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом
один почти мой тем чтобы нее были куда зачем всех никогда можно при наконец два об
другой хоть после над больше тот через эти нас про всего них какая много разве три
эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более
всю между это его её также этом является является того также как
""".split())

_QUOTE = re.compile(r"[«\"“]([^»\"”]{8,})[»\"”]")
_WORD = re.compile(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\-]{2,}")


def _stem(token: str) -> str:
    """Очень грубый стеммер: режем частые русские окончания. Достаточно для overlap."""
    t = token.lower().replace("ё", "е")
    for end in ("ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими", "ость",
                "ция", "ние", "ть", "ая", "ое", "ые", "ий", "ый", "ой", "ам",
                "ям", "ах", "ях", "ов", "ев", "ом", "ем", "ах", "и", "ы", "а",
                "я", "у", "ю", "е", "о"):
        if len(t) - len(end) >= 4 and t.endswith(end):
            return t[: -len(end)]
    return t


def tokens(text: str) -> list[str]:
    """Содержательные основы слов (без стоп-слов)."""
    out = []
    for w in _WORD.findall(text or ""):
        wl = w.lower().replace("ё", "е")
        if wl in _STOP or len(wl) < 3:
            continue
        out.append(_stem(wl))
    return out


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower().replace("ё", "е")


def term_overlap(claim: str, source: str) -> float:
    """Доля содержательных основ утверждения, присутствующих в источнике (0..1)."""
    ct = set(tokens(claim))
    if not ct:
        return 0.0
    st = set(tokens(source))
    return len(ct & st) / len(ct)


def verbatim_quotes(claim: str, source: str) -> list[str]:
    """Кавычечные фрагменты утверждения, дословно встречающиеся в источнике."""
    src = _norm_ws(source)
    found = []
    for m in _QUOTE.finditer(claim):
        q = m.group(1).strip()
        if _norm_ws(q) and _norm_ws(q) in src:
            found.append(q)
    return found


@dataclass
class HeuristicSignal:
    status: Status
    score: float                       # 0..1, уверенность в подтверждении
    quote: str = ""                    # дословная цитата-обоснование, если нашлась
    flags: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)


def _resolve_sources(cit: list[Citation], by_key: dict[str, SourceRef]
                     ) -> tuple[list[SourceRef], list[str]]:
    """Сопоставляет ссылки эпизода с записями литературы; возвращает (найдено, флаги)."""
    resolved, flags = [], []
    for c in cit:
        s = by_key.get(c.ref_key) or by_key.get(c.ref_key.strip())
        if s is None and c.kind == "author_year":
            # мягкое сопоставление по фамилии+году
            for src in by_key.values():
                if src.author and src.year and src.author.split()[0].lower() in c.ref_key.lower() \
                        and src.year in c.ref_key:
                    s = src
                    break
        if s is None:
            flags.append(f"ref_not_in_bibliography:{c.ref_key}")
        else:
            resolved.append(s)
    return resolved, flags


def score_episode(ep: Episode, by_key: dict[str, SourceRef]) -> HeuristicSignal:
    """Главная функция: предварительный статус эпизода по детерминированным сигналам."""
    sources, flags = _resolve_sources(ep.citations, by_key)
    signals: dict = {}

    # 1. ссылка указывает на несуществующую запись → источник выдуман
    if not sources:
        return HeuristicSignal(Status.FABRICATED, 0.0, flags=flags or ["no_source_linked"],
                               signals={"resolved": 0})

    # берём лучший из привязанных источников
    best = None
    best_overlap = -1.0
    quote = ""
    for s in sources:
        if not s.has_content:
            continue
        ov = term_overlap(ep.text, s.content)
        qs = verbatim_quotes(ep.text, s.content)
        if qs and not quote:
            quote = qs[0]
        if ov > best_overlap:
            best_overlap, best = ov, s

    # 2. источники в списке есть, но содержимого нет (не загружен / не найден в сети)
    if best is None:
        return HeuristicSignal(Status.SOURCE_MISSING, 0.0,
                               flags=flags + ["no_source_content"],
                               signals={"resolved": len(sources), "with_content": 0})

    signals["term_overlap"] = round(best_overlap, 3)
    signals["verbatim_quote"] = bool(quote)

    # 3. сверка автор/год для author_year-ссылок
    for c in ep.citations:
        if c.kind == "author_year" and best.year:
            yr = re.search(r"(1[89]\d{2}|20\d{2})", c.ref_key)
            if yr and yr.group(1) != best.year:
                flags.append(f"author_year_mismatch:{c.ref_key}!={best.year}")

    # 4. собираем балл и предварительный статус
    score = best_overlap
    if quote:
        score = max(score, 0.85)
    if any(f.startswith("author_year_mismatch") for f in flags):
        score *= 0.6

    if quote and best_overlap >= 0.3:
        status = Status.SUPPORTED
    elif best_overlap >= 0.6:
        status = Status.PARTIAL    # консервативно: без ИИ/цитаты не выдаём «подтверждён»
    elif best_overlap >= 0.3:
        status = Status.PARTIAL
    else:
        status = Status.NOT_SUPPORTED

    return HeuristicSignal(status, round(min(score, 1.0), 3), quote=quote,
                           flags=flags, signals=signals)
