"""«Сверка» — платформа проверки текста на соответствие источникам.

Ядро (extract / heuristics / grader) — чистые функции без сети и ИИ.
Сеть и ИИ изолированы в sources.py / llm.py / verifier.py.
"""

__version__ = "0.4.0"
APP_NAME = "TrueCheck"
APP_TAGLINE = "Проверка текста на соответствие источникам"
AUTHOR = "Zerno"
AUTHOR_YEAR = "2026"
