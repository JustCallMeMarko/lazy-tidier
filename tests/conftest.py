import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from tidier.config import Config
from tidier.db import DB


@pytest.fixture
def cfg(tmp_path):
    return Config(
        watch_path=tmp_path / "Downloads",
        destination_root=tmp_path / "Downloads" / "Sorted",
    )


@pytest.fixture
def db(tmp_path):
    d = DB(tmp_path / "test.db")
    yield d
    d.close()


class FakeLLM:
    """Deterministic stand-in for Ollama."""

    text_model = "fake-text"
    vision_model = "fake-vision"

    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def classify_text(self, name, content):
        self.calls.append(("text", name))
        return self.result

    def classify_image(self, name, image_path):
        self.calls.append(("image", name))
        return self.result
