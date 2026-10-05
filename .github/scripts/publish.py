#!/usr/bin/env python3
"""Publish the next queued entry from upcoming/.

Entries are written ahead of time in batches and released one per run by the
scheduled `publish` workflow. Each run moves the lowest-numbered item into its
dated folder, re-runs its tests, adds a row to the README index and commits.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
import zoneinfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "upcoming"
README = ROOT / "README.md"
LANG_DIRS = {"Python": "python", "TypeScript": "typescript", "Java": "java", "C++": "cpp"}
AUTHOR = ("Sebas", "sebasbecerra70@gmail.com")


def test_command(path: Path) -> str:
    if (path / "package.json").exists():
        return "npm install --no-audit --no-fund --silent && npm test"
    if (path / "SolutionTest.java").exists():
        return "javac *.java && java -ea SolutionTest"
    if (path / "solution.test.ts").exists():
        return "npx --yes tsx --test solution.test.ts"
    if (path / "test.cpp").exists():
        return "g++ -std=c++17 -Wall -o test test.cpp && ./test"
    return "python -m pytest -q"


def clean(path: Path) -> None:
    for pattern in ("**/__pycache__", "**/.pytest_cache", "**/node_modules", "**/*.class", "test"):
        for p in path.glob(pattern):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.suffix == ".class" or (p.name == "test" and p.parent == path):
                p.unlink()


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def destination(meta: dict, date: str) -> Path:
    if "language" in meta:  # code-a-day layout
        base = ROOT / LANG_DIRS[meta["language"]]
    else:  # ai-lab layout
        base = ROOT / "projects"
    dest = base / f"{date}-{meta['slug']}"
    n = 2
    while dest.exists():
        dest = base / f"{date}-{meta['slug']}-{n}"
        n += 1
    return dest


def index_row(meta: dict, date: str, rel: str) -> str:
    if "language" in meta:
        return f"| {date} | {meta['title']} | {meta['language']} | [{rel}]({rel}) |"
    return (
        f"| {date} | [{meta['title']}]({rel}): {meta['summary']} "
        f"| {meta['technique']} | {meta['domain']} | {meta['stack']} |"
    )


def add_to_index(row: str) -> None:
    text = README.read_text()
    marker = "<!-- INDEX:END -->"
    if marker not in text:
        sys.exit("README is missing the INDEX:END marker")
    README.write_text(text.replace(marker, f"{row}\n{marker}", 1))


def main() -> int:
    date = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date().isoformat()
    queued = sorted(p for p in QUEUE.glob("[0-9]*") if p.is_dir() and not (p / ".skip").exists())
    if not queued:
        print("Queue is empty; nothing to publish.")
        return 0

    flagged = False
    for item in queued:
        if not (item / "meta.json").exists():
            print(f"::warning::{item.name} has no meta.json; skipping")
            continue
        meta = json.loads((item / "meta.json").read_text())
        cmd = test_command(item)
        print(f"== {item.name}: {cmd}", flush=True)
        if subprocess.run(cmd, shell=True, cwd=item).returncode != 0:
            # Leave it queued but flagged so the next run moves on.
            clean(item)
            (item / ".skip").write_text("tests failed during publish\n")
            git("add", str(item))
            flagged = True
            continue
        clean(item)
        dest = destination(meta, date)
        dest.parent.mkdir(parents=True, exist_ok=True)
        git("mv", str(item), str(dest))
        (dest / "meta.json").unlink()
        rel = dest.relative_to(ROOT).as_posix()
        add_to_index(index_row(meta, date, rel))
        git("add", "-A")
        title = meta["title"]
        suffix = f" ({meta['language']})" if "language" in meta else ""
        git(
            "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}",
            "commit", "-q", "-m", f"Add {title}{suffix}",
            "-m", "Co-Authored-By: Claude <noreply@anthropic.com>",
        )
        print(f"Published {rel}")
        return 0

    print("::warning::no publishable entry in the queue")
    if flagged:
        # Commit the skip markers so failing entries aren't retried forever.
        git("-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}",
            "commit", "-q", "-m", "Flag queued entries whose tests failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
