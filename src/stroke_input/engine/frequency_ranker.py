"""FrequencyRanker: composite scoring and ranking for stroke input candidates.

Combines static frequency, user adaptation score, contextual relevance,
match quality, trigram language model score, recency, and position-aware
signal into a single composite score for candidate ordering.

Composite score formula (v2):
    score = w_static   * static_freq
          + w_user     * user_freq
          + w_context  * context_boost
          + w_match    * match_quality
          + w_trigram  * trigram_score     (requires NgramModel + RankingContext)
          + w_recency  * recency_score     (requires UserFreqStore + RankingContext)
          + w_position * position_score   (requires UserFreqStore + RankingContext)

The three new weights (trigram, recency, position) default to 0.0, so all
existing callers continue to work unchanged.

Pass a :class:`RankingContext` to :meth:`FrequencyRanker.composite_score` or
:meth:`FrequencyRanker.rank` to activate the new signals.

Secondary sort: stroke_count ascending (fewer strokes first) when composite
scores are equal.

Traditional Chinese forms receive a small boost over Simplified forms.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from stroke_input.data.ngram_model import NgramModel
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
class RankingContext:
    """Per-query context passed to FrequencyRanker for enhanced scoring.

    Attributes:
        prev1: The immediately preceding selected character, or None.
        prev2: The character before prev1, or None.  Only used when
               prev1 is also set.
        stroke_seq: Current stroke prefix string (e.g. ``"jk"``), used for
                    position-aware scoring.
        now: Reference Unix timestamp for recency scoring.  Defaults to the
             current time at construction.
    """

    prev1: Optional[str] = None
    prev2: Optional[str] = None
    stroke_seq: str = ""
    now: float = field(default_factory=time.time)


@dataclass
class RankerWeights:
    """Configurable weights for the composite scoring formula.

    The three new fields (trigram, recency, position) default to 0.0 for
    full backwards compatibility with existing call sites.

    Attributes:
        static_freq: Weight for the static character frequency.
        user_freq: Weight for the user adaptation score.
        context_boost: Weight for contextual relevance (phrase bigram).
        match_quality: Weight for match quality (exact vs fuzzy).
        trigram: Weight for the trigram language model score.
        recency: Weight for the recency decay score.
        position: Weight for the position-aware learning score.
    """

    static_freq: float = DEFAULT_WEIGHT_STATIC_FREQ
    user_freq: float = DEFAULT_WEIGHT_USER_FREQ
    context_boost: float = DEFAULT_WEIGHT_CONTEXT_BOOST
    match_quality: float = DEFAULT_WEIGHT_MATCH_QUALITY
    trigram: float = 0.0
    recency: float = 0.0
    position: float = 0.0


class FrequencyRanker:
    """Ranks candidates using a weighted composite score.

    The ranker combines up to seven signals:

    1. **Static frequency** — from the stroke database (CharacterRecord.frequency).
    2. **User adaptation** — how often the user has selected this character
       (from UserFreqStore), normalized to [0, 1].
    3. **Contextual relevance** — boost from phrase associations
       (ScoredCandidate.context_boost), normalized to [0, 1].
    4. **Match quality** — 1.0 for exact prefix matches, 0.5 for fuzzy.
    5. **Trigram score** — P(char | prev2, prev1) from NgramModel. *(opt)*
    6. **Recency score** — exp(-Δt/τ) from UserFreqStore timestamps. *(opt)*
    7. **Position score** — 1/(1+avg_rank) from UserFreqStore positions. *(opt)*

    Signals 5-7 require a :class:`RankingContext` and (for 6-7) a
    :class:`~stroke_input.data.user_freq_store.UserFreqStore`.  When no
    context is provided, or the corresponding weight is 0, these signals
    silently contribute 0.

    Tie-breaking:
    - Fewer strokes first (stroke_count ascending).
    - Traditional Chinese forms boosted above Simplified.

    Usage::

        ranker = FrequencyRanker(user_freq_store, ngram_model=ngram)
        ctx = RankingContext(prev1="港", prev2="香", stroke_seq="jk")
        ranked = ranker.rank(candidates, context=ctx)
    """

    def __init__(
        self,
        user_freq_store: Optional[UserFreqStore] = None,
        weights: Optional[RankerWeights] = None,
        ngram_model: Optional[NgramModel] = None,
    ) -> None:
        self._user_freq = user_freq_store
        self._weights = weights or RankerWeights()
        self._ngram = ngram_model

    @property
    def weights(self) -> RankerWeights:
        """Current ranking weights."""
        return self._weights

    def composite_score(
        self,
        candidate: ScoredCandidate,
        context: Optional[RankingContext] = None,
    ) -> float:
        """Compute the composite ranking score for a single candidate.

        Args:
            candidate: A scored candidate from the InferenceEngine.
            context: Optional per-query context for trigram/recency/position
                     signals.  When ``None``, new signals contribute 0.

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
        ctx_boost = min(candidate.context_boost, 1.0)

        # 4. Match quality
        mq = MATCH_QUALITY_EXACT if candidate.is_exact else MATCH_QUALITY_FUZZY

        score = (
            w.static_freq * static_freq
            + w.user_freq * user_score
            + w.context_boost * ctx_boost
            + w.match_quality * mq
        )

        # 5–7: Context-dependent signals
        if context is not None:
            # 5. Trigram score
            if w.trigram > 0 and self._ngram is not None:
                tri = self._ngram.score(
                    rec.character,
                    prev1=context.prev1,
                    prev2=context.prev2,
                )
                score += w.trigram * tri

            # 6. Recency score
            if w.recency > 0 and self._user_freq is not None:
                recency = self._user_freq.recency_score(
                    rec.character, now=context.now
                )
                score += w.recency * recency

            # 7. Position score
            if w.position > 0 and self._user_freq is not None:
                pos = self._user_freq.position_score(
                    context.stroke_seq, rec.character
                )
                score += w.position * pos

        # Traditional Chinese boost
        if _is_likely_traditional(rec.character):
            score += _TRADITIONAL_BOOST

        return score

    def rank(
        self,
        candidates: list[ScoredCandidate],
        context: Optional[RankingContext] = None,
    ) -> list[ScoredCandidate]:
        """Sort candidates by composite score descending.

        Tie-breaking order:
        1. Composite score (descending — higher first)
        2. Stroke count (ascending — fewer strokes first)
        3. Traditional Chinese preference (traditional first)

        Args:
            candidates: Unranked list of scored candidates.
            context: Optional per-query context (see :class:`RankingContext`).

        Returns:
            A new list sorted by composite ranking.
        """
        if not candidates:
            return []

        def sort_key(c: ScoredCandidate) -> tuple[float, int, int]:
            score = self.composite_score(c, context=context)
            trad = 0 if _is_likely_traditional(c.record.character) else 1
            return (-score, c.record.stroke_count, trad)

        return sorted(candidates, key=sort_key)
