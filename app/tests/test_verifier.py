"""Контрактные тесты ИИ-судьи и ПРЕДОХРАНИТЕЛЕЙ §6 AI_RULES.md.

Главный (анти-галлюцинационный) тест блокирует релиз: если модель «подтверждает»
цитатой, которой нет в источнике, код обязан срезать вердикт.
"""
import json

from app import verifier

SOURCE = ("В исследовании показано, что вода закипает при 100 градусах Цельсия "
          "в условиях нормального атмосферного давления на уровне моря.")


def _mock(resp: dict):
    return lambda system, user, temp: json.dumps(resp, ensure_ascii=False)


def test_empty_source_is_source_missing_without_calling_ai():
    called = {"n": 0}
    def chat(s, u, t):
        called["n"] += 1
        return "{}"
    j = verifier.judge("любое утверждение", "", chat_fn=chat)
    assert j.status == "SOURCE_MISSING"
    assert called["n"] == 0           # ИИ даже не вызывался


def test_hallucinated_quote_is_cut_down():
    # модель «подтверждает» цитатой, которой НЕТ в источнике
    j = verifier.judge(
        "Вода закипает при 70 градусах.", SOURCE,
        chat_fn=_mock({"status": "SUPPORTED",
                       "quote": "вода закипает при 70 градусах",
                       "rationale": "выдумка", "confidence": 0.99}))
    assert j.status == "NOT_SUPPORTED"
    assert j.quote == ""
    assert "quote_not_in_source" in j.flags


def test_real_verbatim_quote_supported():
    real = "вода закипает при 100 градусах Цельсия"
    j = verifier.judge(
        "Вода кипит при 100 градусах.", SOURCE,
        chat_fn=_mock({"status": "SUPPORTED", "quote": real,
                       "rationale": "совпадает", "confidence": 0.9}))
    assert j.status == "SUPPORTED"
    assert real in verifier._norm(j.quote) or j.quote


def test_invalid_json_becomes_not_supported():
    j = verifier.judge("утв.", SOURCE, chat_fn=lambda s, u, t: "не json вовсе")
    assert j.status == "NOT_SUPPORTED"
    assert "ai_invalid" in j.flags


def test_too_short_quote_downgraded_to_partial():
    short = SOURCE[:8]  # короче VERIFY_MIN_QUOTE_CHARS
    j = verifier.judge(
        "что-то", SOURCE,
        chat_fn=_mock({"status": "SUPPORTED", "quote": short,
                       "rationale": "к", "confidence": 0.5}))
    assert j.status == "PARTIAL"
    assert "quote_too_short" in j.flags


def test_ai_unavailable_marked():
    j = verifier.judge("утв.", SOURCE, chat_fn=lambda s, u, t: None)
    assert "ai_unavailable" in j.flags


def test_dirty_model_output_is_normalized():
    # реальная модель: markdown-фенсы, lowercase status, confidence строкой
    real = "вода закипает при 100 градусах Цельсия"
    dirty = ('```json\n{"status": "supported", "quote": "%s", '
             '"rationale": "ок", "confidence": "high"}\n```' % real)
    j = verifier.judge("Вода кипит при 100°C.", SOURCE, chat_fn=lambda s, u, t: dirty)
    assert j.status == "SUPPORTED"     # распознан несмотря на фенсы и регистр
    assert j.confidence == 0.0         # нечисловая confidence безопасно обнулена
    assert real in j.quote
