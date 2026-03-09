"""FrequencyRanker: composite scoring and ranking for stroke input candidates.

Combines static frequency, user adaptation score, contextual relevance,
and match quality into a single composite score for candidate ordering.

Composite score formula:
    score = w1 * static_freq + w2 * user_freq + w3 * context_boost + w4 * match_quality

Secondary sort: stroke_count ascending (fewer strokes first) when composite
scores are equal.

Traditional Chinese forms receive a small boost over Simplified forms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from stroke_input.data.user_freq_store import UserFreqStore
from stroke_input.engine.inference_engine import ScoredCandidate

logger = logging.getLogger(__name__)

# Default weights for composite scoring
DEFAULT_WEIGHT_STATIC_FREQ = 0.4
DEFAULT_WEIGHT_USER_FREQ = 0.3
DEFAULT_WEIGHT_CONTEXT_BOOST = 0.2
DEFAULT_WEIGHT_MATCH_QUALITY = 0.1

# Match quality scores
MATCH_QUALITY_EXACT = 1.0
MATCH_QUALITY_FUZZY = 0.5

# Boost applied to Traditional Chinese characters
_TRADITIONAL_BOOST = 0.05

# Maximum user frequency used for normalization
_USER_FREQ_NORM_CAP = 100.0


def _is_likely_traditional(character: str) -> bool:
    """Heuristic check if a character is likely Traditional Chinese.

    Uses CJK Unified Ideographs range and checks for characters that are
    commonly used in Traditional Chinese (Taiwan/Hong Kong) but not in
    Simplified Chinese.  This is a lightweight heuristic — not exhaustive.

    A character is considered "likely traditional" if it falls in the CJK
    Unified Ideographs Extension ranges (U+3400–U+4DBF, U+20000–U+2A6DF)
    or has a code point above U+9000 in the main CJK block, which tends to
    contain more Traditional-only forms.
    """
    cp = ord(character[0]) if character else 0
    # CJK Unified Ideographs: U+4E00–U+9FFF
    # Characters above U+9000 are more likely Traditional-only
    if 0x9000 <= cp <= 0x9FFF:
        return True
    # CJK Extension A (rare/traditional forms)
    if 0x3400 <= cp <= 0x4DBF:
        return True
    # CJK Extension B (rare/traditional forms)
    if 0x20000 <= cp <= 0x2A6DF:
        return True
    return False


@dataclass
class RankerWeights:
    """Configurable weights for the composite scoring formula.

    Attributes:
        static_freq: Weight for the static character frequency.
        user_freq: Weight for the user adaptation score.
        context_boost: Weight for contextual relevance.
        match_quality: Weight for match quality (exact vs fuzzy).
    """

    static_freq: float = DEFAULT_WEIGHT_STATIC_FREQ
    user_freq: float = DEFAULT_WEIGHT_USER_FREQ
    context_boost: float = DEFAULT_WEIGHT_CONTEXT_BOOST
    match_quality: float = DEFAULT_WEIGHT_MATCH_QUALITY


class FrequencyRanker:
    """Ranks candidates using a weighted composite score.

    The ranker combines four signals:

    1. **Static frequency** — from the stroke database (CharacterRecord.frequency).
    2. **User adaptation** — how often the user has selected this character
       (from UserFreqStore), normalized to [0, 1].
    3. **Contextual relevance** — boost from phrase associations
       (ScoredCandidate.context_boost), normalized to [0, 1].
    4. **Match quality** — 1.0 for exact prefix matches, 0.5 for fuzzy.

    Tie-breaking:
    - Fewer strokes first (stroke_count ascending).
    - Traditional Chinese forms boosted above Simplified.

    Usage::

        ranker = FrequencyRanker(user_freq_store)
        ranked = ranker.rank(candidates)
    """

    def __init__(
        self,
        user_freq_store: Optional[UserFreqStore] = None,
        weights: Optional[RankerWeights] = None,
    ) -> None:
        self._user_freq = user_freq_store
        self._weights = weights or RankerWeights()

    @property
    def weights(self) -> RankerWeights:
        """Current ranking weights."""
        return self._weights

    def composite_score(self, candidate: ScoredCandidate) -> float:
        """Compute the composite ranking score for a single candidate.

        Args:
            candidate: A scored candidate from the InferenceEngine.

        Returns:
            The composite score (higher is better).
        """
        w = self._weights
        rec = candidate.record

        # 1. Static frequency (already in [0, 1] range typically)
        static_freq = rec.frequency

        # 2. User adaptation score (normalized)
        user_score = 0.0
        if self._user_freq:
            raw = self._user_freq.get_score(rec.character)
            user_score = min(raw / _USER_FREQ_NORM_CAP, 1.0)

        # 3. Contextual boost (normalize — phrase frequencies can vary)
        ctx = min(candidate.context_boost, 1.0)

        # 4. Match quality
        mq = MATCH_QUALITY_EXACT if candidate.is_exact else MATCH_QUALITY_FUZZY

        score = (
            w.static_freq * static_freq
            + w.user_freq * user_score
            + w.context_boost * ctx
            + w.match_quality * mq
        )

        # Traditional Chinese boost
        if _is_likely_traditional(rec.character):
            score += _TRADITIONAL_BOOST

        return score

    def rank(self, candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
        """Sort candidates by composite score descending.

        Tie-breaking order:
        1. Composite score (descending — higher first)
        2. Stroke count (ascending — fewer strokes first)
        3. Traditional Chinese preference (traditional first)

        Args:
            candidates: Unranked list of scored candidates.

        Returns:
            A new list sorted by composite ranking.
        """
        if not candidates:
            return []

        def sort_key(c: ScoredCandidate) -> tuple[float, int, int]:
            score = self.composite_score(c)
            # Negate score for descending sort; stroke_count ascending
            # Traditional boost: 0 (traditional) sorts before 1 (simplified)
            trad = 0 if _is_likely_traditional(c.record.character) else 1
            return (-score, c.record.stroke_count, trad)

        return sorted(candidates, key=sort_key)
