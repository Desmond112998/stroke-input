"""Phrase dictionary loader for Traditional Chinese phrases.

Loads phrase data from a TSV text file (one phrase per line, tab-separated
phrase and frequency) and indexes them by first character for O(1) lookup.

Expected file format (TSV)::

    你好\t0.85
    中文\t0.72
    電腦\t0.68

Or JSON lines::

    {"phrase": "你好", "frequency": 0.85}
    {"phrase": "中文", "frequency": 0.72}
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from stroke_input.data.models import PhraseEntry

logger = logging.getLogger(__name__)


class PhraseDict:
    """Dictionary of phrases indexed by first character for fast lookup.

    Attributes:
        _index: Mapping from first character to list of PhraseEntry,
                sorted by descending frequency within each bucket.
        _total: Total number of phrases loaded.
    """

    def __init__(self) -> None:
        self._index: dict[str, list[PhraseEntry]] = {}
        self._total: int = 0

    @property
    def total(self) -> int:
        """Total number of phrases in the dictionary."""
        return self._total

    def lookup(self, character: str) -> list[PhraseEntry]:
        """Return phrases starting with the given character.

        Args:
            character: A single Chinese character to look up.

        Returns:
            List of PhraseEntry sorted by descending frequency.
            Empty list if no phrases start with this character.
        """
        return self._index.get(character, [])

    def _build_index(self, entries: list[PhraseEntry]) -> None:
        """Build the first-character index from a flat list of entries."""
        buckets: dict[str, list[PhraseEntry]] = defaultdict(list)
        for entry in entries:
            if not entry.phrase or len(entry.phrase) < 2:
                continue
            first_char = entry.phrase[0]
            buckets[first_char].append(entry)

        # Sort each bucket by frequency descending for ranked lookup
        for char, phrase_list in buckets.items():
            phrase_list.sort(key=lambda e: e.frequency, reverse=True)

        self._index = dict(buckets)
        self._total = sum(len(v) for v in self._index.values())


def _parse_tsv_line(line: str, line_num: int) -> PhraseEntry | None:
    """Parse a single TSV line into a PhraseEntry.

    Returns None for blank/comment lines or malformed entries.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("\t")
    phrase = parts[0].strip()
    if len(phrase) < 2:
        logger.warning("Line %d: phrase too short, skipping: %r", line_num, phrase)
        return None

    frequency = 0.0
    if len(parts) >= 2:
        try:
            frequency = float(parts[1].strip())
        except ValueError:
            logger.warning(
                "Line %d: invalid frequency %r, defaulting to 0.0",
                line_num,
                parts[1].strip(),
            )

    return PhraseEntry(phrase=phrase, frequency=frequency)


def _parse_jsonl_line(line: str, line_num: int) -> PhraseEntry | None:
    """Parse a single JSON-lines entry into a PhraseEntry."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("Line %d: invalid JSON, skipping", line_num)
        return None

    phrase = obj.get("phrase", "")
    if len(phrase) < 2:
        logger.warning("Line %d: phrase too short, skipping: %r", line_num, phrase)
        return None

    frequency = float(obj.get("frequency", 0.0))
    return PhraseEntry(phrase=phrase, frequency=frequency)


def load_phrase_dict(path: Path) -> PhraseDict:
    """Load a phrase dictionary from a file.

    Auto-detects format by extension:
    - .tsv / .txt → tab-separated values
    - .jsonl / .json → JSON lines

    Args:
        path: Path to the phrase data file.

    Returns:
        A PhraseDict indexed by first character.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not recognized.
    """
    if not path.exists():
        raise FileNotFoundError(f"Phrase file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in (".tsv", ".txt"):
        parser = _parse_tsv_line
    elif suffix in (".jsonl", ".json"):
        parser = _parse_jsonl_line
    else:
        raise ValueError(f"Unrecognized phrase file extension: {suffix!r}")

    entries: list[PhraseEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            entry = parser(line, line_num)
            if entry is not None:
                entries.append(entry)

    pd = PhraseDict()
    pd._build_index(entries)
    logger.info(
        "Loaded %d phrases from %s (%d first-character buckets)",
        pd.total,
        path,
        len(pd._index),
    )
    return pd
