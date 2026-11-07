"""Local API. Run with: uvicorn backend.app:app --reload --host 127.0.0.1."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Literal

import anthropic
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import prompts, refs
from .commentary import CommentaryStore
from .passages import CachingSource, PassageError, build_source
from .profiles import (
    READING_LEVELS,
    TRADITIONS,
    get_reading_level,
    get_tradition,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-sonnet-5-5"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    app.state.model = os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
    app.state.store = CommentaryStore()
    app.state.source = None
    app.state.claude = None
    try:
        for tradition in TRADITIONS.values():
            for document in tradition.documents:
                prompts.load_document(document)
        if os.getenv("ESV_API_KEY"):
            app.state.source = CachingSource(build_source())
        if os.getenv("ANTHROPIC_API_KEY"):
            app.state.claude = anthropic.AsyncAnthropic(timeout=90.0, max_retries=1)
        yield
    finally:
        if app.state.claude is not None:
            await app.state.claude.close()
        app.state.store.close()


app = FastAPI(title="BibleGateway AI local API", lifespan=lifespan)


class StudyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reference: str = Field(min_length=1, max_length=100, examples=["John.3.16"])
    tradition: str | None = None
    reading_level: str | None = None

    @field_validator("reference")
    @classmethod
    def valid_reference(cls, value: str) -> str:
        ref = refs.parse_osis(value)
        if not 1 <= ref.chapter <= 150:
            raise ValueError("chapter must be between 1 and 150")
        if ref.verse_start is not None and not (
            1 <= ref.verse_start <= (ref.verse_end or ref.verse_start) <= 176
        ):
            raise ValueError("verses must be between 1 and 176")
        return value

    @field_validator("tradition", "reading_level")
    @classmethod
    def valid_profile(cls, value: str | None, info) -> str | None:
        registry = TRADITIONS if info.field_name == "tradition" else READING_LEVELS
        if value is not None and value not in registry:
            raise ValueError(f"choose from: {', '.join(registry)}")
        return value


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(StudyRequest):
    question: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)

    @field_validator("history")
    @classmethod
    def complete_turns(cls, value: list[HistoryMessage]) -> list[HistoryMessage]:
        if len(value) % 2 or any(
            message.role != ("user" if index % 2 == 0 else "assistant")
            for index, message in enumerate(value)
        ):
            raise ValueError("history must contain alternating user/assistant pairs")
        return value


class StudyResponse(BaseModel):
    reference: str
    translation: str
    text: str
    sources: list[str]
    omitted_modules: list[str]
    model: str
    prompt_version: str
    usage: dict[str, int]


@app.get("/health")
async def health(request: Request):
    state = request.app.state
    missing = []
    if state.source is None:
        missing.append("ESV_API_KEY")
    if state.claude is None:
        missing.append("ANTHROPIC_API_KEY")
    return {
        "status": "ready" if not missing else "needs_configuration",
        "missing": missing,
        "model": state.model,
        "commentary_modules": state.store.modules,
        "prompt_version": prompts.PROMPT_VERSION,
    }


async def generate(body: StudyRequest, request: Request) -> StudyResponse:
    state = request.app.state
    for name, resource in (
        ("ESV_API_KEY", state.source), ("ANTHROPIC_API_KEY", state.claude)
    ):
        if resource is None:
            raise HTTPException(503, f"Set {name} in .env and restart the server")

    ref = refs.parse_osis(body.reference)
    tradition = get_tradition(body.tradition)
    level = get_reading_level(body.reading_level)
    try:
        chapter = await state.source.fetch(refs.parse_osis(ref.chapter_osis))
    except (PassageError, httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "Unable to fetch chapter text from ESV; check the key and reference") from exc

    material = prompts.gather(
        state.store, tradition, ref, chapter,
        None if ref.is_whole_chapter else ref,
    )
    messages = []
    if isinstance(body, ChatRequest):
        messages = [message.model_dump() for message in body.history]
        user = prompts.chat_user_message(ref, body.question, level, None)
    else:
        user = prompts.summary_user_message(ref, level)
    messages.append({"role": "user", "content": user})

    try:
        result = await state.claude.messages.create(
            model=state.model,
            max_tokens=2048,
            system=prompts.system_blocks(tradition, material, ref),
            messages=messages,
        )
    except anthropic.AuthenticationError as exc:
        raise HTTPException(502, "Anthropic rejected the API key; check ANTHROPIC_API_KEY") from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(429, "Anthropic rate limit reached; try again shortly") from exc
    except anthropic.APITimeoutError as exc:
        raise HTTPException(504, "Anthropic request timed out; try again") from exc
    except anthropic.APIError as exc:
        raise HTTPException(502, "Anthropic request failed; check model access and API credits") from exc

    text = "\n\n".join(block.text for block in result.content if block.type == "text")
    if not text.strip():
        raise HTTPException(502, "Anthropic returned no answer")
    if result.stop_reason == "max_tokens":
        raise HTTPException(502, "Anthropic answer exceeded the output limit; try a narrower question")
    usage = result.usage
    return StudyResponse(
        reference=ref.display(),
        translation=state.source.translation,
        text=text,
        sources=[
            note.cite(ref.book.display, ref.chapter)
            for notes in material.notes.values() for note in notes
        ] + list(tradition.documents),
        omitted_modules=material.omitted,
        model=state.model,
        prompt_version=prompts.PROMPT_VERSION,
        usage={
            name: getattr(usage, name, None) or 0
            for name in (
                "input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens",
            )
        },
    )


@app.post("/summary", response_model=StudyResponse)
async def summary(body: StudyRequest, request: Request):
    return await generate(body, request)


@app.post("/chat", response_model=StudyResponse)
async def chat(body: ChatRequest, request: Request):
    return await generate(body, request)
