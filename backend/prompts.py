"""Prompt assembly.

Layered so the stable prefix can be cached. Block order matters:

    system[0]  base rules + tradition + catechism    identical on every request
    system[1]  chapter text + commentary excerpts    identical for a chapter and
                                                     selection, so every turn of
                                                     a conversation reuses it
    messages   selection, question, history          varies per turn

Everything the model is given as reference is attributed, and every commentary
excerpt is labelled with the verse range it actually covers - which is often
wider than the selection, because these commentators write about spans. The
model's job is synthesis and answering; it is not the source of the readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .commentary import CommentaryStore, Note
from .passages import Passage
from .profiles import ReadingLevel, Tradition
from .refs import Reference

DOCUMENTS = Path(__file__).resolve().parent / "documents"

# Bump when the prompt changes. Surfaces in logs and, later, in cache keys.
PROMPT_VERSION = "v1"

BASE_RULES = """\
You help a reader study the Bible on the passage they are currently viewing.

You are given reference material: the text of the chapter, and excerpts from
historic commentaries. Treat that material as your source. Your work is
synthesis - drawing the reference material together, and answering what was
actually asked.

Attribution:
- When a reading comes from a commentator, name them and give the verse range
  their note covers, e.g. "Jamieson-Fausset-Brown on John 3:14-16".
- When a doctrinal claim is grounded in the catechism, cite the question number,
  e.g. "WSC Q20".
- If you say something the reference material does not support, say so plainly
  in the same sentence. Do not present it in the same voice as a sourced claim.
- Not every commentator will have a note on the selected verses. Work with what
  is provided and do not speculate about what the others would have said.

Constraints:
- Do not restate or paraphrase the passage back to the reader. They are looking
  at it.
- Where the commentators disagree, or the passage is genuinely disputed, say so
  rather than silently choosing a reading.
- Do not moralise or add application the reader did not ask for.
- If the reader discloses distress, harm, or crisis, do not counsel them.
  Acknowledge it briefly and encourage them to speak with their pastor or
  another person who can help.\
"""

SUMMARY_TASK = """\
Write a short orientation to this passage, in markdown, using exactly these
headings:

**Where you are** - one or two sentences locating this passage in the book.
**What's happening** - the movement of the passage: its structure and turns.
**Why it matters** - the theological weight of it, grounded in the sources.
**Worth noticing** - one to three concrete observations a careful reader might
miss.

Close with a single line listing which sources informed the summary, e.g.
`_Sources: Jamieson-Fausset-Brown, Geneva Bible Notes, WSC Q20_`

Target {low}-{high} words. Do not exceed it. Keep citations light here - cite
inline only for doctrinal claims or where a reading is distinctively one
commentator's.\
"""

CHAT_TASK = """\
Answer the reader's question about the verses they selected. Draw on the
reference material and cite it as instructed. Be direct: answer what was asked
rather than surveying the passage. If the question cannot be answered from the
reference material, say what is missing.\
"""


@lru_cache(maxsize=8)
def load_document(filename: str) -> str:
    path = DOCUMENTS / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing - run scripts/extract_catechism.py first"
        )
    return path.read_text().strip()


@dataclass(frozen=True)
class ReferenceMaterial:
    """What was actually gathered, so callers can report or log it."""

    chapter: Passage
    notes: dict[str, list[Note]]      # module -> spans, only modules with notes
    omitted: list[str]                # modules with no note covering selection

    @property
    def chars(self) -> int:
        return len(self.chapter.text) + sum(
            len(n.text) for notes in self.notes.values() for n in notes
        )


def gather(
    store: CommentaryStore,
    tradition: Tradition,
    ref: Reference,
    chapter: Passage,
    selection: Reference | None,
) -> ReferenceMaterial:
    """Collect commentary for the selection, or for the chapter if none."""
    verses = selection.verses() if selection else []
    notes: dict[str, list[Note]] = {}
    omitted: list[str] = []
    for module in tradition.commentary_modules:
        found = store.notes_for(module, ref.book.sword_name, ref.chapter, verses)
        if found:
            notes[module] = found
        else:
            omitted.append(module)
    return ReferenceMaterial(chapter=chapter, notes=notes, omitted=omitted)


def _render_commentary(material: ReferenceMaterial, ref: Reference) -> str:
    if not material.notes:
        return (
            "No commentary excerpts are available for these verses in the "
            "sources provided."
        )
    sections: list[str] = []
    for module, notes in material.notes.items():
        name = notes[0].module_name
        blocks = [
            f"### {name} on {note.span_label(ref.book.display, ref.chapter)}\n"
            f"{note.text}"
            for note in notes
        ]
        sections.append("\n\n".join(blocks))
    return "\n\n".join(sections)


def system_blocks(
    tradition: Tradition,
    material: ReferenceMaterial,
    ref: Reference,
    cache: bool = True,
) -> list[dict]:
    """Two blocks, each independently cacheable.

    Block 0 never changes, so it is written once and read by every request -
    including across both endpoints, since toggling `thinking` invalidates only
    the messages tier. Block 1 is fixed for a chapter and selection, so every
    turn of a conversation reuses it.
    """
    documents = "\n\n".join(load_document(name) for name in tradition.documents)

    stable = (
        f"{BASE_RULES}\n\n"
        f"## Interpretive tradition\n\n{tradition.instruction}\n\n"
        f"The following confessional document is provided as general steering "
        f"for that tradition. Use it to frame doctrine; do not quote from it "
        f"mechanically.\n\n{documents}"
    )

    chapter_label = ref.chapter_display()
    reference_material = (
        f"# Reference material\n\n"
        f"## {chapter_label} ({material.chapter.reference})\n\n"
        f"The full chapter, for context.\n\n{material.chapter.text}\n\n"
        f"## Commentary excerpts\n\n"
        f"Each excerpt is labelled with the verse range the commentator wrote "
        f"about, which may be wider than the verses in question.\n\n"
        f"{_render_commentary(material, ref)}"
    )

    blocks = [{"type": "text", "text": stable}, {"type": "text", "text": reference_material}]
    if cache:
        # 1h on the block that never changes; default 5m on chapter material,
        # which only needs to outlive one conversation.
        blocks[0]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
        blocks[1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def summary_user_message(ref: Reference, level: ReadingLevel) -> str:
    scope = (
        f"the whole of {ref.chapter_display()}"
        if ref.is_whole_chapter
        else f"{ref.display()}, within the context of {ref.chapter_display()}"
    )
    low, high = level.summary_words
    return (
        f"The reader is viewing {ref.display()}.\n\n"
        f"Write about {scope}.\n\n"
        f"{level.instruction}\n\n"
        f"{SUMMARY_TASK.format(low=low, high=high)}"
    )


def chat_user_message(
    selection: Reference, question: str, level: ReadingLevel, selected_text: str | None
) -> str:
    parts = [
        f"The reader has selected {selection.display()} and asked a question "
        f"about it.",
        f"## Selected verses\n\n{selection.display()}",
    ]
    if selected_text:
        parts[-1] += f"\n\n{selected_text}"
    parts += [level.instruction, CHAT_TASK, f"## Question\n\n{question}"]
    return "\n\n".join(parts)
