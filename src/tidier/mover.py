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


def _link_into(src: Path, dst: Path) -> Path:
    """Hard-link src to a collision-free name (atomic: never overwrites an
    existing file), then unlink src. Returns the final destination."""
    for i in range(1000):
        cand = dst if i == 0 else dst.with_name(f"{dst.stem}_{i + 1}{dst.suffix}")
        try:
            os.link(src, cand)
            src.unlink()
            return cand
        except FileExistsError:
            continue
    raise RuntimeError(f"could not resolve collision for {dst}")


def safe_move(src: Path, dst: Path) -> Path:
    """Move src toward dst without data loss or overwriting an existing file.
    Atomic link+unlink on one volume; copy-to-temp, hash-verify, then atomic
    link across volumes. Returns the final destination path."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.stat().st_dev == dst.parent.stat().st_dev:
        return _link_into(src, dst)
    digest = sha256_of(src)
    tmp = dst.with_name(dst.name + ".tidier-partial")
    try:
        shutil.copy2(src, tmp)
        if sha256_of(tmp) != digest:
            raise OSError(f"copy verification failed for {src}")
        return _link_into(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


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
