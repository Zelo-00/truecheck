"""Провайдер-агностик ИИ-клиент. Собственная реализация (не из fly).

Поддерживает OpenAI-совместимый эндпоинт и нативный Gemini. Пробует основной
провайдер, затем второй как fallback. Никогда не бросает исключений: на полном
отказе возвращает None — движок продолжает работать на эвристиках.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from . import config

log = logging.getLogger("check.llm")
_ALL = ("openai", "gemini")
# Gemini передаёт ключ в query (?key=...), а Bearer — в заголовке. Любое из них
# может попасть в текст исключения → вырезаем перед логированием.
_SECRET = re.compile(r"(key=|Bearer\s+|sk-)[A-Za-z0-9_\-]+")


def _scrub(msg: str) -> str:
    return _SECRET.sub(r"\1***", msg)


def _has_key(provider: str) -> bool:
    return bool(config.OPENAI_API_KEY) if provider == "openai" else bool(config.GEMINI_API_KEY)


def available() -> bool:
    """True, если ИИ включён и хотя бы у одного провайдера есть ключ."""
    return config.AI_ENABLE and config.VERIFY_AI and any(_has_key(p) for p in _ALL)


def _order() -> list[str]:
    primary = config.AI_PROVIDER if config.AI_PROVIDER in _ALL else "openai"
    return [primary] + [p for p in _ALL if p != primary]


def chat(system: str, user: str, temperature: Optional[float] = None) -> Optional[str]:
    """Один запрос. Возвращает текст ответа или None при полном отказе."""
    temp = config.VERIFY_TEMPERATURE if temperature is None else temperature
    for provider in _order():
        if not _has_key(provider):
            continue
        try:
            if provider == "openai":
                out = _openai(system, user, temp)
            else:
                out = _gemini(system, user, temp)
            if out and out.strip():
                return out.strip()
        except Exception as e:  # noqa: BLE001 — клиент обязан не падать
            log.warning("LLM provider %s failed: %s", provider, _scrub(str(e)))
            continue
    return None


def _openai(system: str, user: str, temp: float) -> Optional[str]:
    import httpx  # ленивый импорт
    url = f"{config.OPENAI_BASE_URL}/chat/completions"
    payload = {
        "model": config.OPENAI_MODEL,
        "temperature": temp,
        "top_p": 1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    r = httpx.post(url, json=payload, headers=headers, timeout=config.AI_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini(system: str, user: str, temp: float) -> Optional[str]:
    import httpx  # ленивый импорт
    url = (f"{config.GEMINI_BASE_URL}/models/{config.GEMINI_MODEL}:generateContent"
           f"?key={config.GEMINI_API_KEY}")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temp, "topP": 1,
                             "responseMimeType": "application/json"},
    }
    r = httpx.post(url, json=payload, timeout=config.AI_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
