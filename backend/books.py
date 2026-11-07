"""Canonical book table.

BibleGateway uses OSIS-style book codes in both places we read from:
  - the passage container's `data-osis` attribute, e.g. "John.3.14-John.3.19"
  - each verse span's class, e.g. "text Josh-8-1"

`display` is what we send to the passage API, which wants human-readable
references ("1 John 5:13", not "1John.5.13").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    osis: str
    display: str
    testament: str  # "OT" or "NT"

    @property
    def sword_name(self) -> str:
        """Book key used by the SWORD modules, and therefore by commentary.db.

        SWORD numbers books with Roman numerals ("I Samuel", not "1 Samuel") and
        calls the last book "Revelation of John". Everything else matches
        `display` exactly.
        """
        if self.osis == "Rev":
            return "Revelation of John"
        for arabic, roman in (("1 ", "I "), ("2 ", "II "), ("3 ", "III ")):
            if self.display.startswith(arabic):
                return roman + self.display[len(arabic):]
        return self.display


_BOOKS: tuple[Book, ...] = (
    Book("Gen", "Genesis", "OT"),
    Book("Exod", "Exodus", "OT"),
    Book("Lev", "Leviticus", "OT"),
    Book("Num", "Numbers", "OT"),
    Book("Deut", "Deuteronomy", "OT"),
    Book("Josh", "Joshua", "OT"),
    Book("Judg", "Judges", "OT"),
    Book("Ruth", "Ruth", "OT"),
    Book("1Sam", "1 Samuel", "OT"),
    Book("2Sam", "2 Samuel", "OT"),
    Book("1Kgs", "1 Kings", "OT"),
    Book("2Kgs", "2 Kings", "OT"),
    Book("1Chr", "1 Chronicles", "OT"),
    Book("2Chr", "2 Chronicles", "OT"),
    Book("Ezra", "Ezra", "OT"),
    Book("Neh", "Nehemiah", "OT"),
    Book("Esth", "Esther", "OT"),
    Book("Job", "Job", "OT"),
    Book("Ps", "Psalms", "OT"),
    Book("Prov", "Proverbs", "OT"),
    Book("Eccl", "Ecclesiastes", "OT"),
    Book("Song", "Song of Solomon", "OT"),
    Book("Isa", "Isaiah", "OT"),
    Book("Jer", "Jeremiah", "OT"),
    Book("Lam", "Lamentations", "OT"),
    Book("Ezek", "Ezekiel", "OT"),
    Book("Dan", "Daniel", "OT"),
    Book("Hos", "Hosea", "OT"),
    Book("Joel", "Joel", "OT"),
    Book("Amos", "Amos", "OT"),
    Book("Obad", "Obadiah", "OT"),
    Book("Jonah", "Jonah", "OT"),
    Book("Mic", "Micah", "OT"),
    Book("Nah", "Nahum", "OT"),
    Book("Hab", "Habakkuk", "OT"),
    Book("Zeph", "Zephaniah", "OT"),
    Book("Hag", "Haggai", "OT"),
    Book("Zech", "Zechariah", "OT"),
    Book("Mal", "Malachi", "OT"),
    Book("Matt", "Matthew", "NT"),
    Book("Mark", "Mark", "NT"),
    Book("Luke", "Luke", "NT"),
    Book("John", "John", "NT"),
    Book("Acts", "Acts", "NT"),
    Book("Rom", "Romans", "NT"),
    Book("1Cor", "1 Corinthians", "NT"),
    Book("2Cor", "2 Corinthians", "NT"),
    Book("Gal", "Galatians", "NT"),
    Book("Eph", "Ephesians", "NT"),
    Book("Phil", "Philippians", "NT"),
    Book("Col", "Colossians", "NT"),
    Book("1Thess", "1 Thessalonians", "NT"),
    Book("2Thess", "2 Thessalonians", "NT"),
    Book("1Tim", "1 Timothy", "NT"),
    Book("2Tim", "2 Timothy", "NT"),
    Book("Titus", "Titus", "NT"),
    Book("Phlm", "Philemon", "NT"),
    Book("Heb", "Hebrews", "NT"),
    Book("Jas", "James", "NT"),
    Book("1Pet", "1 Peter", "NT"),
    Book("2Pet", "2 Peter", "NT"),
    Book("1John", "1 John", "NT"),
    Book("2John", "2 John", "NT"),
    Book("3John", "3 John", "NT"),
    Book("Jude", "Jude", "NT"),
    Book("Rev", "Revelation", "NT"),
)

BY_OSIS: dict[str, Book] = {b.osis: b for b in _BOOKS}

# BibleGateway's verse-span classes hyphenate numbered books ("1-John-5-13"),
# so we also index the hyphenated form.
BY_CLASS_PREFIX: dict[str, Book] = {b.osis.replace("1", "1-").replace("2", "2-").replace("3", "3-"): b for b in _BOOKS if b.osis[0].isdigit()}
BY_CLASS_PREFIX.update({b.osis: b for b in _BOOKS if not b.osis[0].isdigit()})


class UnknownBook(ValueError):
    pass


def lookup(osis_code: str) -> Book:
    book = BY_OSIS.get(osis_code) or BY_CLASS_PREFIX.get(osis_code)
    if book is None:
        raise UnknownBook(f"unrecognized book code: {osis_code!r}")
    return book
