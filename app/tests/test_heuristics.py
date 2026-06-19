"""Тесты детерминированных эвристик."""
from app import heuristics as H
from app.models import Citation, Episode, SourceRef, Status


def _ep(text, *keys):
    return Episode(index=0, text=text,
                   citations=[Citation(raw=f"[{k}]", kind="numeric", ref_key=k) for k in keys])


def test_term_overlap_and_quotes():
    assert H.term_overlap("климат теплеет планета", "планета и климат теплеет") > 0.6
    assert H.verbatim_quotes('сказано «вода кипит при ста»', "текст: вода кипит при ста, факт") == ["вода кипит при ста"]


def test_fabricated_when_ref_absent():
    sig = H.score_episode(_ep("Факт [9]", "9"), by_key={})
    assert sig.status == Status.FABRICATED


def test_source_missing_when_no_content():
    src = SourceRef(key="1", bib_text="Иванов")  # без content
    sig = H.score_episode(_ep("Факт [1]", "1"), by_key={"1": src})
    assert sig.status == Status.SOURCE_MISSING


def test_supported_with_verbatim_quote():
    src = SourceRef(key="1", content="В работе показано: вода кипит при ста градусах при давлении.")
    sig = H.score_episode(_ep('Автор пишет «вода кипит при ста градусах» [1]', "1"),
                          by_key={"1": src})
    assert sig.status == Status.SUPPORTED
    assert "вода кипит при ста градусах" in sig.quote


def test_not_supported_low_overlap():
    src = SourceRef(key="1", content="Совершенно про другое: история древнего рима и легионы.")
    sig = H.score_episode(_ep("Квантовая запутанность фотонов в оптоволокне [1]", "1"),
                          by_key={"1": src})
    assert sig.status == Status.NOT_SUPPORTED
