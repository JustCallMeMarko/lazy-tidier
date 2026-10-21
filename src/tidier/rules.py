"""Extension-based fast-path: no AI call for obvious file types."""

from __future__ import annotations

from pathlib import Path

INSTALLERS = {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage"}
ARCHIVES = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}

RULES = {ext: "Installers" for ext in INSTALLERS} | {
    ext: "Archives" for ext in ARCHIVES
}

# Temp/partial download extensions the watcher ignores
TEMP_EXTENSIONS = {".crdownload", ".part", ".tmp", ".download", ".partial", ".opdownload"}


def fast_path(path: Path) -> str | None:
    """Return a destination folder name for rule-covered extensions, else None."""
    return RULES.get(path.suffix.lower())


def is_temporary(path: Path) -> bool:
    return path.suffix.lower() in TEMP_EXTENSIONS or path.name.startswith(".")
