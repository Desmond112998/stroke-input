#!/usr/bin/env python3
"""Download Conway Stroke Data and build the stroke database.

Downloads codepoint-character-sequence.txt from the stroke-input-data
GitHub repository (CC-BY-4.0), parses it into CharacterRecords, and
serializes to msgpack.

Data source: https://github.com/stroke-input/stroke-input-data
License: CC-BY-4.0
"""

import re
import sys
import urllib.request
from pathlib import Path

# Add src to path so we can import stroke_input
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_FILE = DATA_DIR / "codepoint-character-sequence.txt"
DB_FILE = DATA_DIR / "stroke_db.msgpack"
RANKING_FILE = DATA_DIR / "ranking-traditional.txt"
HK_FREQ_FILE = DATA_DIR / "character_frequency_hk.json"

BASE_URL = "https://raw.githubusercontent.com/stroke-input/stroke-input-data/master"
FILES_TO_DOWNLOAD = {
    "codepoint-character-sequence.txt": f"{BASE_URL}/codepoint-character-sequence.txt",
    "ranking-traditional.txt": f"{BASE_URL}/ranking-traditional.txt",
}


def download_file(name: str, url: str) -> None:
    dest = DATA_DIR / name
    if dest.exists():
        print(f"  Already exists: {name}, skipping")
        return
    print(f"  Downloading {name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "stroke-input/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print(f"  Saved: {dest} ({dest.stat().st_size:,} bytes)")


def parse_ranking(path: Path) -> dict[str, float]:
    """Parse ranking-traditional.txt into a character → frequency dict.

    Uses a Zipf–Mandelbrot mapping (not linear rank) so head characters
    dominate and mid-tail scores decay quickly:

        raw_i = 1 / (i + ZIPF_S) ** ZIPF_A
        freq_i = max(ZIPF_FLOOR, raw_i / raw_0)

    See ``stroke_input.config.ranking`` for the constants.
    """
    from stroke_input.config.ranking import ZIPF_A, ZIPF_FLOOR, ZIPF_S

    if not path.exists():
        return {}
    rankings: dict[str, float] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    chars = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for ch in line:
            if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf' or ch == '〇':
                chars.append(ch)
    total = len(chars)
    if total == 0:
        return {}
    raw0 = 1.0 / ((0 + ZIPF_S) ** ZIPF_A)
    for i, ch in enumerate(chars):
        raw = 1.0 / ((i + ZIPF_S) ** ZIPF_A)
        rankings[ch] = max(ZIPF_FLOOR, raw / raw0)
    return rankings


def expand_sequence_regex(seq_regex: str) -> list[str]:
    """Expand a stroke sequence regex into all possible sequences.

    Handles patterns like: (135|153), (1|3)12, 12(5|25)1
    Also handles backreferences like \\1 which repeat the matched group.
    E.g. (1534|1543)\\1 -> 15341534, 15431543

    Returns a list of all possible digit-only sequences.
    """
    # If no parentheses and no backrefs, return as-is
    if '(' not in seq_regex and '\\' not in seq_regex:
        if re.fullmatch(r'[1-5]+', seq_regex):
            return [seq_regex]
        return []

    # Parse into tokens: each result tracks (accumulated_string, {group_num: matched_text})
    results: list[tuple[str, dict[int, str]]] = [('', {})]
    group_num = 0
    i = 0

    while i < len(seq_regex):
        if seq_regex[i] == '(':
            group_num += 1
            current_group = group_num
            # Find matching close paren
            j = seq_regex.index(')', i)
            alternatives = seq_regex[i + 1:j].split('|')
            new_results = []
            for acc, groups in results:
                for alt in alternatives:
                    new_groups = dict(groups)
                    new_groups[current_group] = alt
                    new_results.append((acc + alt, new_groups))
            results = new_results
            i = j + 1
        elif seq_regex[i] == '\\' and i + 1 < len(seq_regex) and seq_regex[i + 1].isdigit():
            # Backreference: replace with the captured group text
            ref = int(seq_regex[i + 1])
            new_results = []
            for acc, groups in results:
                replacement = groups.get(ref, '')
                new_results.append((acc + replacement, groups))
            results = new_results
            i += 2
        elif seq_regex[i] in '12345':
            results = [(acc + seq_regex[i], groups) for acc, groups in results]
            i += 1
        else:
            i += 1

    # Filter to only valid sequences
    return [acc for acc, _ in results if re.fullmatch(r'[1-5]+', acc)]


def parse_stroke_data(path: Path, rankings: dict[str, float]) -> list:
    """Parse codepoint-character-sequence.txt into CharacterRecords.

    Each character may have multiple stroke sequence variants (from regex
    alternatives in the source data). All variants are included as separate
    CharacterRecord entries so the trie indexes every valid stroke path.
    """
    from stroke_input.data.models import CharacterRecord

    records = []
    seen_chars: set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('['):
            continue

        parts = line.split('\t')
        if len(parts) < 3:
            continue

        codepoint_str = parts[0].strip()
        char_field = parts[1].strip()
        seq_regex = parts[2].strip()

        # Skip if not a valid codepoint line
        if not codepoint_str.startswith('U+'):
            continue

        # Extract character and Conway script markers (^ traditional-only, * simplified-only)
        char_field_raw = char_field
        script_flag = ""
        if char_field_raw.endswith("^"):
            script_flag = "trad"
        elif char_field_raw.endswith("*"):
            script_flag = "simp"
        character = char_field_raw.rstrip("^*")
        if not character or len(character) != 1:
            continue

        # Skip duplicates
        if character in seen_chars:
            continue
        seen_chars.add(character)

        # Expand the sequence regex to get ALL possible stroke sequences
        sequences = expand_sequence_regex(seq_regex)
        if not sequences:
            continue

        freq = rankings.get(character, 0.0)

        # Index every variant so users can find the character regardless
        # of which stroke convention they follow (e.g. macOS vs Nokia)
        for seq_str in sequences:
            stroke_sequence = [int(d) for d in seq_str]
            records.append(CharacterRecord(
                character=character,
                stroke_sequence=stroke_sequence,
                stroke_count=len(stroke_sequence),
                frequency=freq,
                script_flag=script_flag,
            ))

    return records



def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: Downloading Conway Stroke Data...")
    for name, url in FILES_TO_DOWNLOAD.items():
        download_file(name, url)

    print("\nStep 2: Parsing ranking data...")
    if HK_FREQ_FILE.exists():
        import json
        rankings = json.loads(HK_FREQ_FILE.read_text(encoding="utf-8"))
        print(f"  Loaded {len(rankings):,} merged HK character frequencies from {HK_FREQ_FILE.name}")
    else:
        rankings = parse_ranking(RANKING_FILE)
        print(f"  Loaded {len(rankings):,} character rankings from {RANKING_FILE.name}")
        print(f"  (Run scripts/build_hk_frequency.py to build a richer HK frequency table)")

    print("\nStep 3: Building stroke database...")
    if DB_FILE.exists():
        print(f"  Removing old database...")
        DB_FILE.unlink()

    records = parse_stroke_data(RAW_FILE, rankings)
    print(f"  Parsed {len(records):,} characters")

    # Verify 你 (Conway sequence; historically mis-documented as 3235354)
    for r in records:
        if r.character == '你':
            print(f"  Verification: 你 = {r.stroke_sequence} (expected [3, 2, 3, 5, 2, 3, 4])")
            break

    from stroke_input.data.serializer import save_msgpack
    save_msgpack(records, DB_FILE)
    print(f"  Saved database: {DB_FILE}")

    print("\nDone! Stroke database ready for export.")


if __name__ == "__main__":
    main()
