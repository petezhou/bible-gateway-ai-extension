"""Passage reference parsing.

The only reference format entering the backend is OSIS, because that is what
BibleGateway exposes. Two shapes appear:

    "Josh.8"                      whole chapter
    "John.3.14-John.3.19"         verse range
    "John.3.16"                   single verse

Cross-chapter ranges ("John.3.30-John.4.2") are possible on BibleGateway but
out of scope for v0 - we reject them rather than silently mishandle them.
"""

from dataclasses import dataclass

from . import books


class InvalidReference(ValueError):
    pass


@dataclass(frozen=True)
class Reference:
    book: books.Book
    chapter: int
    # None means the whole chapter.
    verse_start: int | None = None
    verse_end: int | None = None

    @property
    def is_whole_chapter(self) -> bool:
        return self.verse_start is None

    @property
    def chapter_osis(self) -> str:
        return f"{self.book.osis}.{self.chapter}"

    def display(self) -> str:
        """Human-readable form, e.g. "John 3:14-19". Sent to the passage API."""
        if self.is_whole_chapter:
            return f"{self.book.display} {self.chapter}"
        if self.verse_end is None or self.verse_end == self.verse_start:
            return f"{self.book.display} {self.chapter}:{self.verse_start}"
        return f"{self.book.display} {self.chapter}:{self.verse_start}-{self.verse_end}"

    def chapter_display(self) -> str:
        return f"{self.book.display} {self.chapter}"

    def verses(self) -> list[int]:
        if self.is_whole_chapter:
            return []
        end = self.verse_end if self.verse_end is not None else self.verse_start
        return list(range(self.verse_start, end + 1))


def _parse_single(token: str) -> tuple[books.Book, int, int | None]:
    parts = token.split(".")
    if len(parts) == 2:
        book_code, chapter = parts
        verse = None
    elif len(parts) == 3:
        book_code, chapter, verse_str = parts
        verse = int(verse_str)
    else:
        raise InvalidReference(f"cannot parse OSIS token: {token!r}")
    return books.lookup(book_code), int(chapter), verse


def parse_osis(osis: str) -> Reference:
    osis = osis.strip()
    if not osis:
        raise InvalidReference("empty reference")

    if "-" not in osis:
        book, chapter, verse = _parse_single(osis)
        return Reference(book, chapter, verse, verse)

    start_token, _, end_token = osis.partition("-")
    book, chapter, verse_start = _parse_single(start_token)
    end_book, end_chapter, verse_end = _parse_single(end_token)

    if end_book.osis != book.osis or end_chapter != chapter:
        raise InvalidReference(
            f"cross-chapter ranges are not supported in v0: {osis!r}"
        )
    if verse_start is None or verse_end is None:
        raise InvalidReference(f"range endpoints need verses: {osis!r}")
    if verse_end < verse_start:
        raise InvalidReference(f"range runs backwards: {osis!r}")

    return Reference(book, chapter, verse_start, verse_end)


def parse_verse_classes(classes: list[str]) -> Reference:
    """Build a Reference from BibleGateway verse-span classes.

    The extension sends the raw class tails it collected, e.g.
    ["Josh-8-3", "Josh-8-4", "Josh-8-9"]. Numbered books hyphenate
    ("1-John-5-13"), so we parse from the right: the last two segments are
    always chapter and verse.
    """
    if not classes:
        raise InvalidReference("no verse classes supplied")

    parsed: list[tuple[str, int, int]] = []
    for raw in classes:
        segments = raw.strip().split("-")
        if len(segments) < 3:
            raise InvalidReference(f"cannot parse verse class: {raw!r}")
        *book_segments, chapter_str, verse_str = segments
        try:
            parsed.append(("-".join(book_segments), int(chapter_str), int(verse_str)))
        except ValueError as exc:
            raise InvalidReference(f"cannot parse verse class: {raw!r}") from exc

    book_codes = {p[0] for p in parsed}
    chapters = {p[1] for p in parsed}
    if len(book_codes) != 1 or len(chapters) != 1:
        raise InvalidReference(
            "selection spans multiple books or chapters, which v0 does not support"
        )

    book = books.lookup(book_codes.pop())
    verse_numbers = sorted(p[2] for p in parsed)
    return Reference(book, chapters.pop(), verse_numbers[0], verse_numbers[-1])
