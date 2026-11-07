#!/usr/bin/env python3
"""Extract SWORD commentary modules into backend/data/commentary.db.

One-time build step. Resumable: progress is checkpointed per (module, book,
chapter), so re-running picks up where it left off.

Why one diatheke call per verse rather than per chapter:
    diatheke labels entries as "John 3:16:" at line start, and commentary prose
    is dense with scripture citations in exactly that form. A chapter-level
    parse bleeds entries into each other. Querying a single verse means the
    label is a string we already know, so stripping it is unambiguous.

Why entries are sparse:
    Matthew Henry attaches one note to a span of verses, keyed at the span's
    first verse; the rest of the span returns empty. JFB and Barnes are
    genuinely per-verse. commentary.py resolves this at lookup time by walking
    backward to the nearest verse in the chapter that carries text.

    .venv/bin/python scripts/extract_commentary.py [--modules MHCC,JFB] [--books John,Rom]
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "sword"
DB_PATH = ROOT / "backend" / "data" / "commentary.db"

# module -> (display name, tradition)
MODULES: dict[str, tuple[str, str]] = {
    "MHCC": ("Matthew Henry's Concise Commentary", "Puritan"),
    "JFB": ("Jamieson, Fausset & Brown", "Scottish Presbyterian"),
    "Geneva": ("Geneva Bible Notes", "Reformed"),
}

# The Geneva module ships no DistributionLicense field. Its underlying text is
# the 1560/1599 Geneva Bible notes, public domain by age.
LICENSE_OVERRIDES: dict[str, str] = {
    "Geneva": "Public Domain (1560/1599 text; module declares none)",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
    module    TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    tradition TEXT NOT NULL,
    license   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commentary (
    module  TEXT NOT NULL,
    book    TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    verse   INTEGER NOT NULL,
    text    TEXT NOT NULL,
    PRIMARY KEY (module, book, chapter, verse)
);
CREATE INDEX IF NOT EXISTS commentary_lookup
    ON commentary (module, book, chapter, verse);
CREATE TABLE IF NOT EXISTS progress (
    module  TEXT NOT NULL,
    book    TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    PRIMARY KEY (module, book, chapter)
);
"""


def module_license(module: str) -> str:
    """Read the module's declared license, falling back to an explicit override."""
    if module in LICENSE_OVERRIDES:
        return LICENSE_OVERRIDES[module]
    for conf in (VENDOR / "mods.d").glob("*.conf"):
        text = conf.read_text(errors="replace")
        if not re.search(rf"^\[{re.escape(module)}\]", text, re.M):
            continue
        match = re.search(r"^DistributionLicense=(.*)$", text, re.M)
        if match and match.group(1).strip():
            return match.group(1).strip()
        return "undeclared"
    return "unknown (module not found)"


def versification() -> list[tuple[str, int, int]]:
    """(book, chapter, verse_count) from the KJV module, which is the
    versification MHCC/JFB/TDavid declare. pysword reads zText modules."""
    from pysword.modules import SwordModules

    modules = SwordModules(str(VENDOR))
    modules.parse_modules()
    bible = modules.get_bible_from_module("KJV")
    structure = bible.get_structure()

    rows: list[tuple[str, int, int]] = []
    for testament in ("ot", "nt"):
        for book in structure.get_books()[testament]:
            for chapter_index, verse_count in enumerate(book.chapter_lengths, start=1):
                rows.append((book.name, chapter_index, verse_count))
    return rows


_ENV = {**os.environ, "SWORD_PATH": str(VENDOR)}


def fetch_verse(module: str, book: str, chapter: int, verse: int) -> str:
    key = f"{book} {chapter}:{verse}"
    try:
        result = subprocess.run(
            ["diatheke", "-b", module, "-f", "plain", "-k", key],
            capture_output=True, text=True, env=_ENV, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return ""
    out = result.stdout
    # Strip the trailing "(MODULE)" marker and the leading label we asked for.
    out = re.sub(rf"\({re.escape(module)}\)\s*$", "", out).strip()
    prefix = f"{key}:"
    if out.startswith(prefix):
        out = out[len(prefix):]
    return " ".join(out.split()).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modules", help="comma-separated subset")
    parser.add_argument("--books", help="comma-separated subset, for smoke tests")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    selected = list(MODULES) if not args.modules else args.modules.split(",")
    book_filter = set(args.books.split(",")) if args.books else None

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)

    for module in selected:
        name, tradition = MODULES[module]
        db.execute(
            "INSERT OR REPLACE INTO modules VALUES (?,?,?,?)",
            (module, name, tradition, module_license(module)),
        )
    db.commit()

    print("reading KJV versification...")
    all_chapters = versification()
    print(f"  {len(all_chapters)} chapters, {sum(v for _, _, v in all_chapters)} verses")

    done = {
        (m, b, c)
        for m, b, c in db.execute("SELECT module, book, chapter FROM progress")
    }

    for module in selected:
        todo = [
            (b, c, n)
            for b, c, n in all_chapters
            if (book_filter is None or b in book_filter)
            and (module, b, c) not in done
        ]
        if not todo:
            print(f"{module}: nothing to do")
            continue

        total_verses = sum(n for _, _, n in todo)
        print(f"{module}: {len(todo)} chapters / {total_verses} verses")
        started = time.time()
        stored = 0

        for index, (book, chapter, verse_count) in enumerate(todo, start=1):
            verses = range(1, verse_count + 1)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                texts = list(
                    pool.map(lambda v: fetch_verse(module, book, chapter, v), verses)
                )
            rows = [
                (module, book, chapter, verse, text)
                for verse, text in zip(verses, texts)
                if text
            ]
            if rows:
                db.executemany(
                    "INSERT OR REPLACE INTO commentary VALUES (?,?,?,?,?)", rows
                )
                stored += len(rows)
            db.execute(
                "INSERT OR REPLACE INTO progress VALUES (?,?,?)", (module, book, chapter)
            )
            db.commit()

            if index % 25 == 0 or index == len(todo):
                elapsed = time.time() - started
                rate = index / elapsed if elapsed else 0
                remaining = (len(todo) - index) / rate if rate else 0
                print(
                    f"  {index}/{len(todo)} chapters, {stored} entries, "
                    f"{rate:.1f} ch/s, ~{remaining / 60:.1f} min left",
                    flush=True,
                )

    print("\ncoverage:")
    for module, entries, books, chars in db.execute(
        "SELECT module, COUNT(*), COUNT(DISTINCT book), SUM(LENGTH(text)) "
        "FROM commentary GROUP BY module ORDER BY module"
    ):
        print(f"  {module:8s} {entries:7d} entries  {books:2d} books  {chars / 1e6:.1f} M chars")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
