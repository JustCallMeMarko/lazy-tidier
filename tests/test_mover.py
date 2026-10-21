from pathlib import Path

import pytest

from tidier.llm import Classification
from tidier.mover import destination, resolve_collision, safe_move, sha256_of, undo_move


def test_collision_suffix(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert resolve_collision(f).name == "a_2.txt"
    (tmp_path / "a_2.txt").write_text("y")
    assert resolve_collision(f).name == "a_3.txt"


def test_safe_move_and_undo(tmp_path):
    src = tmp_path / "src" / "f.txt"
    dst = tmp_path / "dst" / "f.txt"
    src.parent.mkdir()
    src.write_text("hello")
    digest = sha256_of(src)
    safe_move(src, dst)
    assert dst.read_text() == "hello" and not src.exists()
    undo_move(dst, src)
    assert src.read_text() == "hello" and not dst.exists()
    assert sha256_of(src) == digest


def test_undo_refuses_overwrite(tmp_path):
    src = tmp_path / "f.txt"
    dst = tmp_path / "g.txt"
    src.write_text("orig")
    dst.write_text("moved")
    with pytest.raises(FileExistsError):
        undo_move(dst, src)


def test_destination_private_and_review(tmp_path):
    src = tmp_path / "doc.pdf"
    src.write_text("x")
    r = Classification(category="IDs", title="passport", confidence=0.95, sensitive=True)
    assert destination(r, src, tmp_path, "Private", "_Review", "{title}") == tmp_path / "Private" / "doc.pdf"
    r2 = Classification(category="School", title="lecture", confidence=0.9, sensitive=False)
    d = destination(r2, src, tmp_path, "Private", "_Review", "{date}_{title}")
    assert d.parent.name == "School" and d.name.endswith("lecture.pdf")
    d3 = destination(r2, src, tmp_path, "Private", "_Review", "{title}", review_reason=True)
    assert d3.parent.name == "_Review"


def test_safe_move_never_overwrites(tmp_path):
    dst = tmp_path / "dst" / "f.txt"
    dst.parent.mkdir()
    dst.write_text("existing")
    src = tmp_path / "src" / "f.txt"
    src.parent.mkdir()
    src.write_text("new")
    final = safe_move(src, dst)
    assert final.name == "f_2.txt"
    assert dst.read_text() == "existing" and final.read_text() == "new"


def test_cross_volume_removes_source(tmp_path, monkeypatch):
    # simulate differing st_dev so safe_move takes the copy-verify path
    src = tmp_path / "src" / "f.txt"; src.parent.mkdir(); src.write_text("data")
    dst = tmp_path / "dst" / "f.txt"; dst.parent.mkdir()
    real_stat = Path.stat

    class FakeStat:
        def __init__(self, r, dev):
            self._r = r
            self.st_dev = dev
        def __getattr__(self, n):
            return getattr(self._r, n)

    def fake_stat(self, *a, **k):
        r = real_stat(self, *a, **k)
        dev = 1 if str(self).startswith(str(tmp_path / "src")) else 2
        return FakeStat(r, dev)

    monkeypatch.setattr(Path, "stat", fake_stat)
    final = safe_move(src, dst)
    assert final.read_text() == "data" and not src.exists()
