#!/usr/bin/env python3
"""Build a merged Hong Kong Chinese character frequency table.

Downloads and combines three publicly available sources:

1. Apple Daily frequency list (chaaklau/appledaily-frequency)
   - Source: word-freq.tsv
   - License: CC BY 4.0
   - We aggregate word frequencies into per-character counts.

2. Cifu (gwinterstein/Cifu)
   - Source: Lexicon/Cifu-v1.txt
   - Academic lexicon; cite Lai & Winterstein (2020) if used in research.
   - We use the "Written" per-million frequency column for single-character entries.

3. CUHK Lexis Chinese Character Frequency Statistics
   - Source: humanum.arts.cuhk.edu.hk/Lexis/chifreq/
   - We parse the 香港 60/90 年代 HTML tables.

Output: ``data/character_frequency_hk.json`` maps each character to a
normalized score in [0, 1]. The score is a weighted geometric mean of the
per-source ranks, which keeps the ordering robust even when absolute counts
vary by orders of magnitude.
"""

from __future__ import annotations

import json
import math
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EXTERNAL_DIR = DATA_DIR / "external_freq"
OUT_FILE = DATA_DIR / "character_frequency_hk.json"

SOURCES: dict[str, dict[str, Any]] = {
    "appledaily": {
        "url": "https://raw.githubusercontent.com/chaaklau/appledaily-frequency/master/release/word-freq.tsv",
        "file": EXTERNAL_DIR / "appledaily_word_freq.tsv",
        "weight": 0.5,
    },
    "cifu": {
        "url": "https://raw.githubusercontent.com/gwinterstein/Cifu/master/Lexicon/Cifu-v1.txt",
        "file": EXTERNAL_DIR / "cifu_v1.txt",
        "weight": 0.3,
    },
    "cuhk": {
        "url": "https://humanum.arts.cuhk.edu.hk/Lexis/chifreq/chifreq.php?year=60&place=hk&sort=no&method=1",
        "file": EXTERNAL_DIR / "cuhk_lexis_hk60.html",
        "weight": 0.2,
    },
}


class _TableParser(HTMLParser):
    """Minimal HTML table parser for CUHK Lexis."""

    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.in_tr = False
        self.current: list[str] = []
        self.rows: list[list[str]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.in_tr = True
            self.current = []
        elif tag == "td":
            self.in_td = True
            self.text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.in_td = False
            self.current.append("".join(self.text).strip())
        elif tag == "tr":
            self.in_tr = False
            if self.current and any(self.current):
                self.rows.append(self.current)

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.text.append(data)


def _download(name: str, url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  {name}: using cached {dest}")
        return
    print(f"  {name}: downloading from {url}")
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "stroke-input/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print(f"  {name}: saved {dest} ({dest.stat().st_size:,} bytes)")


def _parse_appledaily_word_freq(path: Path) -> dict[str, float]:
    """Return per-character counts aggregated from word frequencies."""
    char_counts: dict[str, int] = {}
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        word, count_str = parts[0], parts[1]
        try:
            count = int(count_str)
        except ValueError:
            continue
        for ch in word:
            # Only CJK unified / extension-A / compatibility ideographs
            if _is_cjk(ch):
                char_counts[ch] = char_counts.get(ch, 0) + count
                total += count
    if not total:
        return {}
    return {ch: cnt / total for ch, cnt in char_counts.items()}


def _parse_cifu(path: Path) -> dict[str, float]:
    """Return per-character frequency from Cifu Written column.

    Single-character entries have NStrokes as a single number; multi-character
    entries use comma-separated stroke counts. We only keep single-character rows.
    """
    char_ppm: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("Word"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        word, strokes_str, written_ppm = parts[0], parts[10], parts[7]
        if not word or len(word) != 1:
            continue
        if "," in strokes_str:
            continue
        try:
            ppm = float(written_ppm)
        except ValueError:
            continue
        if _is_cjk(word):
            char_ppm[word] = ppm
    if not char_ppm:
        return {}
    max_ppm = max(char_ppm.values())
    return {ch: ppm / max_ppm for ch, ppm in char_ppm.items()}


def _parse_cuhk(path: Path) -> dict[str, float]:
    """Return per-character frequency from CUHK Lexis HTML table.

    The table has columns: 單字, 序號, 部首, 筆劃, 頻次, 頻率, 累積頻次, 累積頻率, 見檔次, 見檔率.
    We use the 頻率 column (percentage string like "4.422%").
    """
    html = path.read_text(encoding="utf-8", errors="ignore")
    parser = _TableParser()
    parser.feed(html)
    char_freq: dict[str, float] = {}
    for row in parser.rows[1:]:  # skip header
        if len(row) < 6:
            continue
        cell, freq_str = row[0], row[5]
        # Some cells contain punctuation pairs; take the first CJK character.
        ch = ""
        for c in cell:
            if _is_cjk(c):
                ch = c
                break
        if not ch:
            continue
        m = re.search(r"[0-9]*\.?[0-9]+", freq_str.replace(",", ""))
        if not m:
            continue
        freq_pct = float(m.group()) / 100.0
        char_freq[ch] = freq_pct
    if not char_freq:
        return {}
    max_freq = max(char_freq.values())
    return {ch: freq / max_freq for ch, freq in char_freq.items()}


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0x2CEB0 <= cp <= 0x2EBEF
    )


def _geometric_weighted_mean(values: list[tuple[float, float]]) -> float:
    """Compute weighted geometric mean of (value, weight) pairs.

    Adding a small floor avoids zeroing out characters that are missing from
    one source but present in another.
    """
    FLOOR = 1e-6
    total_weight = sum(w for _, w in values)
    if total_weight == 0:
        return 0.0
    log_sum = 0.0
    for v, w in values:
        log_sum += w * math.log(max(v, FLOOR))
    return math.exp(log_sum / total_weight)


def build_merged_frequency() -> dict[str, float]:
    """Download sources, normalize, and merge into a single character → score map."""
    print("Building merged Hong Kong character frequency table...")

    for key, cfg in SOURCES.items():
        _download(key, cfg["url"], cfg["file"])

    source_freqs: dict[str, dict[str, float]] = {}
    source_freqs["appledaily"] = _parse_appledaily_word_freq(SOURCES["appledaily"]["file"])
    source_freqs["cifu"] = _parse_cifu(SOURCES["cifu"]["file"])
    source_freqs["cuhk"] = _parse_cuhk(SOURCES["cuhk"]["file"])

    for key, freqs in source_freqs.items():
        print(f"  {key}: {len(freqs)} characters")

    all_chars = set()
    for freqs in source_freqs.values():
        all_chars.update(freqs.keys())

    merged: dict[str, float] = {}
    for ch in all_chars:
        values = [
            (source_freqs[src].get(ch, 0.0), cfg["weight"])
            for src, cfg in SOURCES.items()
        ]
        merged[ch] = _geometric_weighted_mean(values)

    # Normalize final scores to [0, 1]
    max_score = max(merged.values()) if merged else 1.0
    if max_score > 0:
        merged = {ch: score / max_score for ch, score in merged.items()}

    # Stable sort for human-readable output
    merged = dict(sorted(merged.items(), key=lambda x: (-x[1], x[0])))

    print(f"  merged: {len(merged)} characters, max score = {max(merged.values(), default=0):.4f}")
    return merged


def main() -> None:
    merged = build_merged_frequency()
    OUT_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
