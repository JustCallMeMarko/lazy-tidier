import pytest

from tidier.llm import Classification
from tidier.validate import normalize_date, sanitize_title, validate

CATS = ["School", "Receipts", "IDs", "Work", "Media", "Misc"]


def cls(**kw):
    base = {"category": "School", "title": "a-title", "confidence": 0.9, "sensitive": False}
    return Classification(**(base | kw))


def test_sanitize_strips_separators():
    assert "/" not in sanitize_title('a/b\\c:d*e?f"g<h>i|j')
    assert sanitize_title("   spaced   out   ") == "spaced-out"


def test_sanitize_caps_length_and_fallback():
    assert len(sanitize_title("x" * 200)) <= 80
    assert sanitize_title("///") == "untitled"


def test_normalize_date():
    assert normalize_date("2026-10-18") == "2026-10-18"
    assert normalize_date("18/10/2026") is None
    assert normalize_date(None) is None


def test_validate_rejects_bad_category():
    with pytest.raises(ValueError):
        validate(cls(category="Nonsense"), CATS, 0.65)


def test_validate_clamps_confidence():
    assert validate(cls(confidence=1.7), CATS, 0.65).confidence == 1.0
