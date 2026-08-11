"""Tests for A4 enhancements to FrequencyRanker:
- RankingContext dataclass
- New weights: trigram, recency, position
- composite_score() uses RankingContext
- InferenceEngine propagates last_two context
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

from stroke_input.data.models import CharacterRecord, PhraseEntry
from stroke_input.data.ngram_model import NgramModel
from stroke_input.data.user_freq_store import UserFreqStore
from stroke_input.engine.frequency_ranker import (
    FrequencyRanker,
    RankerWeights,
    RankingContext,
)
from stroke_input.engine.inference_engine import InferenceEngine, ScoredCandidate
from stroke_input.engine.stroke_engine import StrokeEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rec(char: str, freq: float = 0.5, strokes: list[int] | None = None) -> CharacterRecord:
    s = strokes or [1]
    return CharacterRecord(character=char, stroke_sequence=s, frequency=freq)


def _cand(char: str, freq: float = 0.5, is_exact: bool = True) -> ScoredCandidate:
    return ScoredCandidate(record=_rec(char, freq=freq), is_exact=is_exact)


def _ngram(*phrases: str) -> NgramModel:
    entries = [PhraseEntry(phrase=p, frequency=1.0) for p in phrases]
    return NgramModel.build_from_phrases(entries)


# ---------------------------------------------------------------------------
# RankingContext
# ---------------------------------------------------------------------------

class TestRankingContext:
    def test_defaults(self) -> None:
        ctx = RankingContext()
        assert ctx.prev1 is None
        assert ctx.prev2 is None
        assert ctx.stroke_seq == ""
        assert ctx.now > 0

    def test_custom_values(self) -> None:
        ctx = RankingContext(prev1="你", prev2="我", stroke_seq="jk")
        assert ctx.prev1 == "你"
        assert ctx.prev2 == "我"
        assert ctx.stroke_seq == "jk"

    def test_now_defaults_to_current_time(self) -> None:
        before = time.time()
        ctx = RankingContext()
        after = time.time()
        assert before <= ctx.now <= after


# ---------------------------------------------------------------------------
# RankerWeights — new fields default to 0
# ---------------------------------------------------------------------------

class TestRankerWeightsNewFields:
    def test_new_fields_exist_and_default_zero(self) -> None:
        w = RankerWeights()
        assert hasattr(w, "trigram")
        assert hasattr(w, "recency")
        assert hasattr(w, "position")
        from stroke_input.config.ranking import (
            WEIGHT_POSITION,
            WEIGHT_RECENCY,
            WEIGHT_TRIGRAM,
        )
        assert w.trigram == WEIGHT_TRIGRAM
        assert w.recency == WEIGHT_RECENCY
        assert w.position == WEIGHT_POSITION

    def test_existing_defaults_unchanged(self) -> None:
        from stroke_input.engine.frequency_ranker import (
            DEFAULT_WEIGHT_STATIC_FREQ,
            DEFAULT_WEIGHT_USER_FREQ,
            DEFAULT_WEIGHT_CONTEXT_BOOST,
            DEFAULT_WEIGHT_MATCH_QUALITY,
        )
        w = RankerWeights()
        assert w.static_freq == DEFAULT_WEIGHT_STATIC_FREQ
        assert w.user_freq == DEFAULT_WEIGHT_USER_FREQ
        assert w.context_boost == DEFAULT_WEIGHT_CONTEXT_BOOST
        assert w.match_quality == DEFAULT_WEIGHT_MATCH_QUALITY


# ---------------------------------------------------------------------------
# composite_score with RankingContext
# ---------------------------------------------------------------------------

class TestCompositeScoreWithContext:
    def test_trigram_boost_increases_score(self) -> None:
        """Candidate that fits the trigram context should score higher."""
        ngram = _ngram("香港人")
        weights = RankerWeights(
            static_freq=0.0, user_freq=0.0, context_boost=0.0,
            match_quality=0.0, trigram=1.0, recency=0.0, position=0.0
        )
        ranker = FrequencyRanker(weights=weights, ngram_model=ngram)

        ctx_fit = RankingContext(prev1="港", prev2="香")
        ctx_no = RankingContext(prev1="文", prev2="中")

        c = _cand("人")
        score_fit = ranker.composite_score(c, context=ctx_fit)
        score_no = ranker.composite_score(c, context=ctx_no)
        assert score_fit > score_no

    def test_recency_boost_increases_score(self, tmp_path: Path) -> None:
        store = UserFreqStore(tmp_path / "freq.json")
        now = time.time()
        store.record_selection("好", timestamp=now)  # just selected

        weights = RankerWeights(
            static_freq=0.0, user_freq=0.0, context_boost=0.0,
            match_quality=0.0, trigram=0.0, recency=1.0, position=0.0
        )
        ranker = FrequencyRanker(user_freq_store=store, weights=weights)
        ctx = RankingContext(now=now)

        c_recent = _cand("好")
        c_never = _cand("壞")
        assert ranker.composite_score(c_recent, context=ctx) > \
               ranker.composite_score(c_never, context=ctx)

    def test_position_boost_increases_score(self, tmp_path: Path) -> None:
        store = UserFreqStore(tmp_path / "freq.json")
        store.record_position("jk", "你", rank=0)  # always picked first

        weights = RankerWeights(
            static_freq=0.0, user_freq=0.0, context_boost=0.0,
            match_quality=0.0, trigram=0.0, recency=0.0, position=1.0
        )
        ranker = FrequencyRanker(user_freq_store=store, weights=weights)
        ctx = RankingContext(stroke_seq="jk")

        c_pin = _cand("你")
        c_other = _cand("他")
        assert ranker.composite_score(c_pin, context=ctx) > \
               ranker.composite_score(c_other, context=ctx)

    def test_no_context_arg_uses_zero_new_weights(self) -> None:
        """When no context is passed, new signals contribute 0 (backwards compat)."""
        ngram = _ngram("香港人")
        store = UserFreqStore(Path("dummy.json"))
        weights = RankerWeights(trigram=0.5, recency=0.5, position=0.5)
        ranker = FrequencyRanker(user_freq_store=store, weights=weights, ngram_model=ngram)
        c = _cand("人", freq=0.5)
        # Should not raise; new signals silently contribute 0
        score = ranker.composite_score(c)
        assert score >= 0

    def test_composite_score_signature_no_context_still_works(self) -> None:
        """Old call-site: composite_score(candidate) without context."""
        ranker = FrequencyRanker()
        c = _cand("大", freq=0.8)
        score = ranker.composite_score(c)
        assert score > 0


# ---------------------------------------------------------------------------
# rank() with RankingContext
# ---------------------------------------------------------------------------

class TestRankWithContext:
    def test_rank_accepts_context_kwarg(self) -> None:
        ranker = FrequencyRanker()
        ctx = RankingContext()
        candidates = [_cand("大"), _cand("小")]
        result = ranker.rank(candidates, context=ctx)
        assert len(result) == 2

    def test_trigram_context_reorders_candidates(self) -> None:
        ngram = _ngram("香港人", "香港島", "香港話")
        weights = RankerWeights(
            static_freq=0.1, user_freq=0.0, context_boost=0.0,
            match_quality=0.0, trigram=1.0, recency=0.0, position=0.0
        )
        ranker = FrequencyRanker(weights=weights, ngram_model=ngram)
        ctx = RankingContext(prev1="港", prev2="香")

        # All same static freq — trigram decides
        candidates = [
            _cand("人", freq=0.5),
            _cand("島", freq=0.5),
            _cand("X", freq=0.5),  # unseen in trigram → lower
        ]
        ranked = ranker.rank(candidates, context=ctx)
        chars = [c.record.character for c in ranked]
        # 人 and 島 should both rank above X
        assert chars.index("X") > chars.index("人")
        assert chars.index("X") > chars.index("島")


# ---------------------------------------------------------------------------
# InferenceEngine last_two context propagation (A4)
# ---------------------------------------------------------------------------

class TestInferenceEngineTwoContext:
    def _engine_with_chars(self, chars: list[str]) -> StrokeEngine:
        records = [
            CharacterRecord(character=ch, stroke_sequence=[1], frequency=0.5)
            for ch in chars
        ]
        return StrokeEngine(records)

    def test_on_character_selected_updates_last_two(self) -> None:
        se = self._engine_with_chars(["你", "好", "中"])
        ie = InferenceEngine(se)
        ie.on_character_selected("你")
        assert ie.last_selected == "你"
        assert ie.prev_selected is None

        ie.on_character_selected("好")
        assert ie.last_selected == "好"
        assert ie.prev_selected == "你"

    def test_clear_context_resets_last_two(self) -> None:
        se = self._engine_with_chars(["你"])
        ie = InferenceEngine(se)
        ie.on_character_selected("你")
        ie.on_character_selected("好")
        ie.clear_context()
        assert ie.last_selected is None
        assert ie.prev_selected is None

    def test_three_selections_shifts_ring(self) -> None:
        se = self._engine_with_chars(["甲", "乙", "丙"])
        ie = InferenceEngine(se)
        ie.on_character_selected("甲")
        ie.on_character_selected("乙")
        ie.on_character_selected("丙")
        assert ie.last_selected == "丙"
        assert ie.prev_selected == "乙"
        # 甲 is now out of the two-slot window
