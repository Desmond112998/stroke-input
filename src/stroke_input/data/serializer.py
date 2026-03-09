"""Stroke database serializer and deserializer.

Supports two formats:
- JSON: human-readable, for debug/development
- msgpack: compact binary, for production fast loading

Also provides a pretty-printer for human-readable text output.
"""

import json
import logging
from pathlib import Path

import msgpack

from stroke_input.data.models import CharacterRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal conversion helpers
# ---------------------------------------------------------------------------

def _record_to_dict(record: CharacterRecord) -> dict:
    """Convert a CharacterRecord to a plain dict for serialization."""
    return {
        "character": record.character,
        "stroke_sequence": record.stroke_sequence,
        "stroke_count": record.stroke_count,
        "frequency": record.frequency,
    }


def _dict_to_record(d: dict) -> CharacterRecord:
    """Convert a plain dict back to a CharacterRecord."""
    return CharacterRecord(
        character=d["character"],
        stroke_sequence=list(d["stroke_sequence"]),
        stroke_count=d["stroke_count"],
        frequency=float(d["frequency"]),
    )


# ---------------------------------------------------------------------------
# JSON serialization (human-readable, debug)
# ---------------------------------------------------------------------------

def serialize_json(records: list[CharacterRecord]) -> str:
    """Serialize a list of CharacterRecord to a JSON string.

    Args:
        records: The character records to serialize.

    Returns:
        A JSON string with indentation for readability.
    """
    data = [_record_to_dict(r) for r in records]
    return json.dumps(data, ensure_ascii=False, indent=2)


def save_json(records: list[CharacterRecord], path: Path) -> None:
    """Serialize records to a JSON file."""
    path.write_text(serialize_json(records), encoding="utf-8")
    logger.info("Saved %d records to JSON: %s", len(records), path)


def load_json(path: Path) -> list[CharacterRecord]:
    """Load records from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        List of CharacterRecord loaded from the file.
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return [_dict_to_record(d) for d in data]


# ---------------------------------------------------------------------------
# msgpack serialization (compact binary, production)
# ---------------------------------------------------------------------------

def serialize_msgpack(records: list[CharacterRecord]) -> bytes:
    """Serialize a list of CharacterRecord to msgpack bytes.

    Args:
        records: The character records to serialize.

    Returns:
        Compact binary msgpack representation.
    """
    data = [_record_to_dict(r) for r in records]
    return msgpack.packb(data, use_bin_type=True)


def save_msgpack(records: list[CharacterRecord], path: Path) -> None:
    """Serialize records to a msgpack file."""
    path.write_bytes(serialize_msgpack(records))
    logger.info("Saved %d records to msgpack: %s", len(records), path)


def load_msgpack(path: Path) -> list[CharacterRecord]:
    """Load records from a msgpack file.

    Args:
        path: Path to the msgpack file.

    Returns:
        List of CharacterRecord loaded from the file.
    """
    raw = path.read_bytes()
    data = msgpack.unpackb(raw, raw=False)
    return [_dict_to_record(d) for d in data]


# ---------------------------------------------------------------------------
# Unified loader (auto-detect format by extension)
# ---------------------------------------------------------------------------

def load_database(path: Path) -> list[CharacterRecord]:
    """Load a stroke database from a file, auto-detecting format by extension.

    Supported extensions:
    - .json → JSON format
    - .msgpack / .mpk → msgpack format

    Args:
        path: Path to the database file.

    Returns:
        List of CharacterRecord.

    Raises:
        ValueError: If the file extension is not recognized.
    """
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in (".msgpack", ".mpk"):
        return load_msgpack(path)
    raise ValueError(f"Unrecognized database file extension: {suffix!r}")


# ---------------------------------------------------------------------------
# Pretty-printer
# ---------------------------------------------------------------------------

STROKE_DISPLAY = {1: "一", 2: "丨", 3: "丿", 4: "丶", 5: "乙"}


def pretty_print(records: list[CharacterRecord]) -> str:
    """Format a database into human-readable text.

    Each line shows: character, stroke symbols, stroke codes, and frequency.

    Example output::

        字  一乙一丨一丨  [1,5,1,2,1,2]  freq=0.00
        大  一丿丶        [1,3,4]        freq=0.00

    Args:
        records: The character records to format.

    Returns:
        Multi-line human-readable string.
    """
    lines: list[str] = []
    for rec in records:
        strokes_visual = "".join(
            STROKE_DISPLAY.get(s, "?") for s in rec.stroke_sequence
        )
        strokes_codes = "[" + ",".join(str(s) for s in rec.stroke_sequence) + "]"
        line = f"{rec.character}  {strokes_visual}  {strokes_codes}  freq={rec.frequency:.2f}"
        lines.append(line)
    return "\n".join(lines)
