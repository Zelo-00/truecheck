"""Конфигурация из окружения (.env). Никаких секретов в коде.

Значения читаются один раз при импорте. ИИ-ключи перенесены из проекта fly
в check/.env (общий шлюз), но клиент и логика здесь — собственные.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Минималистичный загрузчик .env (без внешних зависимостей).

    Не перетирает уже выставленные переменные окружения.
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        # значение может иметь хвостовой комментарий "VAL   # коммент"
        val = val.split("#", 1)[0].strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(os.getenv("DOTENV_PATH", ".env"))


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# --- данные ---
DATA_DIR = os.getenv("DATA_DIR", "./data").rstrip("/")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))

# --- ИИ (провайдер-агностик; ключи из .env) ---
AI_ENABLE = _flag("AI_ENABLE", "true")
VERIFY_AI = _flag("VERIFY_AI", "true")
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "30"))
VERIFY_TEMPERATURE = float(os.getenv("VERIFY_TEMPERATURE", "0"))
VERIFY_MIN_QUOTE_CHARS = int(os.getenv("VERIFY_MIN_QUOTE_CHARS", "24"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gemini-3.5-flash").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://open.blackroute.space/v1").rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")

# --- догрузка источников из сети ---
FETCH_SOURCES = _flag("FETCH_SOURCES", "true")
FETCH_TIMEOUT = int(os.getenv("FETCH_TIMEOUT", "20"))

# путь к изолированному правилу ИИ
AI_RULES_PATH = os.getenv("AI_RULES_PATH", "AI_RULES.md")


def ensure_dirs() -> None:
    for d in (DATA_DIR, UPLOADS_DIR, REPORTS_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
