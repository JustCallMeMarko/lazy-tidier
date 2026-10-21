"""Run the pipeline over eval/corpus in dry-run mode and score against labels.csv.

Usage: uv run python eval/run_eval.py [--model qwen2.5:3b]
labels.csv columns: file,category,sensitive
"""

import argparse
import csv
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tidier.config import Config
from tidier.db import DB
from tidier.llm import LLM
from tidier.pipeline import plan_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:3b")
    ap.add_argument("--vision-model", default="qwen2.5vl:3b")
    ap.add_argument("--corpus", default=Path(__file__).parent / "corpus", type=Path)
    ap.add_argument("--labels", default=Path(__file__).parent / "labels.csv", type=Path)
    args = ap.parse_args()

    labels = {}
    with args.labels.open() as f:
        for row in csv.DictReader(f):
            labels[row["file"]] = (row["category"], row["sensitive"].lower() == "true")

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(
            watch_path=args.corpus,
            destination_root=Path(tmp) / "Sorted",
            models={"text": args.model, "vision": args.vision_model},
        )
        db = DB(Path(tmp) / "eval.db")
        llm = LLM(cfg.ollama_host, args.model, args.vision_model)

        correct = total = 0
        per_cat = Counter()
        misses = []
        times = []
        for file, (want_cat, want_sens) in sorted(labels.items()):
            path = args.corpus / file
            if not path.exists():
                print(f"missing corpus file: {file}", file=sys.stderr)
                continue
            t0 = time.time()
            plan = plan_file(path, cfg, db, llm)
            times.append(time.time() - t0)
            total += 1
            per_cat[want_cat] += 1
            got = "Private" if plan.sensitive else plan.category
            ok = (got == want_cat) if not want_sens else plan.sensitive
            if ok:
                correct += 1
            else:
                misses.append((file, want_cat, got, plan.confidence))

    print(f"\nModel: {args.model}")
    print(f"Accuracy: {correct}/{total} = {correct/total:.1%}" if total else "no files")
    if times:
        print(f"Avg seconds/file: {sum(times)/len(times):.1f}  max {max(times):.1f}")
    print("\nPer-category counts:", dict(per_cat))
    if misses:
        print("\nMisses:")
        for file, want, got, conf in misses:
            print(f"  {file}: want {want}, got {got} (conf {conf})")


if __name__ == "__main__":
    main()
