"""User frequency store for per-character selection counts, recency, and
position-aware learning.

Persists how often the user selects each character, the timestamp of each
selection (for recency decay), and per-(stroke_seq, character) rank history
(for position-aware ranking) to a JSON file.

File format (v2)::

    {
        "v": 2,
        "counts": {"你": 15, "好": 8},
        "timestamps": {"你": 1717600000.0},
        "positions": {"jk": {"你": [0, 1, 0]}}
    }

Backwards-compatible with the old flat format ``{"你": 15, "好": 8}``
(detected by absence of the ``"v"`` key).

Recency scoring
---------------
``recency_score(char, now, tau_days)`` returns ``exp(-Δt / τ)`` where Δt is
the time since the last selection in days and τ = tau_days (default 30).
Returns 0.0 if the character has never been selected.

Position-aware scoring
----------------------
``record_position(stroke_seq, char, rank)`` records the rank at which the
user selected *char* for a given stroke prefix.
``position_score(stroke_seq, char)`` returns ``1 / (1 + avg_rank)``, which
is 1.0 when the user always selects it at rank 0 and decreases as the
average rank rises.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum number of stored rank observations per (stroke_seq, char) pair.
# Keeps memory bounded; oldest entries are dropped.
_MAX_RANK_HISTORY = 20

# Current persistence format version
_FORMAT_VERSION = 2

# Default threshold for auto-pinning: how many consecutive rank-0 selections
# before the character is auto-pinned to position 1 for that stroke prefix.
AUTO_PIN_THRESHOLD = 5

# Sentinel score assigned to pinned characters so position_score returns 1.0
# (stored as average_rank = 0 via a sentinel rank list).
_PIN_SENTINEL_RANK = 0


class UserFreqStore:
    """Tracks per-character selection counts, recency, and position data.

    Attributes:
        _path: Path to the JSON file for persistence.
        _counts: character → selection count.
        _timestamps: character → Unix timestamp of the most recent selection.
        _positions: stroke_seq → {char → list[rank]} (bounded history).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._counts: dict[str, int] = {}
        self._timestamps: dict[str, float] = {}
        self._positions: dict[str, dict[str, list[int]]] = {}
        self._phrase_freq: dict[str, int] = {}  # B3: learned phrase counts
        self._pins: dict[str, set[str]] = {}    # C2: stroke_seq → {pinned chars}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Path to the backing JSON file."""
        return self._path

    @property
    def counts(self) -> dict[str, int]:
        """Read-only view of the current counts."""
        return dict(self._counts)

    # ------------------------------------------------------------------
    # Basic frequency
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Recency (A2)
    # ------------------------------------------------------------------

    def record_selection(self, character: str, timestamp: Optional[float] = None) -> None:
        """Record a character selection with a timestamp.

        Updates both the count and the timestamp (keeping the latest one).

        Args:
            character: The selected character.
            timestamp: Unix timestamp of the selection.  Defaults to now.
        """
        if not character:
            return
        ts = timestamp if timestamp is not None else time.time()
        self._counts[character] = self._counts.get(character, 0) + 1
        existing = self._timestamps.get(character)
        if existing is None or ts > existing:
            self._timestamps[character] = ts

    def recency_score(
        self,
        character: str,
        now: Optional[float] = None,
        tau_days: float = 30.0,
    ) -> float:
        """Exponential recency score: exp(-Δt / τ).

        Args:
            character: The character to score.
            now: Reference time (Unix timestamp).  Defaults to ``time.time()``.
            tau_days: Decay time constant in days (default 30).

        Returns:
            Float in [0, 1].  Returns 0.0 if the character was never recorded
            via :meth:`record_selection`.
        """
        ts = self._timestamps.get(character)
        if ts is None:
            return 0.0
        t_now = now if now is not None else time.time()
        delta_days = max(0.0, (t_now - ts) / 86400.0)
        return math.exp(-delta_days / tau_days) if tau_days > 0 else 0.0

    # ------------------------------------------------------------------
    # Position-aware (A3)
    # ------------------------------------------------------------------

    def record_position(self, stroke_seq: str, character: str, rank: int) -> None:
        """Record the rank at which *character* was selected for *stroke_seq*.

        Maintains a bounded history of up to ``_MAX_RANK_HISTORY`` ranks per
        (stroke_seq, character) pair (oldest entries dropped on overflow).

        Args:
            stroke_seq: Stroke prefix string (e.g. ``"jk"`` or ``"12"``).
            character: The selected character.
            rank: Zero-based rank position at which the character was chosen.
        """
        if stroke_seq not in self._positions:
            self._positions[stroke_seq] = {}
        char_ranks = self._positions[stroke_seq]
        if character not in char_ranks:
            char_ranks[character] = []
        ranks = char_ranks[character]
        ranks.append(rank)
        if len(ranks) > _MAX_RANK_HISTORY:
            ranks.pop(0)

    def average_rank(self, stroke_seq: str, character: str) -> Optional[float]:
        """Return the average selection rank for (stroke_seq, character).

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to look up.

        Returns:
            Average rank as a float, or ``None`` if no data is available.
        """
        ranks = self._positions.get(stroke_seq, {}).get(character)
        if not ranks:
            return None
        return sum(ranks) / len(ranks)

    # ------------------------------------------------------------------
    # Phrase auto-learning (B3)
    # ------------------------------------------------------------------

    def record_phrase(self, phrase: str) -> None:
        """Record a user-typed phrase (two or more characters).

        Single-character or empty strings are silently ignored.

        Args:
            phrase: The phrase string to record.
        """
        if not phrase or len(phrase) < 2:
            return
        self._phrase_freq[phrase] = self._phrase_freq.get(phrase, 0) + 1

    def get_phrase_count(self, phrase: str) -> int:
        """Return how many times the user has typed *phrase*.

        Args:
            phrase: The phrase string.

        Returns:
            Count (≥ 0).
        """
        return self._phrase_freq.get(phrase, 0)

    def auto_learn_phrase(self, chars: list[str]) -> None:
        """Join *chars* into a phrase and record it.

        Convenience helper for auto-learning when the user consecutively
        selects multiple characters.  Ignores sequences shorter than 2.

        Args:
            chars: List of single characters committed in sequence.
        """
        phrase = "".join(chars)
        self.record_phrase(phrase)

    def top_phrases(self, n: int = 20) -> list[tuple[str, int]]:
        """Return the top *n* most frequently typed phrases.

        Args:
            n: Maximum number of entries to return.

        Returns:
            List of ``(phrase, count)`` tuples sorted by count descending.
        """
        items = sorted(self._phrase_freq.items(), key=lambda x: x[1], reverse=True)
        return items[:n]

    # ------------------------------------------------------------------
    # Smart pin (C2)
    # ------------------------------------------------------------------

    def pin_character(self, stroke_seq: str, character: str) -> None:
        """Permanently pin *character* to rank 0 for *stroke_seq*.

        A pinned character always receives a :meth:`position_score` of 1.0,
        regardless of its historical average rank.

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to pin.
        """
        if stroke_seq not in self._pins:
            self._pins[stroke_seq] = set()
        self._pins[stroke_seq].add(character)

    def unpin_character(self, stroke_seq: str, character: str) -> None:
        """Remove the pin for *character* under *stroke_seq*.

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to unpin.
        """
        if stroke_seq in self._pins:
            self._pins[stroke_seq].discard(character)

    def is_pinned(self, stroke_seq: str, character: str) -> bool:
        """Return whether *character* is pinned for *stroke_seq*.

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to check.

        Returns:
            ``True`` if pinned, ``False`` otherwise.
        """
        return character in self._pins.get(stroke_seq, set())

    def position_score(self, stroke_seq: str, character: str) -> float:
        """Score derived from average selection rank: ``1 / (1 + avg_rank)``.

        Pinned characters always return 1.0 regardless of rank history.

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to score.

        Returns:
            Float in [0, 1].  Returns 0.0 if no position data is available
            and the character is not pinned.
        """
        if self.is_pinned(stroke_seq, character):
            return 1.0
        avg = self.average_rank(stroke_seq, character)
        if avg is None:
            return 0.0
        return 1.0 / (1.0 + avg)

    def maybe_auto_pin(
        self,
        stroke_seq: str,
        character: str,
        threshold: int = AUTO_PIN_THRESHOLD,
    ) -> bool:
        """Auto-pin *character* if it has been selected at rank 0 at least
        *threshold* times in the rank history for *stroke_seq*.

        Args:
            stroke_seq: Stroke prefix string.
            character: The character to evaluate.
            threshold: Minimum number of rank-0 selections required.

        Returns:
            ``True`` if the character was (just) pinned, ``False`` otherwise.
        """
        ranks = self._positions.get(stroke_seq, {}).get(character, [])
        rank_zero_count = sum(1 for r in ranks if r == 0)
        if rank_zero_count >= threshold:
            self.pin_character(stroke_seq, character)
            return True
        return False

    def load(self) -> None:
        """Load data from the JSON file.

        Supports both the legacy flat format (``{"你": 5}``) and the current
        v2 format.  If the file is missing or corrupted, starts fresh.
        """
        if not self._path.exists():
            logger.info("User frequency file not found, starting fresh: %s", self._path)
            self._counts = {}
            self._timestamps = {}
            self._positions = {}
            self._phrase_freq = {}
            self._pins = {}
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
            self._timestamps = {}
            self._positions = {}
            self._phrase_freq = {}
            self._pins = {}
            return

        if not isinstance(data, dict):
            logger.warning(
                "User frequency file has unexpected format (expected dict), starting fresh"
            )
            self._counts = {}
            self._timestamps = {}
            self._positions = {}
            self._phrase_freq = {}
            self._pins = {}
            return

        if data.get("v") == _FORMAT_VERSION:
            # ---- v2 format ----
            raw_counts = data.get("counts", {})
            raw_ts = data.get("timestamps", {})
            raw_pos = data.get("positions", {})
            raw_pf = data.get("phrase_freq", {})

            clean_counts: dict[str, int] = {}
            for key, value in raw_counts.items():
                if isinstance(key, str) and isinstance(value, (int, float)):
                    clean_counts[key] = int(value)
                else:
                    logger.warning(
                        "Skipping invalid count entry: %r → %r", key, value
                    )
            self._counts = clean_counts

            self._timestamps = {
                k: float(v)
                for k, v in raw_ts.items()
                if isinstance(k, str) and isinstance(v, (int, float))
            }

            loaded_positions: dict[str, dict[str, list[int]]] = {}
            for seq, char_map in raw_pos.items():
                if not isinstance(char_map, dict):
                    continue
                loaded_positions[seq] = {
                    ch: [int(r) for r in ranks if isinstance(r, (int, float))]
                    for ch, ranks in char_map.items()
                    if isinstance(ranks, list)
                }
            self._positions = loaded_positions

            self._phrase_freq = {
                k: int(v)
                for k, v in raw_pf.items()
                if isinstance(k, str) and isinstance(v, (int, float))
            }

            # pins: {stroke_seq: [char, ...]}
            raw_pins = data.get("pins", {})
            self._pins = {
                seq: set(chars)
                for seq, chars in raw_pins.items()
                if isinstance(chars, list)
            }
        else:
            # ---- Legacy flat format: {"你": 5, ...} ----
            clean: dict[str, int] = {}
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, (int, float)):
                    clean[key] = int(value)
                else:
                    logger.warning(
                        "Skipping invalid entry in user freq: %r → %r", key, value
                    )
            self._counts = clean
            self._timestamps = {}
            self._positions = {}
            self._phrase_freq = {}
            self._pins = {}

        logger.info(
            "Loaded user frequency data: %d characters, %d timestamps, "
            "%d position contexts, %d learned phrases, %d pin groups",
            len(self._counts),
            len(self._timestamps),
            len(self._positions),
            len(self._phrase_freq),
            len(self._pins),
        )

    def save(self) -> None:
        """Persist current data to the JSON file (v2 format).

        Creates parent directories if needed. Logs a warning on failure.
        """
        payload = {
            "v": _FORMAT_VERSION,
            "counts": self._counts,
            "timestamps": self._timestamps,
            "positions": self._positions,
            "phrase_freq": self._phrase_freq,
            "pins": {seq: sorted(chars) for seq, chars in self._pins.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug("Saved user frequency data: %d characters", len(self._counts))
        except OSError as exc:
            logger.warning("Failed to save user frequency file %s: %s", self._path, exc)
