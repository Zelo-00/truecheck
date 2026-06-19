"""Гибридная привязка источников: загруженный файл → иначе догрузка из сети.

Сеть изолирована здесь. Все сетевые функции не бросают исключений: на отказе
возвращают пустой результат, источник помечается origin='none' с пояснением.
Этот же модуль умеет скачивать ПРОВЕРЯЕМЫЙ документ по ссылке на статью.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Optional
from urllib.parse import urlsplit

from . import config
from .extract import html_to_text, read_document
from .heuristics import tokens
from .models import SourceRef

log = logging.getLogger("check.sources")

_UA = {"User-Agent": "Mozilla/5.0 (compatible; TrueCheckBot/0.1; +verification)"}


def _is_public_url(url: str) -> bool:
    """SSRF-защита: разрешаем только http(s) на публичные адреса.

    Блокируем loopback/private/link-local/reserved (напр. 127.0.0.1, 10.x,
    169.254.169.254 — метаданные облака). Резолвим хост и проверяем все адреса.
    """
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        infos = socket.getaddrinfo(parts.hostname, parts.port or 0, proto=socket.IPPROTO_TCP)
        for *_, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return bool(infos)
    except Exception:  # noqa: BLE001 — не резолвится → не качаем
        return False


# ----------------------------------------------------------------------------- #
#  Сетевые помощники
# ----------------------------------------------------------------------------- #

def fetch_bytes(url: str) -> tuple[Optional[bytes], str]:
    """Скачивает URL (только публичные http(s)). Возвращает (bytes|None, content_type)."""
    if not _is_public_url(url):
        log.warning("fetch blocked (non-public or bad url): %s", url)
        return None, ""
    try:
        import httpx  # ленивый импорт
        with httpx.Client(follow_redirects=True, timeout=config.FETCH_TIMEOUT,
                          headers=_UA) as cli:
            r = cli.get(url)
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "")
    except Exception as e:  # noqa: BLE001
        log.warning("fetch failed %s: %s", url, e)
        return None, ""


def fetch_text_from_url(url: str) -> tuple[str, str]:
    """Скачивает страницу/файл по ссылке и извлекает текст.

    Возвращает (text, suggested_name). Подходит и для документа-под-проверку
    (ссылка на статью), и для догрузки источника.
    """
    data, ctype = fetch_bytes(url)
    if not data:
        return "", ""
    name = url.rstrip("/").split("/")[-1] or "article"
    ctype = ctype.lower()
    if "pdf" in ctype or name.lower().endswith(".pdf"):
        return read_document(data, name if name.endswith(".pdf") else name + ".pdf"), name
    if "html" in ctype or "xml" in ctype or not name.endswith((".txt", ".md")):
        return html_to_text(data.decode("utf-8", errors="replace")), name
    return read_document(data, name), name


# ----------------------------------------------------------------------------- #
#  Привязка источников к записям литературы
# ----------------------------------------------------------------------------- #

def _score_match(ref: SourceRef, fname: str, text: str) -> int:
    """Насколько файл похож на данную запись литературы (имя + содержимое)."""
    score = 0
    base = re.sub(r"\.[a-z0-9]+$", "", fname.lower())
    key = ref.key.strip()
    # 1. имя файла начинается с номера ссылки ([N]/N./N_/N-) либо равно ему
    if key.isdigit() and (re.match(rf"^\[?{key}[\].)_\-\s]", base) or base == key):
        score += 6
    low = text.lower()
    # 2. фамилия автора — в имени файла и/или в тексте источника
    if ref.author:
        surname = ref.author.split()[0].lower().strip(".")
        if len(surname) >= 4:
            if surname in fname.lower():
                score += 4
            if surname in low:
                score += 4
    # 3. год издания встречается в тексте
    if ref.year and ref.year in text:
        score += 2
    # 4. пересечение слов заголовка с текстом источника
    tw = set(tokens(ref.title))
    if tw:
        score += min(3, len(tw & set(tokens(text))))
    return score


def _assign_files(sources: list[SourceRef], file_text: dict[str, str]) -> dict[str, str]:
    """Глобально сопоставляет файлы записям литературы (1:1) по содержимому/имени.

    Жадно берём пары с наибольшим совпадением; остаток раздаём по порядку
    (пользователь часто грузит файлы в порядке списка литературы).
    """
    if not sources or not file_text:
        return {}
    pairs = []
    for ref in sources:
        for fname, text in file_text.items():
            pairs.append((_score_match(ref, fname, text), ref.key, fname))
    pairs.sort(key=lambda p: p[0], reverse=True)

    assign: dict[str, str] = {}
    used_files: set[str] = set()
    for score, key, fname in pairs:
        if score <= 0 or key in assign or fname in used_files:
            continue
        assign[key] = fname
        used_files.add(fname)

    # добор по порядку: оставшиеся записи ↔ оставшиеся файлы
    rem_refs = [s.key for s in sources if s.key not in assign]
    rem_files = [f for f in sorted(file_text) if f not in used_files]
    for key, fname in zip(rem_refs, rem_files):
        assign[key] = fname
        used_files.add(fname)
        log.info("источник [%s] ← файл %s (по порядку)", key, fname)
    return assign


def attach_sources(sources: list[SourceRef], uploads: dict[str, bytes],
                   fetch: Optional[bool] = None) -> list[SourceRef]:
    """Наполняет каждую SourceRef текстом: сначала файл, затем (опц.) сеть."""
    do_fetch = config.FETCH_SOURCES if fetch is None else fetch

    # читаем все загруженные файлы один раз
    file_text: dict[str, str] = {}
    for fname, data in uploads.items():
        try:
            file_text[fname] = read_document(data, fname)
        except Exception as e:  # noqa: BLE001
            file_text[fname] = ""
            log.warning("не прочитан файл %s: %s", fname, e)

    assign = _assign_files(sources, file_text)
    used = set(assign.values())

    for ref in sources:
        fname = assign.get(ref.key)
        if fname and file_text.get(fname, "").strip():
            ref.content = file_text[fname]
            ref.origin = "local"
            ref.location = fname
            ref.note = f"Загружен файлом: {fname}"
            log.info("источник [%s] привязан к %s (%d симв.)", ref.key, fname, len(ref.content))
            continue

        # догрузка из сети по DOI/URL
        if do_fetch and (ref.url or ref.doi):
            target = ref.url or f"https://doi.org/{ref.doi}"
            text, _ = fetch_text_from_url(target)
            if text.strip():
                ref.content = text
                ref.origin = "fetched"
                ref.location = target
                ref.note = "Скачан из сети"
                log.info("источник [%s] скачан из сети: %s", ref.key, target)
                continue
            ref.note = "Не удалось скачать из сети"

        ref.origin = "none"
        if not ref.note:
            ref.note = "Источник недоступен (нет файла и ссылки)"

    leftover = [f for f in file_text if f not in used]
    if leftover:
        log.warning("загруженные файлы без привязки к списку литературы: %s", leftover)
    log.info("источников: %d, с содержимым: %d",
             len(sources), sum(1 for s in sources if s.has_content))
    return sources


def index_by_key(sources: list[SourceRef]) -> dict[str, SourceRef]:
    """Словарь ключ → SourceRef для быстрой привязки эпизодов."""
    out: dict[str, SourceRef] = {}
    for s in sources:
        out[s.key] = s
        if s.author and s.year:  # альтернативный ключ author_year
            out[f"{s.author.split()[0]} {s.year}"] = s
    return out
