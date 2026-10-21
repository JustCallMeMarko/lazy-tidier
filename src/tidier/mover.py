"""Safe file moves: collision handling, atomic/cross-volume move, undo."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

from .llm import Classification


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def resolve_collision(dst: Path) -> Path:
    """Return dst, or dst with _2/_3 suffix if it already exists."""
    if not dst.exists():
        return dst
    for i in range(2, 1000):
        candidate = dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not resolve collision for {dst}")


def safe_move(src: Path, dst: Path):
    """Move src to dst without data loss: atomic on same volume,
    copy-hash-verify-delete across volumes."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.stat().st_dev == dst.parent.stat().st_dev:
        os.replace(src, dst)
        return
    digest = sha256_of(src)
    shutil.copy2(src, dst)
    if sha256_of(dst) != digest:
        dst.unlink(missing_ok=True)
        raise OSError(f"copy verification failed for {src}")
    src.unlink()


def build_name(result: Classification, ext: str, naming: str, fallback_ts: float) -> str:
    date = result.date or datetime.fromtimestamp(fallback_ts).strftime("%Y-%m-%d")
    name = naming.format(date=date, category=result.category, title=result.title)
    return name + ext


def destination(
    result: Classification,
    src: Path,
    root: Path,
    private_folder: str,
    review_folder: str,
    naming: str,
    review_reason: bool = False,
    rule_folder: str | None = None,
) -> Path:
    """Compute the destination path for a file."""
    ext = src.suffix
    if review_reason:
        return root / review_folder / src.name
    if result.sensitive:
        return root / private_folder / src.name
    if rule_folder:
        return root / rule_folder / src.name
    folder = root / result.category
    if result.subfolder:
        folder = folder / result.subfolder
    dst = folder / build_name(result, ext, naming, src.stat().st_mtime)
    # model-supplied path parts can never escape the sorted root
    if not dst.resolve().is_relative_to(root.resolve()):
        return root / review_folder / src.name
    return dst


def undo_move(dst: Path, src: Path):
    """Reverse a logged move. Raises if the moved file no longer exists."""
    if not dst.exists():
        raise FileNotFoundError(f"{dst} no longer exists (moved or deleted?)")
    if src.exists():
        raise FileExistsError(f"{src} already exists — refusing to overwrite")
    src.parent.mkdir(parents=True, exist_ok=True)
    safe_move(dst, src)
