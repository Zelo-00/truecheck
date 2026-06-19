"""Тесты SSRF-защиты привязки источников (без обращения в сеть)."""
from app.sources import _is_public_url


def test_blocks_loopback_and_private():
    assert _is_public_url("http://127.0.0.1/x") is False
    assert _is_public_url("http://localhost/") is False
    assert _is_public_url("http://10.0.0.5/") is False
    assert _is_public_url("http://169.254.169.254/latest/meta-data") is False  # облачные метаданные


def test_blocks_non_http_schemes():
    assert _is_public_url("ftp://example.org/x") is False
    assert _is_public_url("file:///etc/passwd") is False
    assert _is_public_url("not a url") is False


def test_allows_public_ip():
    # числовой публичный IP — getaddrinfo без обращения в DNS
    assert _is_public_url("https://8.8.8.8/") is True
