"""«Злые» тесты реальных границ — то, на чём движок раньше ломался."""
from app import extract, grader, report as report_mod
from app.grader import _best_excerpt
from app.models import Citation, Episode, Report, SourceRef, Status
from app.sources import _assign_files
from app.verifier import relevant_window


def test_window_covers_tail_of_long_source():
    # факт в самом КОНЦЕ длинного источника не должен теряться
    fact = "нормальное атмосферное давление равно ровно сто один килопаскаль"
    src = ("посторонний наполнитель текста про погоду и кота. " * 400) + fact
    assert len(src) > 8000
    win = relevant_window(fact, src, max_chars=4000)
    assert "сто один килопаскаль" in win


def test_best_excerpt_picks_relevant_not_longest():
    ep = Episode(index=0, text="квантовая запутанность фотонов в оптоволокне",
                 citations=[Citation(raw="[1]", kind="numeric", ref_key="1"),
                            Citation(raw="[2]", kind="numeric", ref_key="2")])
    long_irrelevant = SourceRef(key="1", content="история древнего рима и легионы. " * 500)
    short_relevant = SourceRef(key="2",
                               content="доказана квантовая запутанность фотонов в оптоволокне на 100 км")
    ex = _best_excerpt(ep, {"1": long_irrelevant, "2": short_relevant})
    assert "запутанность фотонов" in ex     # выбран релевантный, не длиннейший


def test_assign_files_uses_upload_order_not_alphabet():
    srcs = [SourceRef(key="1", bib_text="x"), SourceRef(key="2", bib_text="y")]
    # имена без сигналов; порядок ЗАГРУЗКИ: b → [1], a → [2]
    files = {"b.txt": "контент один про разное", "a.txt": "контент два про иное"}
    assign, low = _assign_files(srcs, files)
    assert assign["1"] == "b.txt" and assign["2"] == "a.txt"
    assert low == {"1", "2"}                 # помечены как низкоуверенные


def test_ai_invalid_does_not_lower_heuristic():
    text = 'Автор пишет «вода кипит при ста градусах» [1].\n\nЛитература\n1. Иванов 2010.'
    eps, srcs = extract.analyze_document(text)
    srcs[0].content = "Показано: вода кипит при ста градусах при нормальном давлении."

    def chat(s, u, t):
        return "не json вовсе"                # мусорный ответ ИИ
    rep = grader.build_report("jx", "d", eps, srcs, use_ai=True, chat_fn=chat)
    v = rep.episodes[0].verdict
    assert v.status == Status.SUPPORTED       # эвристика не занижена кривым ИИ
    assert v.explanation                      # есть человекочитаемое объяснение


def test_every_verdict_has_explanation():
    text = 'Факт раз [9].\n\nЛитература\n1. Иванов 2010.'   # [9] нет в списке → FABRICATED
    eps, srcs = extract.analyze_document(text)
    rep = grader.build_report("jy", "d", eps, srcs, use_ai=False)
    assert rep.episodes[0].verdict.status == Status.FABRICATED
    assert "выдуман" in rep.episodes[0].verdict.explanation.lower()


def test_history_is_session_scoped():
    report_mod.append_index(Report(job_id="aaa111", doc_name="A", created_at="t"), "sidA")
    report_mod.append_index(Report(job_id="bbb222", doc_name="B", created_at="t"), "sidB")
    a = report_mod.read_index("sidA")
    assert any(e["job_id"] == "aaa111" for e in a)
    assert not any(e["job_id"] == "bbb222" for e in a)   # чужая сессия не видна
    assert report_mod.read_index("") == []               # без сессии — пусто
