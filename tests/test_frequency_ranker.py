"""Unit tests for FrequencyRanker composite scoring and ranking."""

import pytest
from pathlib import Path

from stroke_input.data.models import CharacterRecord
from stroke_input.data.user_freq_store import UserFreqStore
from stroke_input.engine.frequency_ranker import (
    FrequencyRanker,
    RankerWeights,
    MATCH_QUALITY_EXACT,
    MATCH_QUALITY_FUZZY,
    _is_traditional_preferred,
)
from stroke_input.engine.inference_engine import ScoredCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(
    char: str,
    strokes: list[int],
    freq: float = 0.5,
    is_exact: bool = True,
    context_boost: float = 0.0,
    script_flag: str = "",
) -> ScoredCandidate:
    """Build a ScoredCandidate for testing."""
    rec = CharacterRecord(
        character=char,
        stroke_sequence=strokes,
        frequency=freq,
        script_flag=script_flag,
    )
    return ScoredCandidate(record=rec, is_exact=is_exact, context_boost=context_boost)


# ---------------------------------------------------------------------------
# Composite score tests
# ---------------------------------------------------------------------------

class TestCompositeScore:
    """Tests for the composite_score method."""

    def test_exact_match_scores_higher_than_fuzzy(self):
        ranker = FrequencyRanker()
        exact = _candidate("大", [1, 3, 4], freq=0.5, is_exact=True)
        fuzzy = _candidate("大", [1, 3, 4], freq=0.5, is_exact=False)
        assert ranker.composite_score(exact) > ranker.composite_score(fuzzy)

    def test_higher_static_freq_scores_higher(self):
        ranker = FrequencyRanker()
        high = _candidate("大", [1, 3, 4], freq=0.9, is_exact=True)
        low = _candidate("小", [2, 3, 4], freq=0.1, is_exact=True)
        assert ranker.composite_score(high) > ranker.composite_score(low)

    def test_context_boost_increases_score(self):
        ranker = FrequencyRanker()
        boosted = _candidate("好", [3, 2, 1], freq=0.5, context_boost=0.8)
        plain = _candidate("好", [3, 2, 1], freq=0.5, context_boost=0.0)
        assert ranker.composite_score(boosted) > ranker.composite_score(plain)

    def test_user_freq_increases_score(self, tmp_path: Path):
        store = UserFreqStore(tmp_path / "freq.json")
        for _ in range(50):
            store.increment("大")
        ranker = FrequencyRanker(user_freq_store=store)
        c = _candidate("大", [1, 3, 4], freq=0.5)
        score_with_user = ranker.composite_score(c)

        ranker_no_user = FrequencyRanker()
        score_without_user = ranker_no_user.composite_score(c)
        assert score_with_user > score_without_user

    def test_score_without_user_store(self):
        """Ranker works fine without a UserFreqStore."""
        ranker = FrequencyRanker()
        c = _candidate("人", [3, 4], freq=0.7)
        score = ranker.composite_score(c)
        assert score > 0

    def test_custom_weights(self):
        weights = RankerWeights(static_freq=1.0, user_freq=0.0, context_boost=0.0, match_quality=0.0)
        ranker = FrequencyRanker(weights=weights)
        c = _candidate("大", [1, 3, 4], freq=0.8)
        # Score should be dominated by static_freq
        score = ranker.composite_score(c)
        # static_freq * 0.8 + traditional boost (if applicable)
        assert score >= 0.8


# ---------------------------------------------------------------------------
# Ranking order tests
# ---------------------------------------------------------------------------

class TestRanking:
    """Tests for the rank method ordering."""

    def test_higher_frequency_ranked_first(self):
        ranker = FrequencyRanker()
        candidates = [
            _candidate("低", [1, 3, 2, 1, 4], freq=0.2),
            _candidate("大", [1, 3, 4], freq=0.9),
            _candidate("中", [2, 5, 1, 2], freq=0.5),
        ]
        ranked = ranker.rank(candidates)
        chars = [c.record.character for c in ranked]
        assert chars.index("大") < chars.index("中")
        assert chars.index("中") < chars.index("低")

    def test_stroke_count_tiebreak(self):
        """When composite scores are equal, fewer strokes should rank first."""
        # Use same frequency and match quality, no user freq or context
        weights = RankerWeights(static_freq=1.0, user_freq=0.0, context_boost=0.0, match_quality=0.0)
        ranker = FrequencyRanker(weights=weights)
        # Two characters with same frequency but different stroke counts
        few = _candidate("一", [1], freq=0.5)
        many = _candidate("三", [1, 1, 1], freq=0.5)
        ranked = ranker.rank([many, few])
        assert ranked[0].record.character == "一"
        assert ranked[1].record.character == "三"

    def test_exact_before_fuzzy(self):
        ranker = FrequencyRanker()
        exact = _candidate("大", [1, 3, 4], freq=0.5, is_exact=True)
        fuzzy = _candidate("天", [1, 1, 3, 4], freq=0.5, is_exact=False)
        ranked = ranker.rank([fuzzy, exact])
        assert ranked[0].record.character == "大"

    def test_empty_candidates(self):
        ranker = FrequencyRanker()
        assert ranker.rank([]) == []

    def test_single_candidate(self):
        ranker = FrequencyRanker()
        c = _candidate("人", [3, 4], freq=0.7)
        ranked = ranker.rank([c])
        assert len(ranked) == 1
        assert ranked[0].record.character == "人"

    def test_traditional_preferred_over_simplified(self):
        """Conway trad-only marker should rank above unmarked when scores are close."""
        weights = RankerWeights(
            static_freq=1.0,
            user_freq=0.0,
            context_boost=0.0,
            match_quality=0.0,
            trigram=0.0,
            recency=0.0,
            position=0.0,
        )
        ranker = FrequencyRanker(weights=weights)
        trad = _candidate("體", [1] * 5, freq=0.5, script_flag="trad")
        simp = _candidate("体", [1] * 5, freq=0.5, script_flag="simp")
        ranked = ranker.rank([simp, trad])
        assert ranked[0].record.character == "體"


# ---------------------------------------------------------------------------
# Traditional Chinese detection (Conway markers)
# ---------------------------------------------------------------------------

class TestTraditionalDetection:
    """Tests for _is_traditional_preferred using Conway script_flag."""

    def test_trad_flag(self):
        rec = CharacterRecord(character="體", stroke_sequence=[1], script_flag="trad")
        assert _is_traditional_preferred(rec) is True

    def test_simp_flag(self):
        rec = CharacterRecord(character="体", stroke_sequence=[1], script_flag="simp")
        assert _is_traditional_preferred(rec) is False

    def test_shared_flag(self):
        rec = CharacterRecord(character="大", stroke_sequence=[1], script_flag="")
        assert _is_traditional_preferred(rec) is False
