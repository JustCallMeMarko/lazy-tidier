"""Per-file processing pipeline shared by run/dry-run/once."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import extract, mover, rules, validate
from .config import Config
from .db import DB
from .llm import LLM, Classification


@dataclass
class Plan:
    src: Path
    dst: Path
    category: str | None
    confidence: float | None
    sensitive: bool
    via: str  # rule | cache | model | review | error
    note: str = ""


def is_stable(path: Path, polls: int = 3, interval: float = 2.0) -> bool:
    """True after `polls` consecutive identical (size, mtime) observations and the
    file is readable. Any change restarts the count; bounded by 5x polls."""
    try:
        last = (path.stat().st_size, path.stat().st_mtime)
    except OSError:
        return False
    same = 1
    attempts = 0
    while same < polls and attempts < polls * 5:
        time.sleep(interval)
        attempts += 1
        try:
            current = (path.stat().st_size, path.stat().st_mtime)
        except OSError:
            return False
        if current != last:
            last = current
            same = 1
            continue
        same += 1
    if same < polls:
        return False
    try:
        with path.open("rb"):
            pass
    except OSError:
        return False
    return True


def _cache_key(path: Path) -> str:
    return f"{mover.sha256_of(path)}|{path.name}"


def needs_model(path: Path, cfg: Config, db: DB) -> bool:
    """False when the file can be routed without a model (rule, cache hit,
    or nothing extractable — those go to _Review without a model call).
    Unreadable files return True (held pending — likely a transient error);
    callers should check existence first."""
    if rules.fast_path(path):
        return False
    try:
        if db.cache_get(_cache_key(path), cfg.models.text) is not None or \
                db.cache_get(_cache_key(path), cfg.models.vision) is not None:
            return False
    except OSError:
        return True
    result = extract.extract(path)
    extract.cleanup(result)
    return bool(result.text or result.image_path)


def plan_file(path: Path, cfg: Config, db: DB, llm: LLM | None) -> Plan:
    """Decide where a file should go. Pure — touches nothing."""
    dst_root = cfg.root

    folder = rules.fast_path(path)
    if folder:
        return Plan(path, dst_root / folder / path.name, folder, 1.0, False, "rule")

    cached = db.cache_get(_cache_key(path), cfg.models.text) or \
        db.cache_get(_cache_key(path), cfg.models.vision)
    if cached:
        result = Classification.model_validate(cached)
        if result.confidence < cfg.confidence_threshold and not result.sensitive:
            return Plan(path, dst_root / cfg.review_folder / path.name,
                        result.category, result.confidence, False, "cache",
                        "low confidence")
        dst = mover.destination(result, path, dst_root, cfg.private_folder,
                                cfg.review_folder, cfg.naming)
        return Plan(path, dst, result.category, result.confidence, result.sensitive, "cache")

    if llm is None:
        return Plan(path, dst_root / cfg.review_folder / path.name, None, None, False,
                    "review", "no model available")

    result_ex = extract.extract(path)
    model_used = cfg.models.text
    try:
        if result_ex.image_path and (result_ex.kind == "image" or not result_ex.text):
            cls = llm.classify_image(path.name, result_ex.image_path)
            model_used = cfg.models.vision
        elif result_ex.text:
            cls = llm.classify_text(path.name, result_ex.text)
        else:
            cls = None
    finally:
        extract.cleanup(result_ex)

    if cls is None:
        return Plan(path, dst_root / cfg.review_folder / path.name, None, None, False,
                    "review", f"extract={result_ex.kind}")

    try:
        result = validate.validate(cls, cfg.categories, cfg.confidence_threshold)
    except ValueError:
        return Plan(path, dst_root / cfg.review_folder / path.name, cls.category,
                    cls.confidence, cls.sensitive, "review", "bad category")

    if not result.sensitive:
        db.cache_put(_cache_key(path), result.model_dump(), model_used)

    if result.confidence < cfg.confidence_threshold and not result.sensitive:
        return Plan(path, dst_root / cfg.review_folder / path.name, result.category,
                    result.confidence, False, "review", "low confidence")

    dst = mover.destination(result, path, dst_root, cfg.private_folder,
                            cfg.review_folder, cfg.naming)
    return Plan(path, dst, result.category, result.confidence, result.sensitive, "model")


def execute(plan: Plan, cfg: Config, db: DB) -> Path:
    """Perform a planned move and log it. Returns final destination."""
    sha = mover.sha256_of(plan.src)
    dst = mover.safe_move(plan.src, plan.dst)
    db.log_move(plan.src, dst, sha, plan.category, plan.confidence, plan.sensitive)
    return dst


def process(path: Path, cfg: Config, db: DB, llm: LLM | None, dry_run: bool) -> Plan:
    plan = plan_file(path, cfg, db, llm)
    if not dry_run and plan.src.exists():
        plan.dst = execute(plan, cfg, db)
    return plan
