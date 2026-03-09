"""User frequency store for per-character selection counts.

Persists how often the user selects each character to a JSON file,
enabling the FrequencyRanker to adapt to user preferences over time.

JSON file format::

    {
        "你": 15,
        "好": 8,
        "中": 23
    }
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class UserFreqStore:
    """Tracks per-character selection counts with JSON persistence.

    Attributes:
        _path: Path to the JSON file for persistence.
        _counts: In-memory mapping of character → selection count.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._counts: dict[str, int] = {}

    @property
    def path(self) -> Path:
        """Path to the backing JSON file."""
        return self._path

    @property
    def counts(self) -> dict[str, int]:
        """Read-only view of the current counts."""
        return dict(self._counts)

    def increment(self, character: str) -> None:
        """Increment the selection count for a character.

        Args:
            character: A single character whose count to bump.
        """
        if not character:
            return
        self._counts[character] = self._counts.get(character, 0) + 1

    def get_score(self, character: str) -> int:
        """Return the selection count for a character.

        Args:
            character: The character to look up.

        Returns:
            The number of times this character has been selected, or 0.
        """
        return self._counts.get(character, 0)

    def load(self) -> None:
        """Load counts from the JSON file.

        If the file is missing or corrupted, starts with an empty store
        and logs a warning.
        """
        if not self._path.exists():
            logger.info("User frequency file not found, starting fresh: %s", self._path)
            self._counts = {}
            return

        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load user frequency file %s (%s), starting fresh",
                self._path,
                exc,
            )
            self._counts = {}
            return

        if not isinstance(data, dict):
            logger.warning(
                "User frequency file has unexpected format (expected dict), starting fresh"
            )
            self._counts = {}
            return

        # Validate entries: keep only str→int pairs
        clean: dict[str, int] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, (int, float)):
                clean[key] = int(value)
            else:
                logger.warning("Skipping invalid entry in user freq: %r → %r", key, value)
        self._counts = clean
        logger.info("Loaded user frequency data: %d characters", len(self._counts))

    def save(self) -> None:
        """Persist current counts to the JSON file.

        Creates parent directories if needed. Logs a warning on failure.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._counts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug("Saved user frequency data: %d characters", len(self._counts))
        except OSError as exc:
            logger.warning("Failed to save user frequency file %s: %s", self._path, exc)
