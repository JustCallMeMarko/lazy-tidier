"""Validate and sanitize model output."""

from __future__ import annotations

import re
from datetime import datetime

from .llm import Classification

RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WS = re.compile(r"\s+")


def sanitize_title(title: str, max_len: int = 80) -> str:
    t = RESERVED.sub("-", title)
    t = WS.sub("-", t).strip("-_. ")
    return t[:max_len].rstrip("-_. ") or "untitled"


def sanitize_subfolder(sub: str | None) -> str | None:
    if not sub:
        return None
    s = sanitize_title(sub, max_len=40)
    if s == "untitled" or s in {".", ".."}:
        return None
    return s


def normalize_date(date: str | None) -> str | None:
    if not date:
        return None
    try:
        return datetime.strptime(date.strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def validate(
    result: Classification,
    categories: list[str],
    confidence_threshold: float,
) -> Classification:
    """Return a normalized Classification; raises ValueError on bad category."""
    cat = result.category.strip()
    if cat not in categories:
        raise ValueError(f"unknown category {cat!r}")
    return Classification(
        category=cat,
        subfolder=sanitize_subfolder(result.subfolder),
        title=sanitize_title(result.title),
        date=normalize_date(result.date),
        confidence=max(0.0, min(1.0, result.confidence)),
        sensitive=result.sensitive,
    )
