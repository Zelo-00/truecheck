"""Тесты грейдинга: комбинация ИИ+эвристик, сводка, покрытие всех эпизодов."""
import json

from app import extract, grader
from app.models import Status, worst


def test_worst_status():
    assert worst(Status.SUPPORTED, Status.NOT_SUPPORTED) == Status.NOT_SUPPORTED
    assert worst(Status.FABRICATED, Status.PARTIAL) == Status.FABRICATED
    assert worst(Status.SUPPORTED, Status.SUPPORTED) == Status.SUPPORTED


def _doc():
    text = (
        'Автор пишет «вода кипит при ста градусах» [1]. Жизнь занесена из космоса [2].\n\n'
        'Список литературы\n'
        '1. Иванов И.И. Физика. — М., 2010.\n'
        '2. Петров П.П. Химия. — СПб., 2012.\n'
    )
    eps, srcs = extract.analyze_document(text)
    srcs[0].content = "Показано: вода кипит при ста градусах при нормальном давлении."
    srcs[0].origin = "local"
    return eps, srcs


def test_build_report_covers_all_episodes():
    eps, srcs = _doc()
    rep = grader.build_report("j1", "doc", eps, srcs, use_ai=False)
    assert len(rep.episodes) == 2
    assert all(ep.verdict is not None for ep in rep.episodes)   # ни один не пропущен
    assert sum(rep.counts.values()) == 2
    assert 0 <= rep.score <= 100
    assert rep.verdict_text


def test_source_missing_episode():
    eps, srcs = _doc()
    rep = grader.build_report("j2", "doc", eps, srcs, use_ai=False)
    # [2] без содержимого → источник не найден
    ep2 = rep.episodes[1]
    assert ep2.verdict.status in (Status.SOURCE_MISSING, Status.NOT_SUPPORTED)


def test_ai_can_only_lower_status():
    eps, srcs = _doc()
    # эвристика по [1] даёт SUPPORTED (есть дословная цитата), но ИИ говорит NOT_SUPPORTED
    def chat(s, u, t):
        return json.dumps({"status": "NOT_SUPPORTED", "quote": "",
                           "rationale": "нет", "confidence": 0.8})
    rep = grader.build_report("j3", "doc", eps, srcs, use_ai=True, chat_fn=chat)
    assert rep.episodes[0].verdict.status == Status.NOT_SUPPORTED


def test_ai_unavailable_falls_back_to_heuristics():
    eps, srcs = _doc()
    def chat(s, u, t):                 # ИИ недоступен
        return None
    rep = grader.build_report("j4", "doc", eps, srcs, use_ai=True, chat_fn=chat)
    # не должно занижать: [1] остаётся подтверждённым по эвристике+цитате
    assert rep.episodes[0].verdict.status == Status.SUPPORTED
