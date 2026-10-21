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
    """True when size+mtime are unchanged across `polls` checks and file is readable."""
    try:
        last = (path.stat().st_size, path.stat().st_mtime)
    except OSError:
        return False
    for _ in range(polls - 1):
        time.sleep(interval)
        try:
            current = (path.stat().st_size, path.stat().st_mtime)
        except OSError:
            return False
        if current != last:
            last = current
    try:
        with path.open("rb"):
            pass
    except OSError:
        return False
    return True


def plan_file(path: Path, cfg: Config, db: DB, llm: LLM | None) -> Plan:
    """Decide where a file should go. Pure — touches nothing."""
    dst_root = cfg.root

    folder = rules.fast_path(path)
    if folder:
        return Plan(path, dst_root / folder / path.name, folder, 1.0, False, "rule")

    sha = mover.sha256_of(path)
    if cached := db.cache_get(sha):
        result = Classification.model_validate(cached)
        dst = mover.destination(result, path, dst_root, cfg.private_folder,
                                cfg.review_folder, cfg.naming)
        return Plan(path, dst, result.category, result.confidence, result.sensitive, "cache")

    if llm is None:
        return Plan(path, dst_root / cfg.review_folder / path.name, None, None, False,
                    "review", "no model available")

    result_ex = extract.extract(path)
    try:
        if result_ex.image_path and not result_ex.text:
            cls = llm.classify_image(path.name, result_ex.image_path)
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
        db.cache_put(sha, result.model_dump(), llm.text_model)

    if result.confidence < cfg.confidence_threshold and not result.sensitive:
        return Plan(path, dst_root / cfg.review_folder / path.name, result.category,
                    result.confidence, False, "review", "low confidence")

    dst = mover.destination(result, path, dst_root, cfg.private_folder,
                            cfg.review_folder, cfg.naming)
    return Plan(path, dst, result.category, result.confidence, result.sensitive, "model")


def execute(plan: Plan, cfg: Config, db: DB) -> Path:
    """Perform a planned move and log it. Returns final destination."""
    dst = mover.resolve_collision(plan.dst)
    sha = mover.sha256_of(plan.src)
    mover.safe_move(plan.src, dst)
    db.log_move(plan.src, dst, sha, plan.category, plan.confidence, plan.sensitive)
    return dst


def process(path: Path, cfg: Config, db: DB, llm: LLM | None, dry_run: bool) -> Plan:
    plan = plan_file(path, cfg, db, llm)
    if not dry_run and plan.src.exists():
        plan.dst = execute(plan, cfg, db)
    return plan
