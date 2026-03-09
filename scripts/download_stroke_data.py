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
    """Parse ranking-traditional.txt into a character -> frequency dict."""
    if not path.exists():
        return {}
    rankings: dict[str, float] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    chars = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Each line is just characters, ranked by frequency
        for ch in line:
            if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf' or ch == '〇':
                chars.append(ch)
    # Assign frequency scores: higher rank = higher score
    total = len(chars)
    for i, ch in enumerate(chars):
        rankings[ch] = max(0.01, 1.0 - (i / total))
    return rankings


def expand_sequence_regex(seq_regex: str) -> list[str]:
    """Expand a simple stroke sequence regex into all possible sequences.

    Handles patterns like: (135|153), (1|3)12, 12(5|25)1
    Returns a list of all possible digit-only sequences.
    """
    # Remove backslash references like \1 (backreferences to capture groups)
    # For our purposes, we just take the first alternative
    seq_regex = re.sub(r'\\[0-9]', '', seq_regex)

    # If no parentheses, return as-is (if it's pure digits)
    if '(' not in seq_regex:
        if re.fullmatch(r'[1-5]+', seq_regex):
            return [seq_regex]
        return []

    # Expand parenthesized alternatives
    # Find the first group and expand it
    results = ['']
    i = 0
    while i < len(seq_regex):
        if seq_regex[i] == '(':
            # Find matching close paren
            j = seq_regex.index(')', i)
            alternatives = seq_regex[i+1:j].split('|')
            new_results = []
            for prefix in results:
                for alt in alternatives:
                    new_results.append(prefix + alt)
            results = new_results
            i = j + 1
        elif seq_regex[i] in '12345':
            results = [r + seq_regex[i] for r in results]
            i += 1
        else:
            i += 1

    # Filter to only valid sequences
    return [r for r in results if re.fullmatch(r'[1-5]+', r)]


def parse_stroke_data(path: Path, rankings: dict[str, float]) -> list:
    """Parse codepoint-character-sequence.txt into CharacterRecords."""
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

        # Extract character (remove markers like ^, *)
        character = char_field.rstrip('^*')
        if not character or len(character) != 1:
            continue

        # Skip duplicates
        if character in seen_chars:
            continue
        seen_chars.add(character)

        # Expand the sequence regex to get possible stroke sequences
        sequences = expand_sequence_regex(seq_regex)
        if not sequences:
            continue

        # Use the first (primary) sequence
        primary_seq = sequences[0]
        stroke_sequence = [int(d) for d in primary_seq]

        freq = rankings.get(character, 0.0)

        records.append(CharacterRecord(
            character=character,
            stroke_sequence=stroke_sequence,
            stroke_count=len(stroke_sequence),
            frequency=freq,
        ))

    return records


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: Downloading Conway Stroke Data...")
    for name, url in FILES_TO_DOWNLOAD.items():
        download_file(name, url)

    print("\nStep 2: Parsing ranking data...")
    rankings = parse_ranking(RANKING_FILE)
    print(f"  Loaded {len(rankings):,} character rankings")

    print("\nStep 3: Building stroke database...")
    if DB_FILE.exists():
        print(f"  Removing old database...")
        DB_FILE.unlink()

    records = parse_stroke_data(RAW_FILE, rankings)
    print(f"  Parsed {len(records):,} characters")

    # Verify 你
    for r in records:
        if r.character == '你':
            print(f"  Verification: 你 = {r.stroke_sequence} (expected [3,2,3,5,3,5,4])")
            break

    from stroke_input.data.serializer import save_msgpack
    save_msgpack(records, DB_FILE)
    print(f"  Saved database: {DB_FILE}")

    print("\nDone! You can now run the app.")


if __name__ == "__main__":
    main()
