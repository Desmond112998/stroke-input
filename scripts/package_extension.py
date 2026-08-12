#!/usr/bin/env python3
"""Package the Chrome extension into a zip file for Chrome Web Store upload.

Usage:
    python scripts/package_extension.py
    python scripts/package_extension.py --output my-extension.zip

Steps:
    1. Rebuilds stroke database from Conway data (if source exists)
    2. Re-exports data for Chrome extension
    3. Validates manifest.json
    4. Zips only the files needed for the extension (excludes STORE_LISTING.md etc.)
    5. Reports final zip size
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "chrome-extension"
DEFAULT_OUTPUT = ROOT / "stroke-input-extension.zip"

# Files/patterns to exclude from the zip
EXCLUDE = {
    "STORE_LISTING.md",
}
EXCLUDE_DIR_PARTS = {
    "test",
    "screenshots",
}

REQUIRED_FILES = [
    "manifest.json",
    "engine.js",
    "content.js",
    "options.html",
    "options.js",
    "style.css",
    "data/strokes.json",
    "data/strokes_wubi.json",
    "data/phrases.json",
    "data/bigrams.json",
    "data/trigrams.json",
    "data/cantonese_freq.json",
    "data/ranking_config.json",
]


def rebuild_data() -> None:
    """Rebuild stroke DB and re-export for Chrome if source data exists."""
    raw_file = ROOT / "data" / "codepoint-character-sequence.txt"
    if not raw_file.exists():
        print("  Skipping rebuild (no source data found)")
        return

    print("  Rebuilding stroke database...")
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))

    from download_stroke_data import (
        HK_FREQ_FILE,
        parse_ranking,
        parse_stroke_data,
        RANKING_FILE,
        DB_FILE,
    )
    from stroke_input.data.serializer import save_msgpack

    if HK_FREQ_FILE.exists():
        import json

        rankings = json.loads(HK_FREQ_FILE.read_text(encoding="utf-8"))
        print(f"  Using merged HK frequencies ({len(rankings)} chars)")
    else:
        rankings = parse_ranking(RANKING_FILE)
        print(f"  Using fallback rankings ({len(rankings)} chars)")
    records = parse_stroke_data(raw_file, rankings)
    save_msgpack(records, DB_FILE)
    print(f"  Built {len(records):,} records")

    print("  Exporting for Chrome extension...")
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "scripts" / "export_for_chrome.py")], check=True)


def validate_manifest() -> dict:
    """Validate manifest.json has required fields."""
    manifest_path = EXT_DIR / "manifest.json"
    if not manifest_path.exists():
        print("ERROR: manifest.json not found")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    required_keys = ["manifest_version", "name", "version", "description"]
    missing = [k for k in required_keys if k not in manifest]
    if missing:
        print(f"ERROR: manifest.json missing keys: {missing}")
        sys.exit(1)

    if manifest["manifest_version"] != 3:
        print("WARNING: manifest_version is not 3")

    return manifest


def validate_files() -> None:
    """Check all required extension files exist."""
    missing = []
    for f in REQUIRED_FILES:
        if not (EXT_DIR / f).exists():
            missing.append(f)
    if missing:
        print(f"ERROR: Missing required files: {missing}")
        sys.exit(1)


def build_zip(output: Path) -> None:
    """Create the extension zip from chrome-extension/ directory."""
    if output.exists():
        output.unlink()

    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(EXT_DIR.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(EXT_DIR)
            if rel.name in EXCLUDE:
                continue
            if any(part in EXCLUDE_DIR_PARTS for part in rel.parts):
                continue
            zf.write(file_path, rel)
            count += 1

    size_kb = output.stat().st_size / 1024
    print(f"  Packed {count} files -> {output.name} ({size_kb:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Package Chrome extension for Web Store")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help="Output zip path (default: stroke-input-extension.zip)")
    parser.add_argument("--skip-rebuild", action="store_true",
                        help="Skip rebuilding stroke data")
    args = parser.parse_args()

    print("Step 1: Rebuild data")
    if args.skip_rebuild:
        print("  Skipped (--skip-rebuild)")
    else:
        rebuild_data()

    print("\nStep 2: Validate manifest")
    manifest = validate_manifest()
    print(f"  {manifest['name']} v{manifest['version']}")

    print("\nStep 3: Validate files")
    validate_files()
    print("  All required files present")

    print("\nStep 4: Package zip")
    build_zip(args.output)

    print(f"\nDone! Upload {args.output.name} to Chrome Web Store.")


if __name__ == "__main__":
    main()
