# Implementation Plan: «Сверка»

Регламент: `/home/deploy/SkillTask.md`. Источник истины: `SPEC.md`, `AI_RULES.md`.

## Overview
Строим веб-платформу проверки текста по источникам вертикальными срезами:
от моделей и движка (без сети/ИИ) → к гибридной привязке источников и ИИ-судье →
к веб-интерфейсу и упаковке в Docker. Каждый срез тестируется в изоляции `DATA_DIR`.

## Architecture Decisions
- **Чистое ядро.** `extract/heuristics/grader` — чистые функции без сети; сеть и
  ИИ изолированы в `sources.py`/`llm.py`/`verifier.py` → ядро тестируется детерминированно.
- **ИИ не «поднимает» статус.** Итог эпизода = худшее из (эвристики, ИИ-судья) — §6.5 `AI_RULES.md`.
- **Дословная цитата обязательна** для подтверждения — детектор галлюцинаций встроен в код, а не доверен модели.
- **Свой дизайн.** Светлая forensic-тема, сплит-вью; ни стилей, ни кода `fly`.

## Task List

### Phase 1: Ядро без сети и ИИ
- [ ] **Task 1 — Модели и конфиг.** `models.py` (Citation, SourceRef, Episode, MatchJudgement, EpisodeVerdict, Report), `config.py` (.env).
  - Acceptance: dataclasses сериализуются в dict/JSON; конфиг читает `.env`.
  - Verify: `pytest app/tests/test_models.py -q`.
  - Files: `app/models.py`, `app/config.py`, `app/tests/test_models.py`. Scope: S.
- [ ] **Task 2 — Извлечение текста и эпизодов.** `extract.py`: txt/docx/pdf → текст; парсинг списка литературы; разбиение на эпизоды; парсинг маркеров `[n]`, `[n, с. x]`, `(Автор, год)`, URL/DOI.
  - Acceptance: на эталонном тексте находит ≥95% маркеров; каждый эпизод привязан к записи литературы.
  - Verify: `pytest app/tests/test_extract.py -q`.
  - Files: `app/extract.py`, `app/tests/test_extract.py`, `app/tests/fixtures/*`. Scope: M.
- [ ] **Task 3 — Эвристики.** `heuristics.py`: наличие источника в списке, совпадение дословных цитат («…»), пересечение терминов (TF/леммы), сверка автор/год.
  - Acceptance: возвращает суб-сигналы 0..1 + флаги (`citation_verbatim`, `author_year_mismatch`, `source_absent`).
  - Verify: `pytest app/tests/test_heuristics.py -q`.
  - Files: `app/heuristics.py`, `app/tests/test_heuristics.py`. Scope: M.

### Checkpoint: Ядро
- [ ] Тесты 1–3 зелёные в изоляции; ядро не делает сетевых вызовов.

### Phase 2: Источники и ИИ-судья
- [ ] **Task 4 — Гибридная привязка источников.** `sources.py`: сопоставить ссылку → загруженный файл; если нет и `FETCH_SOURCES` — скачать по URL/DOI; извлечь текст; вернуть `SourceRef(status=local|fetched|not_found)`.
  - Acceptance: при наличии файла берёт файл; без файла и без сети → `not_found` (не падает).
  - Verify: `pytest app/tests/test_sources.py -q` (сеть замокана).
  - Files: `app/sources.py`, `app/tests/test_sources.py`. Scope: M.
- [ ] **Task 5 — ИИ-клиент.** `llm.py`: провайдер-агностик (openai-совм. + gemini fallback), `temperature=0`, не бросает исключений (None на отказе).
  - Acceptance: при пустых ключах `available()==False`; формирует корректный payload.
  - Verify: `pytest app/tests/test_llm.py -q` (HTTP замокан).
  - Files: `app/llm.py`, `app/tests/test_llm.py`. Scope: S.
- [ ] **Task 6 — ИИ-судья + предохранители.** `verifier.py`: системный промпт из `AI_RULES.md`; `judge(claim, excerpt)`; пост-валидация §6 (quote-substring, min-chars, пустой источник, понижение статуса).
  - Acceptance: **анти-галлюцинационный** тест зелёный — выдуманная цитата срезается до `NOT_SUPPORTED`.
  - Verify: `pytest app/tests/test_verifier.py -q` (mock-LLM + приманка).
  - Files: `app/verifier.py`, `app/tests/test_verifier.py`. Scope: M.

### Checkpoint: Верификация
- [ ] Анти-галлюцинационный тест зелёный; ИИ не «поднимает» статус выше эвристик.

### Phase 3: Грейдинг, отчёт, веб, упаковка
- [ ] **Task 7 — Грейдер и отчёт.** `grader.py` (статус эпизода = худшее из ИИ/эвристик; сводный балл 0–100%; вердикт «ИИ-генерация/литература не соответствует» по доле НЕ ПОДТВЕРЖДЁН/ВЫДУМАН). `report.py` (Report → JSON/Markdown/HTML).
  - Acceptance: отчёт покрывает **все** эпизоды; есть сводный балл и вердикт.
  - Verify: `pytest app/tests/test_grader.py -q`.
  - Files: `app/grader.py`, `app/report.py`, `app/tests/test_grader.py`. Scope: M.
- [ ] **Task 8 — FastAPI + свой фронт.** `main.py` (роуты: `GET /`, `POST /check`, `GET /report/{id}`, `GET /api/report/{id}.json`), шаблоны `base/index/report`, `static/app.css|app.js` — оригинальный дизайн.
  - Acceptance: e2e через `TestClient`: загрузка текста+источника → HTML-отчёт со всеми эпизодами.
  - Verify: `pytest app/tests/test_e2e.py -q`; ручной заход на `/`.
  - Files: `app/main.py`, `app/templates/*`, `app/static/*`, `app/tests/test_e2e.py`. Scope: L → при необходимости дробить (api / шаблоны).
- [ ] **Task 9 — Упаковка.** `Dockerfile`, `docker-compose.yml` (app+nginx), `web/nginx.conf`, `README.md`/RUN_GUIDE.
  - Acceptance: `docker compose up -d --build` поднимает платформу, `/` отвечает 200.
  - Verify: `docker compose ps`, `curl -s localhost/ | head`.
  - Files: `Dockerfile`, `docker-compose.yml`, `web/nginx.conf`, `README.md`. Scope: M.

### Checkpoint: Complete
- [ ] Все критерии `SPEC.md` выполнены; e2e и анти-галлюцинационный тесты зелёные; `/review` пройдено; `/ship` go.

## Risks and Mitigations
| Риск | Влияние | Митигатор |
|------|---------|-----------|
| Парсинг ссылок хрупкий (разные ГОСТ/стили) | High | Набор регэкспов + фикстуры на каждый стиль; неуверенные → `ИСТОЧНИК НЕ НАЙДЕН`, не молча |
| ИИ галлюцинирует цитату | High | Предохранитель §6.2 (quote-substring) + блокирующий тест |
| Пейвол/недоступность источника | Med | Статус `not_found`, не выдаём за «проверено» |
| docx/pdf экзотика | Med | Фолбэк на сырой текст, явная ошибка вместо краха |

## Open Questions
- Экспорт отчёта в PDF/DOCX — следующая итерация (сейчас HTML/JSON/MD).
