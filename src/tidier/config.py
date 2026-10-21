"""YAML configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Models(BaseModel):
    text: str = "qwen2.5:3b"
    vision: str = "qwen2.5vl:3b"


class Config(BaseModel):
    watch_path: Path = Path("~/Downloads")
    destination_root: Path = Path("~/Downloads/Sorted")
    models: Models = Field(default_factory=Models)
    ollama_host: str = "http://localhost:11434"
    confidence_threshold: float = 0.65
    stability_polls: int = 3
    stability_interval: float = 2.0
    mode: str = "realtime"  # realtime | batch
    batch_schedule: str = "02:00"
    idle_only: bool = True
    categories: list[str] = Field(
        default_factory=lambda: ["School", "Receipts", "IDs", "Work", "Media", "Misc"]
    )
    private_folder: str = "Private"
    review_folder: str = "_Review"
    naming: str = "{date}_{category}_{title}"
    digest: bool = True

    @property
    def watch(self) -> Path:
        return self.watch_path.expanduser()

    @property
    def root(self) -> Path:
        return self.destination_root.expanduser()


DEFAULT_CONFIG_PATH = Path("~/.config/tidier/config.yaml")


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    path = path.expanduser()
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    else:
        # Fall back to ./config.yaml if present, else defaults
        local = Path("config.yaml")
        data = yaml.safe_load(local.read_text()) if local.exists() else {}
    return Config(**(data or {}))
