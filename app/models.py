"""Модели данных движка «Сверка». Чистые dataclasses, сериализуются в dict/JSON."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    """Статус эпизода (итоговый и промежуточные)."""
    SUPPORTED = "SUPPORTED"            # ПОДТВЕРЖДЁН
    PARTIAL = "PARTIAL"               # ЧАСТИЧНО
    NOT_SUPPORTED = "NOT_SUPPORTED"   # НЕ ПОДТВЕРЖДЁН
    SOURCE_MISSING = "SOURCE_MISSING" # ИСТОЧНИК НЕ НАЙДЕН
    FABRICATED = "FABRICATED"         # ИСТОЧНИК ВЫДУМАН

    @property
    def ru(self) -> str:
        return {
            "SUPPORTED": "Подтверждён",
            "PARTIAL": "Частично",
            "NOT_SUPPORTED": "Не подтверждён",
            "SOURCE_MISSING": "Источник не найден",
            "FABRICATED": "Источник выдуман",
        }[self.value]

    # порядок «тяжести»: больше = хуже. Используется для взятия худшего статуса.
    @property
    def severity(self) -> int:
        return {
            "SUPPORTED": 0,
            "PARTIAL": 1,
            "SOURCE_MISSING": 2,
            "NOT_SUPPORTED": 3,
            "FABRICATED": 4,
        }[self.value]


def worst(a: "Status", b: "Status") -> "Status":
    """Худший (более тяжёлый) из двух статусов — §6.5 AI_RULES.md."""
    return a if a.severity >= b.severity else b


@dataclass
class Citation:
    """Маркер цитирования, найденный в тексте: [12], [12, с. 44], (Иванов, 2021), URL/DOI."""
    raw: str                       # как встретилось в тексте
    kind: str                      # numeric | author_year | url | doi
    ref_key: str = ""              # ключ для привязки к списку литературы (номер/автор-год/url)
    page: Optional[str] = None     # «с. 44», если указана
    start: int = -1                # позиция в исходном тексте
    end: int = -1


@dataclass
class SourceRef:
    """Запись списка литературы и привязанный к ней текст источника."""
    key: str                       # номер «[12]» или «Иванов 2021»
    bib_text: str = ""             # строка из списка литературы
    author: str = ""
    year: str = ""
    title: str = ""
    url: str = ""
    doi: str = ""
    # привязка контента:
    origin: str = "none"           # local | fetched | none
    location: str = ""             # путь к файлу или URL, откуда взят текст
    content: str = ""              # извлечённый текст источника ("" если не найден)
    note: str = ""                 # пояснение (например, причина not_found)

    @property
    def has_content(self) -> bool:
        return bool(self.content and self.content.strip())


@dataclass
class MatchJudgement:
    """Вердикт ИИ-судьи (после программных предохранителей §6 AI_RULES.md)."""
    status: str                    # SUPPORTED | PARTIAL | NOT_SUPPORTED | SOURCE_MISSING
    quote: str = ""                # ДОСЛОВНАЯ подстрока источника
    rationale: str = ""
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)  # ai_invalid, quote_not_in_source, ...


@dataclass
class EpisodeVerdict:
    """Итог по одному эпизоду: эвристики + ИИ → статус."""
    status: Status
    heuristic_score: float = 0.0   # 0..1, уверенность эвристик в подтверждении
    ai: Optional[MatchJudgement] = None
    quote: str = ""                # дословная цитата-обоснование (если есть)
    reasons: list[str] = field(default_factory=list)  # человекочитаемые пояснения/флаги


@dataclass
class Episode:
    """Смысловой фрагмент текста с привязанными ссылками."""
    index: int
    text: str                      # сам фрагмент (предложение/абзац)
    citations: list[Citation] = field(default_factory=list)
    para: int = 0                  # номер абзаца
    verdict: Optional[EpisodeVerdict] = None


@dataclass
class Report:
    """Полный отчёт по документу."""
    job_id: str
    doc_name: str
    created_at: str
    episodes: list[Episode] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    # сводка:
    score: int = 0                 # 0..100 — общий процент соответствия
    counts: dict = field(default_factory=dict)  # по статусам
    verdict_text: str = ""         # человекочитаемый сводный вердикт
    ai_generated_likelihood: int = 0  # 0..100 — оценка «литература не соответствует / ИИ-генерация»
    ai_used: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
