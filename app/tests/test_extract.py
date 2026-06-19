"""Тесты извлечения текста, ссылок и эпизодов."""
from app import extract


def test_parse_numeric_citations():
    cits = extract.parse_citations("Факт [1]. Ещё [2, с. 14]. Группа [3, 4; 5].")
    keys = sorted({c.ref_key for c in cits if c.kind == "numeric"})
    assert keys == ["1", "2", "3", "4", "5"]
    page = [c.page for c in cits if c.ref_key == "2"][0]
    assert page == "14"


def test_parse_author_year_and_url_doi():
    cits = extract.parse_citations(
        "Как пишет (Иванов, 2021). См. https://e.org/x и doi:10.1000/abc.def")
    kinds = {c.kind for c in cits}
    assert "author_year" in kinds
    assert "url" in kinds
    assert any(c.kind == "doi" for c in cits)


def test_abbreviation_does_not_split_sentence():
    # «с.» и «т. д.» не должны рвать предложение
    eps = extract.split_episodes("Данные выросли вдвое [2, с. 14] и т. д. за год.")
    assert len(eps) == 1
    assert eps[0].citations[0].ref_key == "2"


def test_split_bibliography_and_entries():
    text = (
        "Тело статьи с фактом [1].\n\n"
        "Список литературы\n"
        "1. Петров П.П. Климат // Наука, 2020. URL: http://e.org/a\n"
        "2. Сидоров С.С. Данные. — М., 2019.\n"
    )
    body, sources = extract.split_bibliography(text)
    assert "Список литературы" not in body
    assert len(sources) == 2
    assert sources[0].year == "2020"
    assert sources[0].url.startswith("http")
    assert sources[1].year == "2019"


def test_analyze_document_episode_count():
    text = (
        "Первое утверждение [1]. Второе утверждение [2]. Без ссылки тут.\n\n"
        "Литература\n1. А. Б.\n2. В. Г.\n"
    )
    eps, srcs = extract.analyze_document(text)
    assert len(eps) == 2          # только предложения со ссылками
    assert len(srcs) == 2
