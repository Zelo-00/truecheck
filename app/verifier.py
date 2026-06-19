"""ИИ-судья соответствия под изолированным правилом AI_RULES.md.

Ключевая идея: коду нельзя доверять модели на слово. Любой её ответ проходит
программные предохранители (§6 AI_RULES.md), главный из которых — проверка, что
дословная цитата действительно является подстрокой переданного фрагмента.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Optional

from . import config, llm
from .heuristics import tokens
from .models import MatchJudgement

_VALID = {"SUPPORTED", "PARTIAL", "NOT_SUPPORTED", "SOURCE_MISSING"}
_RULES_CACHE: Optional[str] = None


def _system_prompt() -> str:
    """Системный промпт = заблокированный контракт AI_RULES.md + требование JSON."""
    global _RULES_CACHE
    if _RULES_CACHE is None:
        p = Path(config.AI_RULES_PATH)
        rules = p.read_text(encoding="utf-8") if p.exists() else "Суди только по фрагменту."
        _RULES_CACHE = (
            rules
            + f"\n\nMIN_QUOTE_CHARS = {config.VERIFY_MIN_QUOTE_CHARS}."
            + "\nОтветь СТРОГО одним JSON-объектом по схеме §4. Без текста вокруг."
        )
    return _RULES_CACHE


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower().replace("ё", "е")


def relevant_window(claim: str, source: str, max_chars: int = 4000) -> str:
    """Окно источника вокруг наиболее релевантной утверждению зоны (дословно)."""
    if not source:
        return ""
    if len(source) <= max_chars:
        return source
    terms = set(tokens(claim))
    src_low = source.lower()
    best_pos, best_hits = 0, -1
    step = 500
    for pos in range(0, max(1, len(source) - max_chars + 1), step):
        window = src_low[pos: pos + max_chars]
        hits = sum(1 for t in terms if t in window)
        if hits > best_hits:
            best_hits, best_pos = hits, pos
    return source[best_pos: best_pos + max_chars]


def _parse(raw: str) -> Optional[dict]:
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)  # вытащить JSON, если есть обёртка
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def judge(claim: str, source_excerpt: Optional[str],
          chat_fn: Optional[Callable[[str, str, float], Optional[str]]] = None
          ) -> MatchJudgement:
    """Главный вход. chat_fn инъектируется в тестах (mock-LLM)."""
    # §6.4 / §2.4 — пустой источник: никаких догадок, ИИ даже не зовём
    excerpt = (source_excerpt or "").strip()
    if not excerpt:
        return MatchJudgement(status="SOURCE_MISSING", quote="", confidence=0.0,
                              rationale="Источник недоступен — сверка невозможна.",
                              flags=["source_missing"])

    user = (f"CLAIM:\n{claim}\n\nSOURCE_EXCERPT:\n{excerpt}\n\n"
            "Верни JSON по схеме §4 (status, quote, rationale, confidence).")
    fn = chat_fn or (lambda s, u, t: llm.chat(s, u, t))
    raw = fn(_system_prompt(), user, config.VERIFY_TEMPERATURE)

    # ИИ недоступен — честно говорим, что машинной сверки не было
    if not raw:
        return MatchJudgement(status="NOT_SUPPORTED", quote="", confidence=0.0,
                              rationale="ИИ-сверка недоступна; решение по эвристикам.",
                              flags=["ai_unavailable"])

    return _apply_safeguards(_parse(raw), excerpt)


def _apply_safeguards(data: Optional[dict], excerpt: str) -> MatchJudgement:
    """Предохранители §6 AI_RULES.md — код не верит модели на слово."""
    flags: list[str] = []

    # §6.1 — невалидный JSON
    if not isinstance(data, dict):
        return MatchJudgement(status="NOT_SUPPORTED", quote="", confidence=0.0,
                              rationale="Невалидный ответ ИИ.", flags=["ai_invalid"])

    status = str(data.get("status", "")).upper()
    quote = str(data.get("quote", "") or "")
    rationale = str(data.get("rationale", "") or "")
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    if status not in _VALID:
        status, flags = "NOT_SUPPORTED", flags + ["ai_invalid_status"]

    # §6.2 — ГЛАВНЫЙ детектор галлюцинации: цитата обязана быть в источнике
    if status in ("SUPPORTED", "PARTIAL"):
        if not quote or _norm(quote) not in _norm(excerpt):
            status = "NOT_SUPPORTED"
            quote = ""
            flags.append("quote_not_in_source")

    # §6.3 — слишком короткая цитата для «подтверждён»
    if status == "SUPPORTED" and len(quote.strip()) < config.VERIFY_MIN_QUOTE_CHARS:
        status = "PARTIAL"
        flags.append("quote_too_short")

    return MatchJudgement(status=status, quote=quote.strip(), rationale=rationale,
                          confidence=max(0.0, min(conf, 1.0)), flags=flags)
