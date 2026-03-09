"""InferenceEngine: fuzzy matching and contextual boosting for stroke input.

Performs approximate matching (tolerating up to one stroke substitution) and
contextual ranking (boosting characters that commonly follow the last selected
character in the phrase dictionary).

Fuzzy matches are only surfaced when fewer than 3 exact prefix matches exist,
and they always rank below exact matches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from stroke_input.data.models import CharacterRecord, StrokeType
from stroke_input.data.phrase_loader import PhraseDict
from stroke_input.engine.stroke_engine import StrokeEngine

logger = logging.getLogger(__name__)

# Stroke codes for substitution during fuzzy matching
_STROKE_CODES = [
    StrokeType.HENG,
    StrokeType.SHU,
    StrokeType.PIE,
    StrokeType.DIAN,
    StrokeType.ZHE,
]

# Minimum number of exact matches before fuzzy results are suppressed
_EXACT_THRESHOLD = 3


@dataclass
class ScoredCandidate:
    """A candidate character with its matching metadata.

    Attributes:
        record: The underlying CharacterRecord.
        is_exact: True if the candidate was an exact prefix match.
        context_boost: Additional score from contextual phrase association.
    """

    record: CharacterRecord
    is_exact: bool = True
    context_boost: float = 0.0


class InferenceEngine:
    """Fuzzy matching and contextual boosting layer on top of StrokeEngine.

    The engine wraps a ``StrokeEngine`` for exact prefix lookups and adds:

    * **Fuzzy matching** – when fewer than 3 exact prefix matches exist,
      generates candidate sequences by substituting one stroke at a time
      and queries the underlying trie for each variant.
    * **Contextual boost** – after a character is selected, phrases starting
      with that character are looked up in the ``PhraseDict`` and the second
      character of each phrase receives a ranking boost.

    Usage::

        ie = InferenceEngine(stroke_engine, phrase_dict)
        candidates = ie.query([1, 3, 4])
        ie.on_character_selected("大")
        candidates = ie.query([1, 1])  # contextual boost applied
    """

    def __init__(
        self,
        stroke_engine: StrokeEngine,
        phrase_dict: Optional[PhraseDict] = None,
    ) -> None:
        self._engine = stroke_engine
        self._phrase_dict = phrase_dict
        self._last_selected: Optional[str] = None
        # Pre-computed set of boosted characters (second chars of phrases)
        self._boosted_chars: dict[str, float] = {}

    @property
    def last_selected(self) -> Optional[str]:
        """The last character selected by the user (for contextual boost)."""
        return self._last_selected

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_character_selected(self, character: str) -> None:
        """Notify the engine that a character was selected.

        Updates the contextual boost set based on phrases starting with
        *character* in the phrase dictionary.

        Args:
            character: The character the user just selected.
        """
        self._last_selected = character
        self._boosted_chars = {}

        if not self._phrase_dict or not character:
            return

        phrases = self._phrase_dict.lookup(character)
        for entry in phrases:
            if len(entry.phrase) >= 2:
                second_char = entry.phrase[1]
                # Use phrase frequency as boost weight; keep the max if
                # the same character appears in multiple phrases.
                existing = self._boosted_chars.get(second_char, 0.0)
                self._boosted_chars[second_char] = max(existing, entry.frequency)

    def clear_context(self) -> None:
        """Reset the contextual boost state."""
        self._last_selected = None
        self._boosted_chars = {}

    def query(
        self,
        stroke_sequence: Optional[list[int]] = None,
    ) -> list[ScoredCandidate]:
        """Return scored candidates for the given stroke sequence.

        Exact prefix matches are returned first.  When fewer than 3 exact
        matches exist, fuzzy matches (one-stroke substitution) are appended.
        Contextual boost is applied to all candidates.

        Args:
            stroke_sequence: The stroke sequence to query.  If ``None``,
                uses the StrokeEngine's current internal sequence.

        Returns:
            A list of ``ScoredCandidate`` sorted by:
            1. Exact matches before fuzzy matches
            2. Within each group, contextual boost (descending)
            3. Then by character frequency (descending)
        """
        seq = stroke_sequence if stroke_sequence is not None else self._engine.current_sequence
        if not seq:
            return []

        # --- Exact prefix matches ---
        exact_records = self._engine.query(seq)
        exact_chars = {r.character for r in exact_records}
        exact_candidates = [
            ScoredCandidate(
                record=r,
                is_exact=True,
                context_boost=self._boosted_chars.get(r.character, 0.0),
            )
            for r in exact_records
        ]

        # --- Fuzzy matches (only when exact < threshold) ---
        fuzzy_candidates: list[ScoredCandidate] = []
        if len(exact_candidates) < _EXACT_THRESHOLD:
            fuzzy_records = self._fuzzy_match(seq, exact_chars)
            fuzzy_candidates = [
                ScoredCandidate(
                    record=r,
                    is_exact=False,
                    context_boost=self._boosted_chars.get(r.character, 0.0),
                )
                for r in fuzzy_records
            ]

        # --- Sort each group ---
        exact_candidates.sort(
            key=lambda c: (c.context_boost, c.record.frequency),
            reverse=True,
        )
        fuzzy_candidates.sort(
            key=lambda c: (c.context_boost, c.record.frequency),
            reverse=True,
        )

        return exact_candidates + fuzzy_candidates

    # ------------------------------------------------------------------
    # Fuzzy matching internals
    # ------------------------------------------------------------------

    def _fuzzy_match(
        self,
        sequence: list[int],
        exclude: set[str],
    ) -> list[CharacterRecord]:
        """Generate fuzzy matches by substituting one stroke at a time.

        For each position in *sequence*, replace the stroke with each of
        the 5 basic stroke types (skipping the original) and query the
        trie.  Characters already in *exclude* (exact matches) are omitted.

        Args:
            sequence: The original stroke sequence.
            exclude: Characters to exclude (already exact-matched).

        Returns:
            De-duplicated list of fuzzy-matched CharacterRecords.
        """
        seen: set[str] = set(exclude)
        results: list[CharacterRecord] = []

        for pos in range(len(sequence)):
            original_code = sequence[pos]
            for substitute in _STROKE_CODES:
                if substitute == original_code:
                    continue
                # Build the modified sequence
                modified = list(sequence)
                modified[pos] = substitute
                matches = self._engine.query(modified)
                for rec in matches:
                    if rec.character not in seen:
                        seen.add(rec.character)
                        results.append(rec)

        return results
