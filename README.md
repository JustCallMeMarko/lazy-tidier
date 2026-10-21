# Lazy File Tidier

Your Downloads folder, sorted while you do nothing.

A local, offline background agent that watches your Downloads folder, reads each
new file with open-weight models via Ollama, renames it sensibly, and moves it
into the right folder. **No file content ever leaves your machine.**

## Quickstart

```bash
# one-time: install Ollama (https://ollama.com) and pull the models
ollama pull qwen2.5:3b
ollama pull qwen2.5vl:3b

git clone <this repo> && cd lazy-tidier
uv run tidy dry-run     # see what it would do — changes nothing
uv run tidy run         # start the watcher
```

From clone to first dry-run: under 5 minutes (plus the one-time model pull).

## Commands

| Command | Purpose |
| --- | --- |
| `tidy run` | Watch the folder and sort files as they arrive |
| `tidy dry-run` | Print planned moves for existing files; change nothing |
| `tidy once` | Process everything currently in the folder, then exit |
| `tidy undo --last N` | Reverse the last N moves |
| `tidy status` | Queue, recent moves, and Ollama health |
| `tidy digest` | Summary of the last 24 h of sorting |

## How it works

```
Downloads ──events──► Watcher ──► Stability check ──► SQLite queue
                                                        │
   Rules fast-path ◄── Extractor (PyMuPDF/OCR/docx) ◄── Worker
        │                     │
        ▼                     ▼
   Mover ◄── Validator ◄── Ollama (localhost only)
        │
        ▼
   Move log (undoable) + Daily digest
```

- **Safe by default:** never deletes, never overwrites (`_2` suffix on
  collisions), atomic moves with copy-verify-delete across volumes, and every
  move is logged so `tidy undo` restores files exactly.
- **Privacy:** the only network target is `localhost:11434`. A startup check
  refuses to run against a non-loopback Ollama host. Files flagged `sensitive`
  (IDs, bank statements, medical records) go to `Private/` and their text is
  never written to logs, the DB, or the cache.
- **Low confidence?** Ambiguous files land in `_Review/` instead of being misfiled.
- **Cheap:** installers and archives skip the model entirely; identical files
  (by SHA-256) reuse cached classifications.

## Configuration

`config.yaml` (repo root or `~/.config/tidier/config.yaml`):

```yaml
watch_path: ~/Downloads
destination_root: ~/Downloads/Sorted
models:
  text: qwen2.5:3b      # swap to qwen2.5:7b for higher accuracy
  vision: qwen2.5vl:3b
confidence_threshold: 0.65
categories: [School, Receipts, IDs, Work, Media, Misc]
naming: "{date}_{category}_{title}"
```

Swapping models is a one-line edit — everything else stays the same.

## Development

```bash
uv sync
uv run pytest          # unit + integration tests (mocked Ollama)
uv run ruff check
uv run python eval/run_eval.py   # accuracy eval on eval/corpus vs labels.csv
```

## Why open-weight models

- **Privacy** — IDs, receipts, and school records stay on your machine.
- **Offline** — works with zero internet (demo it in airplane mode).
- **Cost** — $0 per file, forever.
- **Swappable / tunable** — one-line model swaps; prompt and taxonomy are yours.
