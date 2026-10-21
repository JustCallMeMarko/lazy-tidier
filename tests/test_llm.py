import pytest

from tidier.llm import assert_loopback


def test_loopback_ok():
    for h in ["http://localhost:11434", "http://127.0.0.1:11434", "localhost:11434"]:
        assert_loopback(h)


def test_remote_host_rejected():
    with pytest.raises(RuntimeError):
        assert_loopback("http://192.168.1.50:11434")
    with pytest.raises(RuntimeError):
        assert_loopback("http://ollama.example.com:11434")
