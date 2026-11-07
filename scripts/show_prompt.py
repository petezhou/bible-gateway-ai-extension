#!/usr/bin/env python3
"""Assemble and print a prompt without calling the model.

Lets you read exactly what would be sent, and get real token counts, before
spending anything on generation. Token counting via the API is free.

    .venv/bin/python scripts/show_prompt.py John.3.14-John.3.19
    .venv/bin/python scripts/show_prompt.py Josh.8 --full
    .venv/bin/python scripts/show_prompt.py John.3.16 -q "Who is 'the world' here?"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from backend import prompts, refs  # noqa: E402
from backend.commentary import CommentaryStore  # noqa: E402
from backend.passages import CachingSource, build_source  # noqa: E402
from backend.profiles import get_reading_level, get_tradition  # noqa: E402

MODEL = "claude-sonnet-5"


def count_tokens(system: list[dict], user: str) -> int | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    client = anthropic.Anthropic()
    result = client.messages.count_tokens(
        model=MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return result.input_tokens


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("osis", help="e.g. John.3.14-John.3.19 or Josh.8")
    parser.add_argument("-q", "--question", help="render the chat prompt instead")
    parser.add_argument("--level", default=None)
    parser.add_argument("--tradition", default=None)
    parser.add_argument("--full", action="store_true", help="print the whole prompt")
    args = parser.parse_args()

    ref = refs.parse_osis(args.osis)
    tradition = get_tradition(args.tradition)
    level = get_reading_level(args.level)
    store = CommentaryStore()
    source = CachingSource(build_source())

    chapter_ref = refs.parse_osis(ref.chapter_osis)
    chapter = await source.fetch(chapter_ref)
    selection = None if ref.is_whole_chapter else ref

    material = prompts.gather(store, tradition, ref, chapter, selection)
    system = prompts.system_blocks(tradition, material, ref)
    if args.question:
        user = prompts.chat_user_message(selection or ref, args.question, level, None)
    else:
        user = prompts.summary_user_message(ref, level)

    print(f"prompt_version : {prompts.PROMPT_VERSION}")
    print(f"reference      : {ref.display()}  (chapter {ref.chapter_display()})")
    print(f"tradition      : {tradition.label}")
    print(f"reading level  : {level.label}")
    print(f"translation    : {source.translation}")
    print(f"mode           : {'chat' if args.question else 'summary'}")
    print()
    print("commentary gathered:")
    for module, notes in material.notes.items():
        spans = ", ".join(
            n.span_label(ref.book.display, ref.chapter) for n in notes
        )
        chars = sum(len(n.text) for n in notes)
        print(f"  {module:8s} {len(notes)} span(s)  {chars:6d} chars  [{spans}]")
    for module in material.omitted:
        print(f"  {module:8s} omitted - no note covering the selection")
    print()

    print("block sizes:")
    for index, block in enumerate(system):
        ttl = block.get("cache_control", {}).get("ttl", "5m" if "cache_control" in block else "-")
        print(
            f"  system[{index}] {len(block['text']):7d} chars  "
            f"~{len(block['text']) // 4:6d} tok (est)  cache={ttl}"
        )
    print(f"  user      {len(user):7d} chars  ~{len(user) // 4:6d} tok (est)")

    total = count_tokens(system, user)
    if total is None:
        print("\n(set ANTHROPIC_API_KEY for exact token counts)")
    else:
        est = sum(len(b["text"]) for b in system) // 4 + len(user) // 4
        print(f"\nexact input tokens: {total}   (rough estimate was {est})")
        cached = 0.20 / 1e6 * total          # Sonnet 5 intro cache-read rate
        uncached = 2.00 / 1e6 * total        # Sonnet 5 intro input rate
        print(f"input cost: ${uncached:.4f} uncached / ${cached:.4f} cached")

    if args.full:
        print("\n" + "=" * 78)
        for index, block in enumerate(system):
            print(f"\n----- system[{index}] -----\n")
            print(block["text"])
        print("\n----- user -----\n")
        print(user)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
