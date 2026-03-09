#!/usr/bin/env python3
"""Download Make Me a Hanzi data files and build the stroke database.

Downloads dictionary.txt and graphics.txt from the Make Me a Hanzi GitHub
repository, then parses them into a msgpack stroke database.
"""

import urllib.request
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILES = {
    "dictionary.txt": "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt",
    "graphics.txt": "https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt",
}


def download_file(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  Already exists: {dest.name}, skipping")
        return
    print(f"  Downloading {dest.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "stroke-input/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print(f"  Saved: {dest} ({dest.stat().st_size:,} bytes)")


def build_database() -> None:
    db_path = DATA_DIR / "stroke_db.msgpack"
    if db_path.exists():
        print(f"  Database already exists: {db_path.name}, skipping")
        return

    print("  Parsing stroke data and building database...")
    from stroke_input.data.parser import parse_make_me_a_hanzi
    from stroke_input.data.serializer import save_msgpack

    records = parse_make_me_a_hanzi(
        DATA_DIR / "dictionary.txt",
        DATA_DIR / "graphics.txt",
    )
    save_msgpack(records, db_path)
    print(f"  Built database: {len(records):,} characters -> {db_path.name}")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Step 1: Downloading Make Me a Hanzi data files...")
    for filename, url in FILES.items():
        download_file(url, DATA_DIR / filename)

    print("\nStep 2: Building stroke database...")
    build_database()

    print("\nDone! You can now run the app with: python -m stroke_input")


if __name__ == "__main__":
    main()
