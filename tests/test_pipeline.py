from pathlib import Path

from conftest import FakeLLM

from tidier.llm import Classification
from tidier.pipeline import is_stable, plan_file, process


def good(**kw):
    base = {"category": "Receipts", "title": "coffee-receipt", "confidence": 0.9, "sensitive": False}
    return Classification(**(base | kw))


def test_rule_fast_path_skips_llm(cfg, db, tmp_path):
    f = cfg.watch / "setup.msi"
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f.write_text("x")
    llm = FakeLLM()
    plan = plan_file(f, cfg, db, llm)
    assert plan.via == "rule" and plan.dst.parent.name == "Installers"
    assert llm.calls == []


def test_low_confidence_goes_to_review(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "mystery.txt"
    f.write_text("hmm")
    plan = plan_file(f, cfg, db, FakeLLM(good(confidence=0.3)))
    assert plan.via == "review" and plan.dst.parent.name == "_Review"


def test_sensitive_goes_private_and_not_cached(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "passport-scan.txt"
    f.write_text("passport no 123")
    plan = plan_file(f, cfg, db, FakeLLM(good(category="IDs", sensitive=True)))
    assert plan.dst.parent.name == "Private"
    assert db.cache_get("anything") is None
    from tidier.mover import sha256_of
    assert db.cache_get(sha256_of(f)) is None  # sensitive text never cached


def test_cache_hit_skips_llm(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "doc.txt"
    f.write_text("some content")
    llm = FakeLLM(good())
    plan_file(f, cfg, db, llm)
    assert len(llm.calls) == 1
    plan2 = plan_file(f, cfg, db, llm)
    assert plan2.via == "cache" and len(llm.calls) == 1


def test_none_result_goes_review(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "bad.txt"
    f.write_text("x")
    plan = plan_file(f, cfg, db, FakeLLM(None))
    assert plan.via == "review"


def test_execute_moves_and_logs(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "invoice.txt"
    f.write_text("invoice total 42")
    process(f, cfg, db, FakeLLM(good()), dry_run=False)
    moves = db.recent_moves(1)
    assert len(moves) == 1
    dst = Path(moves[0]["dst_path"])
    assert dst.exists() and not f.exists()
    assert dst.parent.name == "Receipts"


def test_dry_run_changes_nothing(cfg, db):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "invoice.txt"
    f.write_text("invoice total 42")
    before = {p.name: p.read_bytes() for p in cfg.watch.rglob("*") if p.is_file()}
    process(f, cfg, db, FakeLLM(good()), dry_run=True)
    after = {p.name: p.read_bytes() for p in cfg.watch.rglob("*") if p.is_file()}
    assert before == after and not cfg.root.exists()


def test_stability(cfg):
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "f.txt"
    f.write_text("x")
    assert is_stable(f, polls=2, interval=0.01)
    assert not is_stable(cfg.watch / "missing.txt", polls=2, interval=0.01)


def test_undo_via_db(cfg, db):
    from tidier.mover import undo_move
    cfg.watch.mkdir(parents=True, exist_ok=True)
    f = cfg.watch / "a.txt"
    f.write_text("data")
    process(f, cfg, db, FakeLLM(good()), dry_run=False)
    m = db.recent_moves(1)[0]
    undo_move(Path(m["dst_path"]), Path(m["src_path"]))
    db.mark_undone(m["id"])
    assert f.exists() and db.recent_moves(1) == []
