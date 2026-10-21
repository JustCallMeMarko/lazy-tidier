"""tidy CLI: run | dry-run | once | undo | status | digest."""

from __future__ import annotations

import time
from pathlib import Path

import typer

from .config import Config, load_config
from .db import DB
from .digest import digest as make_digest
from .llm import LLM
from .mover import undo_move
from .pipeline import plan_file, process
from .rules import is_temporary
from .watcher import watch

app = typer.Typer(help="Lazy File Tidier — sorts your Downloads with local AI.")


def _ctx(config: Path | None) -> tuple[Config, DB]:
    cfg = load_config(config)
    db = DB(cfg.root / ".tidier.db")
    return cfg, db


def _llm(cfg: Config) -> LLM | None:
    try:
        llm = LLM(cfg.ollama_host, cfg.models.text, cfg.models.vision)
        return llm if llm.health() else None
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    except Exception:
        return None


def _print_plan(plan, dry_run: bool):
    arrow = "->" if not dry_run else "~>"
    tag = f"[{plan.via}]" + (f" {plan.note}" if plan.note else "")
    typer.echo(f"  {plan.src.name} {arrow} {plan.dst}  {tag}")


def _process_path(path: Path, cfg: Config, db: DB, llm: LLM | None, dry: bool):
    if not path.is_file() or is_temporary(path):
        return
    try:
        plan = process(path, cfg, db, llm, dry)
        _print_plan(plan, dry)
    except Exception as e:
        typer.echo(f"  {path.name}: failed ({e})", err=True)


@app.command()
def run(config: Path | None = typer.Option(None, "--config", "-c")):
    """Start the watcher and process files as they arrive."""
    cfg, db = _ctx(config)
    llm = _llm(cfg)
    if llm is None:
        typer.echo("warning: Ollama unreachable — files will queue until it is up", err=True)
    cfg.watch.mkdir(parents=True, exist_ok=True)
    observer = watch(cfg, db)
    typer.echo(f"Watching {cfg.watch} -> {cfg.root}  (Ctrl+C to stop)")
    try:
        while True:
            if llm is None:
                llm = _llm(cfg)
            for p in db.pending():
                _process_path(Path(p), cfg, db, llm, dry=False)
                db.set_status(p, "done")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


@app.command()
def once(config: Path | None = typer.Option(None, "--config", "-c")):
    """Process everything currently in the watch folder, then exit."""
    cfg, db = _ctx(config)
    llm = _llm(cfg)
    for path in sorted(cfg.watch.iterdir()):
        _process_path(path, cfg, db, llm, dry=False)


@app.command(name="dry-run")
def dry_run(config: Path | None = typer.Option(None, "--config", "-c")):
    """Print planned moves for existing files; change nothing."""
    cfg, db = _ctx(config)
    llm = _llm(cfg)
    if llm is None:
        typer.echo("warning: Ollama unreachable — review-folder plans only", err=True)
    for path in sorted(cfg.watch.iterdir()):
        if not path.is_file() or is_temporary(path):
            continue
        try:
            _print_plan(plan_file(path, cfg, db, llm), dry_run=True)
        except Exception as e:
            typer.echo(f"  {path.name}: failed ({e})", err=True)


@app.command()
def undo(
    last: int = typer.Option(1, "--last", "-n"),
    config: Path | None = typer.Option(None, "--config", "-c"),
):
    """Reverse the last N moves."""
    _cfg, db = _ctx(config)
    for m in reversed(db.recent_moves(last)):
        src, dst = Path(m["src_path"]), Path(m["dst_path"])
        try:
            undo_move(dst, src)
            db.mark_undone(m["id"])
            typer.echo(f"  restored {src}")
        except (FileNotFoundError, FileExistsError) as e:
            typer.echo(f"  skipped {dst.name}: {e}", err=True)


@app.command()
def status(config: Path | None = typer.Option(None, "--config", "-c")):
    """Show queue, recent moves, and model health."""
    cfg, db = _ctx(config)
    try:
        llm = LLM(cfg.ollama_host, cfg.models.text, cfg.models.vision)
        healthy = llm.health()
    except RuntimeError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Ollama ({cfg.ollama_host}): {'up' if healthy else 'DOWN'}")
    typer.echo(f"Queue: {db.queue_counts() or 'empty'}")
    moves = db.recent_moves(10)
    if moves:
        typer.echo("Recent moves:")
        for m in moves:
            typer.echo(f"  [{m['ts'][:10]}] {Path(m['src_path']).name} -> {m['dst_path']}")


@app.command()
def digest(
    hours: int = typer.Option(24, "--hours"),
    config: Path | None = typer.Option(None, "--config", "-c"),
):
    """Print a summary of recent activity."""
    _cfg, db = _ctx(config)
    typer.echo(make_digest(db, hours))


def main():
    app()


if __name__ == "__main__":
    main()
