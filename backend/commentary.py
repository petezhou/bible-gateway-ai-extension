"""Commentary lookup over the extracted SWORD modules.

Two properties of the source data drive this module's shape.

Range keying.
    Matthew Henry attaches one note to a span of verses, and in the extracted
    data that note is repeated under every verse of the span. MHCC on John is
    28,718 rows but only 4,047 distinct notes. So a span is reconstructed as a
    contiguous run of verses carrying identical text, and reported once with its
    true verse range.

Gaps.
    Some spans are absent entirely - MHCC has no note anywhere in John 3:9-21.
    A commentator with no note covering the selection is omitted rather than
    substituted with a neighbouring note. Attributing Henry's note on John 3:1-8
    to a question about John 3:16 would be a citation the reader cannot trust,
    and the point of carrying three commentators is that the others cover the
    gap.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "commentary.db"


@dataclass(frozen=True)
class Note:
    module: str
    module_name: str
    # The verse range this note actually covers in the source, not the range the
    # caller asked about. These differ whenever a selection lands inside a span.
    span_start: int
    span_end: int
    text: str

    def span_label(self, book_display: str, chapter: int) -> str:
        if self.span_start == self.span_end:
            return f"{book_display} {chapter}:{self.span_start}"
        return f"{book_display} {chapter}:{self.span_start}-{self.span_end}"

    def cite(self, book_display: str, chapter: int) -> str:
        return f"{self.module_name} on {self.span_label(book_display, chapter)}"


class CommentaryStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        if not db_path.exists():
            raise FileNotFoundError(
                f"{db_path} missing - run scripts/extract_commentary.py first"
            )
        # Read-only. check_same_thread=False because FastAPI serves from a
        # threadpool; concurrent SQLite reads are safe.
        self._db = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
        )
        self._names: dict[str, str] = {
            module: name
            for module, name in self._db.execute("SELECT module, name FROM modules")
        }
        self._verify_book_keys()

    def _verify_book_keys(self) -> None:
        """Fail loudly if our book naming does not match the extracted data.

        The DB is keyed by SWORD's book names. Querying it with OSIS codes
        returns empty results rather than raising, so a naming mismatch is
        silent - indistinguishable from a commentator having no note.
        """
        from . import books

        present = {
            row[0] for row in self._db.execute("SELECT DISTINCT book FROM commentary")
        }
        missing = sorted({b.sword_name for b in books.BY_OSIS.values()} - present)
        if missing:
            raise RuntimeError(
                "commentary.db is missing book keys "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''} - "
                "books.Book.sword_name does not match the extracted data"
            )

    @property
    def modules(self) -> dict[str, str]:
        return dict(self._names)

    def close(self) -> None:
        self._db.close()

    def spans(self, module: str, book: str, chapter: int) -> list[Note]:
        """Every distinct note in a chapter, with its true verse range.

        Consecutive verses carrying identical text collapse into one span. A
        break in verse numbering also ends a span, so a gap in the source is
        never bridged.
        """
        rows = self._db.execute(
            "SELECT verse, text FROM commentary "
            "WHERE module=? AND book=? AND chapter=? ORDER BY verse",
            (module, book, chapter),
        ).fetchall()

        notes: list[Note] = []
        for verse, text in rows:
            previous = notes[-1] if notes else None
            contiguous = (
                previous is not None
                and previous.text == text
                and verse == previous.span_end + 1
            )
            if contiguous:
                notes[-1] = Note(
                    module=previous.module,
                    module_name=previous.module_name,
                    span_start=previous.span_start,
                    span_end=verse,
                    text=text,
                )
                continue
            notes.append(
                Note(
                    module=module,
                    module_name=self._names.get(module, module),
                    span_start=verse,
                    span_end=verse,
                    text=text,
                )
            )
        return notes

    def notes_for(
        self, module: str, book: str, chapter: int, verses: list[int]
    ) -> list[Note]:
        """Spans overlapping `verses`, each labelled with its own range.

        A span that overlaps the selection at all is returned whole, because the
        note was written about the span as a unit and truncating it would strip
        the reasoning. Returns empty if this module has no note covering the
        selection - the caller omits the module rather than substituting.
        """
        if not verses:
            return self.spans(module, book, chapter)
        low, high = min(verses), max(verses)
        return [
            note
            for note in self.spans(module, book, chapter)
            if note.span_start <= high and note.span_end >= low
        ]

    def coverage(self) -> list[tuple[str, int, int, int]]:
        """(module, rows, distinct_texts, books) - for the inspection CLI."""
        return self._db.execute(
            "SELECT module, COUNT(*), COUNT(DISTINCT text), COUNT(DISTINCT book) "
            "FROM commentary GROUP BY module ORDER BY module"
        ).fetchall()
