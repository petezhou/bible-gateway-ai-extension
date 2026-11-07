"""Passage text retrieval.

The extension never sends page text - only references. The backend resolves the
text itself, so the passage source is swappable without touching anything else.

Chapter text is memoised for the lifetime of the process. Chat resolves the
containing chapter on every turn, and the free ESV tier has daily verse caps
that a single debugging session can otherwise burn through.
"""

import os
from typing import Protocol

import httpx

from .refs import Reference


class PassageError(RuntimeError):
    pass


class Passage:
    def __init__(self, reference: str, text: str) -> None:
        self.reference = reference
        self.text = text

    def __repr__(self) -> str:
        return f"Passage({self.reference!r}, {len(self.text)} chars)"


class PassageSource(Protocol):
    name: str
    translation: str

    async def fetch(self, ref: Reference) -> Passage: ...


class ESVSource:
    """api.esv.org - free for non-commercial use, requires a key.

    Attribution and the copyright notice must be displayed with every passage;
    the extension renders `Passage.reference` and a fixed notice alongside.
    """

    name = "esv"
    translation = "ESV"
    _ENDPOINT = "https://api.esv.org/v3/passage/text/"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise PassageError("ESV_API_KEY is not set")
        self._api_key = api_key

    async def fetch(self, ref: Reference) -> Passage:
        params = {
            "q": ref.display(),
            "include-headings": "true",
            "include-footnotes": "false",
            "include-verse-numbers": "true",
            "include-short-copyright": "false",
            "include-passage-references": "false",
            "indent-poetry": "false",
        }
        headers = {"Authorization": f"Token {self._api_key}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(self._ENDPOINT, params=params, headers=headers)
        if response.status_code != 200:
            raise PassageError(
                f"ESV API returned {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        passages = payload.get("passages") or []
        if not passages:
            raise PassageError(f"ESV API returned no text for {ref.display()!r}")
        return Passage(payload.get("canonical") or ref.display(), passages[0].strip())


def build_source() -> PassageSource:
    return ESVSource(os.environ.get("ESV_API_KEY", ""))


class CachingSource:
    """Process-lifetime memoisation. Dies on restart; no persistence."""

    def __init__(self, inner: PassageSource) -> None:
        self._inner = inner
        self._cache: dict[str, Passage] = {}
        self.name = inner.name
        self.translation = inner.translation

    async def fetch(self, ref: Reference) -> Passage:
        key = f"{self.name}:{ref.display()}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        passage = await self._inner.fetch(ref)
        self._cache[key] = passage
        return passage

    @property
    def stats(self) -> dict[str, int]:
        return {"entries": len(self._cache)}
