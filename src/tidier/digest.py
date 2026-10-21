"""Daily digest of moves."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .db import DB


def digest(db: DB, hours: int = 24) -> str:
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    moves = db.moves_since(since)
    if not moves:
        return f"Nothing sorted in the last {hours}h."
    counts = Counter(m["category"] or "review" for m in moves)
    private = sum(1 for m in moves if m["sensitive"])
    lines = [f"Tidied {len(moves)} file(s) in the last {hours}h:"]
    for cat, n in counts.most_common():
        lines.append(f"  {cat}: {n}")
    if private:
        lines.append(f"  ({private} routed to Private/)")
    lines.append("")
    for m in moves[:15]:
        lines.append(f"  {Path(m['src_path']).name} -> {m['dst_path']}")
    if len(moves) > 15:
        lines.append(f"  …and {len(moves) - 15} more")
    return "\n".join(lines)
