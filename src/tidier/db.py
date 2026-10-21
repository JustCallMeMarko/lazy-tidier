"""SQLite storage: move log, work queue, hash cache."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS moves (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  src_path TEXT NOT NULL,
  dst_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  category TEXT,
  confidence REAL,
  sensitive INTEGER DEFAULT 0,
  undone INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cache (
  sha256 TEXT PRIMARY KEY,
  result_json TEXT NOT NULL,
  model TEXT NOT NULL,
  ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL,
  enqueued_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    # -- queue --
    def enqueue(self, path: Path):
        self.conn.execute(
            "INSERT OR IGNORE INTO queue (path, status, enqueued_at) VALUES (?, 'pending', ?)",
            (str(path), _now()),
        )
        self.conn.commit()

    def pending(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT path FROM queue WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return [r[0] for r in rows]

    def set_status(self, path: str, status: str):
        self.conn.execute(
            "UPDATE queue SET status = ? WHERE path = ?", (status, path)
        )
        self.conn.commit()

    def queue_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM queue GROUP BY status"
        ).fetchall()
        return dict(rows)

    # -- moves --
    def log_move(
        self,
        src: Path,
        dst: Path,
        sha256: str,
        category: str | None,
        confidence: float | None,
        sensitive: bool,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO moves (ts, src_path, dst_path, sha256, category, confidence, sensitive)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), str(src), str(dst), sha256, category, confidence, int(sensitive)),
        )
        self.conn.commit()
        return cur.lastrowid

    def recent_moves(self, n: int = 20, include_undone: bool = False) -> list[dict]:
        q = "SELECT id, ts, src_path, dst_path, category, confidence, sensitive, undone FROM moves"
        if not include_undone:
            q += " WHERE undone = 0"
        q += " ORDER BY id DESC LIMIT ?"
        cols = ["id", "ts", "src_path", "dst_path", "category", "confidence", "sensitive", "undone"]
        return [dict(zip(cols, r)) for r in self.conn.execute(q, (n,)).fetchall()]

    def moves_since(self, iso_ts: str) -> list[dict]:
        cols = ["id", "ts", "src_path", "dst_path", "category", "confidence", "sensitive", "undone"]
        rows = self.conn.execute(
            "SELECT id, ts, src_path, dst_path, category, confidence, sensitive, undone"
            " FROM moves WHERE ts >= ? ORDER BY id",
            (iso_ts,),
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def mark_undone(self, move_id: int):
        self.conn.execute("UPDATE moves SET undone = 1 WHERE id = ?", (move_id,))
        self.conn.commit()

    # -- cache --
    def cache_get(self, sha256: str) -> dict | None:
        row = self.conn.execute(
            "SELECT result_json FROM cache WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, sha256: str, result: dict, model: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO cache (sha256, result_json, model, ts) VALUES (?, ?, ?, ?)",
            (sha256, json.dumps(result), model, _now()),
        )
        self.conn.commit()
