#!/usr/bin/env python3
"""Generate a Traditional Chinese phrase dictionary TSV file.

Downloads and processes the CEDICT (CC-CEDICT) open-source Chinese-English
dictionary to extract Traditional Chinese phrases with frequency estimates.

CEDICT is released under CC BY-SA 4.0 and contains ~120,000 entries with
both Traditional and Simplified forms.

Output format (TSV): phrase<TAB>frequency
"""

import re
import sys
import urllib.request
import gzip
import io
from pathlib import Path


CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "phrases.tsv"


def download_cedict() -> str:
    """Download and decompress the CEDICT dictionary."""
    print(f"Downloading CEDICT from {CEDICT_URL} ...")
    req = urllib.request.Request(CEDICT_URL, headers={"User-Agent": "stroke-input/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        compressed = resp.read()
    text = gzip.decompress(compressed).decode("utf-8")
    print(f"Downloaded {len(text):,} characters of dictionary data.")
    return text


# CEDICT line format: Traditional Simplified [pinyin] /english1/english2/
CEDICT_LINE_RE = re.compile(
    r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$"
)


def is_cjk_char(ch: str) -> bool:
    """Check if a character is in the CJK Unified Ideographs range."""
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF       # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF    # CJK Extension A
        or 0xF900 <= cp <= 0xFAFF    # CJK Compatibility Ideographs
        or 0x20000 <= cp <= 0x2A6DF  # CJK Extension B
    )


def is_all_cjk(text: str) -> bool:
    """Check if all characters in text are CJK ideographs."""
    return all(is_cjk_char(ch) for ch in text)


def estimate_frequency(phrase: str, definitions: str) -> float:
    """Estimate phrase frequency based on heuristics.

    Shorter, more common phrases get higher frequency scores.
    """
    base = 1.0

    # Shorter phrases are generally more common
    length = len(phrase)
    if length == 2:
        base = 0.8
    elif length == 3:
        base = 0.6
    elif length == 4:
        base = 0.5  # 四字成語 (4-char idioms) are very common
    elif length <= 6:
        base = 0.3
    else:
        base = 0.1

    # Boost for common definition patterns
    defs_lower = definitions.lower()
    common_markers = [
        "classifier", "measure word", "surname", "province",
        "city", "country", "Taiwan", "Hong Kong",
    ]
    for marker in common_markers:
        if marker in defs_lower:
            base *= 1.1
            break

    # Boost for Taiwan/HK specific terms
    if "tw" in defs_lower or "taiwan" in defs_lower or "hong kong" in defs_lower:
        base *= 1.2

    return round(min(base, 1.0), 4)


def parse_cedict(text: str) -> list[tuple[str, float]]:
    """Parse CEDICT text and extract Traditional Chinese phrases."""
    phrases: list[tuple[str, float]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = CEDICT_LINE_RE.match(line)
        if not m:
            continue

        traditional = m.group(1)
        definitions = m.group(4)

        # Only keep multi-character phrases (2+ chars) that are all CJK
        if len(traditional) < 2 or not is_all_cjk(traditional):
            continue

        if traditional in seen:
            continue
        seen.add(traditional)

        freq = estimate_frequency(traditional, definitions)
        phrases.append((traditional, freq))

    return phrases


def main() -> None:
    text = download_cedict()
    phrases = parse_cedict(text)

    # Sort by frequency descending, then by phrase
    phrases.sort(key=lambda p: (-p[1], p[0]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        fh.write("# Traditional Chinese Phrase Dictionary\n")
        fh.write("# Source: CC-CEDICT (CC BY-SA 4.0)\n")
        fh.write("# Format: phrase<TAB>frequency\n")
        for phrase, freq in phrases:
            fh.write(f"{phrase}\t{freq}\n")

    print(f"\nGenerated {len(phrases):,} phrases → {OUTPUT_FILE}")
    if len(phrases) < 50_000:
        print(f"WARNING: Only {len(phrases):,} phrases (target: 50,000+)")
        print("The CEDICT source should provide enough multi-char entries.")
    else:
        print("✓ Meets the 50,000+ phrase requirement.")


if __name__ == "__main__":
    main()
