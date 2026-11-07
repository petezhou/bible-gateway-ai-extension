"""Tradition and reading-level profiles.

Everything tradition-specific lives here rather than inline in prompt assembly,
so adding a tradition is a registry entry plus a document file. The frontend
does not expose these yet; requests fall back to the defaults below.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tradition:
    id: str
    label: str
    # Prepended to the system prompt. Describes the interpretive stance.
    instruction: str
    # Filenames under backend/documents/, loaded in order.
    documents: tuple[str, ...]
    # Commentary modules to draw on, most-trusted first. Must exist in the
    # commentary DB's `modules` table.
    commentary_modules: tuple[str, ...]


@dataclass(frozen=True)
class ReadingLevel:
    id: str
    label: str
    instruction: str
    # Target length of the summary card, in words.
    summary_words: tuple[int, int]


TRADITIONS: dict[str, Tradition] = {
    "westminster-pca": Tradition(
        id="westminster-pca",
        label="Reformed / Westminster (PCA)",
        # Deliberately minimal. The interpretive steering comes from the
        # commentators and the catechism supplied below, not from instructing
        # the model in a method. Telling it to read redemptive-historically
        # produces that framing even where the sources do not support it, which
        # is precisely the unauditable output we are trying to avoid.
        instruction=(
            "Read and explain Scripture from a confessionally Reformed "
            "perspective, as expressed in the Westminster Standards."
        ),
        documents=(
            "westminster-shorter-catechism.md",
            # "westminster-confession.md",  # add once sourced
        ),
        commentary_modules=("MHCC", "JFB", "Geneva"),
    ),
}

READING_LEVELS: dict[str, ReadingLevel] = {
    "lay-devotional": ReadingLevel(
        id="lay-devotional",
        label="Lay / devotional",
        instruction=(
            "Write for an ordinary churchgoer with no formal theological "
            "training. Use plain language. Do not use untranslated Hebrew or "
            "Greek. If a technical term is unavoidable, define it in the same "
            "sentence."
        ),
        summary_words=(250, 350),
    ),
    "pastor": ReadingLevel(
        id="pastor",
        label="Pastor / sermon prep",
        instruction=(
            "Write for a seminary-trained pastor preparing to preach. Assume "
            "theological vocabulary. Give more attention to the structure of "
            "the argument and to interpretive tensions that bear on preaching."
        ),
        summary_words=(350, 500),
    ),
    "scholar": ReadingLevel(
        id="scholar",
        label="Scholar",
        instruction=(
            "Write for a reader with original-language competence. Note "
            "textual and lexical issues where the commentators raise them. "
            "Density is acceptable."
        ),
        summary_words=(400, 600),
    ),
}

DEFAULT_TRADITION = "westminster-pca"
DEFAULT_READING_LEVEL = "lay-devotional"


def get_tradition(tradition_id: str | None) -> Tradition:
    return TRADITIONS[tradition_id or DEFAULT_TRADITION]


def get_reading_level(level_id: str | None) -> ReadingLevel:
    return READING_LEVELS[level_id or DEFAULT_READING_LEVEL]
