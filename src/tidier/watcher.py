"""Filesystem watcher: enqueue new stable files under the watch path."""

from __future__ import annotations

import threading
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import pipeline, rules
from .config import Config
from .db import DB


class _Handler(FileSystemEventHandler):
    def __init__(self, cfg: Config, db: DB):
        self.cfg = cfg
        self.db = db

    def _maybe_enqueue(self, path: Path):
        if not path.is_file() or rules.is_temporary(path):
            return
        # Skip files already inside the sorted output tree
        try:
            path.relative_to(self.cfg.root)
            return
        except ValueError:
            pass
        # A failed stability check (still downloading) retries a bounded number
        # of times so the finished file is not forgotten.
        for _ in range(5):
            if pipeline.is_stable(path, self.cfg.stability_polls, self.cfg.stability_interval):
                self.db.enqueue(path)
                return

    def on_created(self, event):
        if not event.is_directory:
            threading.Thread(
                target=self._maybe_enqueue, args=(Path(event.src_path),), daemon=True
            ).start()

    def on_moved(self, event):
        if not event.is_directory:
            threading.Thread(
                target=self._maybe_enqueue, args=(Path(event.dest_path),), daemon=True
            ).start()


def watch(cfg: Config, db: DB) -> Observer:
    handler = _Handler(cfg, db)
    observer = Observer()
    observer.schedule(handler, str(cfg.watch), recursive=False)
    observer.start()
    return observer
