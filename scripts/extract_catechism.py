#!/usr/bin/env python3
"""Extract the Westminster Shorter Catechism to markdown.

The catechism is a 1647 document, public domain. Output is gitignored - a local
build asset, not something this repo redistributes.

Expects the edition where each question and answer sits on a single line:

    Q. 1. What is the chief end of man?A. Man's chief end is ...

Proof texts live in a separate section and are not extracted. The proofs roughly
quadruple the token count, and for steering the model the question-and-answer
text is what matters. Superscript proof markers appear in the extracted text as
bare digits attached to words ("God,1") and are stripped.

    .venv/bin/python scripts/extract_catechism.py backend/documents/Shorter_Catechism.pdf
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "backend" / "documents" / "westminster-shorter-catechism.md"

EXPECTED_QUESTIONS = 107

# Question markers are located in the joined document stream rather than per
# line. Line boundaries are unreliable: pypdf sometimes merges two questions
# onto one line (Q23/Q24) and splits page numbers onto their own.
Q_MARKER = re.compile(r"Q\.\s*(\d{1,3})\.\s*")

# Splits a question chunk into question text and answer text.
ANSWER_SPLIT = re.compile(r"\s*A\.\s*")

# The catechism's own answers never cite scripture inline - proofs are carried as
# footnote numbers and collected in a separate section. So the first inline
# reference marks where an answer ends and proof material begins. This matters
# for the final question, whose chunk would otherwise run to end of document and
# absorb the entire proofs section.
PROOF_BOUNDARY = re.compile(r"\b(?:[1-3]\s)?[A-Z][a-z]{2,}\.?\s*\d+:\d+")

# Page furniture to drop before joining.
RUNNING_HEADER = re.compile(r"^WESTMINSTER SHORTER CATECHISM", re.I)
PAGE_NUMBER = re.compile(r"^\d{1,3}$")

# Footnote markers: digits fused to the preceding word, e.g. "God,1" or "Spirit,7".
# Requires no space before the digits and a boundary after, so ordinary numerals
# separated by spaces are left alone.
FOOTNOTE_MARKER = re.compile(r"(?<=[A-Za-z,;:.\)])(\d{1,3})(?=[\s,;:.\)]|$)")


def read_stream(path: Path) -> str:
    """Whole document as one whitespace-normalised stream, minus page furniture."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    kept: list[str] = []
    dropped = 0
    for page in reader.pages:
        for line in (page.extract_text() or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if PAGE_NUMBER.match(stripped) or RUNNING_HEADER.match(stripped):
                dropped += 1
                continue
            kept.append(stripped)
    print(f"  {len(reader.pages)} pages, {len(kept)} lines kept, {dropped} furniture lines dropped")
    return " ".join(kept)


def clean(text: str) -> str:
    text = FOOTNOTE_MARKER.sub("", text)
    text = text.replace("­", "")        # soft hyphen
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    print(f"reading {args.pdf}")
    stream = read_stream(args.pdf)

    markers = list(Q_MARKER.finditer(stream))
    print(f"  {len(markers)} question markers found in stream")

    found: dict[int, tuple[str, str]] = {}
    malformed: list[int] = []
    for index, marker in enumerate(markers):
        number = int(marker.group(1))
        end = markers[index + 1].start() if index + 1 < len(markers) else len(stream)
        chunk = stream[marker.end():end]

        boundary = PROOF_BOUNDARY.search(chunk)
        if boundary:
            chunk = chunk[: boundary.start()]

        parts = ANSWER_SPLIT.split(chunk, maxsplit=1)
        if len(parts) != 2:
            malformed.append(number)
            continue
        # The proofs section repeats questions; keep the first occurrence, which
        # is the catechism proper.
        found.setdefault(number, (clean(parts[0]), clean(parts[1])))

    if not found:
        print("  ERROR: no questions parsed - check Q_MARKER against the layout")
        return 1
    if malformed:
        print(f"  WARNING: no 'A.' found for Q{malformed[:10]}")

    body = "\n\n".join(
        f"**Q{n}.** {found[n][0]}\n\n**A.** {found[n][1]}" for n in sorted(found)
    )
    header = (
        "# The Westminster Shorter Catechism (1647)\n\n"
        "Public domain. Supplied as confessional context for general steering.\n"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(f"{header}\n{body}\n")

    numbers = sorted(found)
    missing = sorted(set(range(1, EXPECTED_QUESTIONS + 1)) - set(numbers))
    short = [n for n in numbers if len(found[n][1]) < 15]

    print(f"  wrote {args.out}")
    print(f"  {len(body)} chars, ~{len(body) // 4} tokens (rough)")
    print(f"  {len(found)} questions, Q{min(numbers)}-Q{max(numbers)}")
    if missing:
        print(f"  WARNING: missing {len(missing)} questions: {missing[:20]}")
    if max(numbers) > EXPECTED_QUESTIONS:
        print(f"  WARNING: highest is Q{max(numbers)}, expected {EXPECTED_QUESTIONS}")
    if short:
        print(f"  WARNING: suspiciously short answers at {short[:10]}")
    if not missing and max(numbers) == EXPECTED_QUESTIONS and not short:
        print("  OK: all 107 questions present, no truncated answers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
