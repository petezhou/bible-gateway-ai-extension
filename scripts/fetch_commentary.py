#!/usr/bin/env python3
"""Download public-domain SWORD commentary modules into vendor/sword/.

One-time build step. Output is gitignored: these are local build assets, not
something this repo redistributes.

Every module below is pre-1929 and distributed by CrossWire as public domain,
but the extractor reads each module's declared DistributionLicense and records
it rather than trusting this comment.

    python3 scripts/fetch_commentary.py
"""

from __future__ import annotations

import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

MIRROR = "https://crosswire.org/ftpmirror/pub/sword/packages/rawzip/"

# (module, why it is here)
MODULES: list[tuple[str, str]] = [
    ("MHCC", "Matthew Henry's Concise Commentary - whole Bible, Puritan"),
    ("JFB", "Jamieson-Fausset-Brown - whole Bible, Scottish Presbyterian"),
    ("Geneva", "Geneva Bible translation notes - Reformed, 1560/1599"),
    # KJV is not a commentary. It is the versification reference the commentary
    # modules declare, and pysword can read it (zText), so the extractor uses it
    # to enumerate exact verse counts per chapter.
    ("KJV", "KJV - versification reference for the extractor"),
]

VENDOR = Path(__file__).resolve().parent.parent / "vendor" / "sword"


def fetch(module: str) -> None:
    url = f"{MIRROR}{module}.zip"
    print(f"  {module}: downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "bible-study-poc/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    print(f"  {module}: {len(payload) / 1024:.0f} KiB, unpacking")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(VENDOR)


def main() -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    print(f"SWORD_PATH will be {VENDOR}")
    for module, why in MODULES:
        print(f"{module} - {why}")
        try:
            fetch(module)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  {module}: FAILED - {exc}", file=sys.stderr)
            continue
        # Be polite to a volunteer-run mirror.
        time.sleep(1.0)

    installed = sorted(p.stem for p in (VENDOR / "mods.d").glob("*.conf"))
    print(f"\ninstalled modules: {', '.join(installed) or '(none)'}")
    print(f"\nverify with:  SWORD_PATH={VENDOR} diatheke -b MHCC -k John 3:16")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
