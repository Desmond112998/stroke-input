"""Tests for NgramModel — unigram/bigram/trigram language model with add-k smoothing."""

from __future__ import annotations

import pytest

from stroke_input.data.models import PhraseEntry
from stroke_input.data.ngram_model import NgramModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_phrases(*texts: str, freq: float = 0.0) -> list[PhraseEntry]:
    """Build phrases. Default freq=0 → count weight 1 (see NGRAM_FREQ_WEIGHT_K)."""
    return [PhraseEntry(phrase=t, frequency=freq) for t in texts]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestBuild:
    def test_build_from_empty(self) -> None:
        m = NgramModel.build_from_phrases([])
        assert m.vocab_size == 0

    def test_build_from_single_bigram(self) -> None:
        phrases = _make_phrases("你好")
        m = NgramModel.build_from_phrases(phrases)
        assert m.vocab_size == 2  # 你, 好

    def test_build_from_trigram_phrase(self) -> None:
        phrases = _make_phrases("中文字")
        m = NgramModel.build_from_phrases(phrases)
        assert m.vocab_size == 3

    def test_build_counts_repeated_chars(self) -> None:
        # 中 appears as first char in both, so unigram count should be 2
        phrases = _make_phrases("中文", "中國")
        m = NgramModel.build_from_phrases(phrases)
        assert m.unigram_count("中") == 2

    def test_build_counts_bigrams(self) -> None:
        phrases = _make_phrases("你好", "你們")
        m = NgramModel.build_from_phrases(phrases)
        assert m.bigram_count("你", "好") == 1
        assert m.bigram_count("你", "們") == 1

    def test_build_counts_trigrams(self) -> None:
        phrases = _make_phrases("中文字")
        m = NgramModel.build_from_phrases(phrases)
        assert m.trigram_count("中", "文", "字") == 1

    def test_single_char_phrase_ignored_for_bigram(self) -> None:
        # Single-char phrase should contribute to unigram only (or be skipped)
        phrases = _make_phrases("中")
        m = NgramModel.build_from_phrases(phrases)
        # No bigrams expected
        assert m.bigram_count("中", "中") == 0

    def test_multiple_occurrences_accumulate(self) -> None:
        phrases = _make_phrases("你好", "你好", "你好")
        m = NgramModel.build_from_phrases(phrases)
        assert m.bigram_count("你", "好") == 3

    def test_phrase_frequency_weights_counts(self) -> None:
        low = NgramModel.build_from_phrases(_make_phrases("你好", freq=0.0))
        high = NgramModel.build_from_phrases(_make_phrases("你好", freq=1.0))
        assert high.bigram_count("你", "好") > low.bigram_count("你", "好")
        assert low.bigram_count("你", "好") == 1
        assert high.bigram_count("你", "好") == 11  # 1 + round(1.0 * 10)


# ---------------------------------------------------------------------------
# Scoring — unigram
# ---------------------------------------------------------------------------

class TestUnigramScore:
    def test_known_char_has_positive_score(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        assert m.unigram_score("你") > 0

    def test_unknown_char_has_positive_score_due_to_smoothing(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        # add-k smoothing ensures unseen chars still get > 0
        assert m.unigram_score("未") > 0

    def test_frequent_char_scores_higher_than_rare(self) -> None:
        phrases = _make_phrases("你好", "你們", "你是")  # 你 appears 3×
        m = NgramModel.build_from_phrases(phrases)
        assert m.unigram_score("你") > m.unigram_score("好")

    def test_score_is_in_0_1_range(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("中文", "中國", "香港"))
        for ch in "中文國香港X":
            s = m.unigram_score(ch)
            assert 0.0 < s <= 1.0, f"unigram_score({ch!r}) = {s} out of (0,1]"


# ---------------------------------------------------------------------------
# Scoring — bigram
# ---------------------------------------------------------------------------

class TestBigramScore:
    def test_known_bigram_higher_than_unknown(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        assert m.bigram_score("你", "好") > m.bigram_score("你", "壞")

    def test_unknown_prev_falls_back_to_unigram(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        # prev "X" is completely unknown → should not crash, returns > 0 via smoothing
        assert m.bigram_score("X", "好") > 0

    def test_score_is_in_0_1_range(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("中文字", "中文書"))
        for ch in "中文字書X":
            s = m.bigram_score("中", ch)
            assert 0.0 < s <= 1.0, f"bigram_score('中', {ch!r}) = {s}"


# ---------------------------------------------------------------------------
# Scoring — trigram
# ---------------------------------------------------------------------------

class TestTrigramScore:
    def test_known_trigram_higher_than_unknown(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("中文字"))
        assert m.trigram_score("中", "文", "字") > m.trigram_score("中", "文", "書")

    def test_unknown_trigram_context_falls_back_gracefully(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        s = m.trigram_score("X", "Y", "好")
        assert s > 0

    def test_score_is_in_0_1_range(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("香港人", "香港島", "香港話"))
        for ch in "香港人島話X":
            s = m.trigram_score("香", "港", ch)
            assert 0.0 < s <= 1.0, f"trigram_score('香','港',{ch!r}) = {s}"


# ---------------------------------------------------------------------------
# Unified score() API — interpolated
# ---------------------------------------------------------------------------

class TestScoreAPI:
    def test_no_context_equals_unigram(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好", "中文"))
        # When no prev context, score should equal unigram_score
        assert m.score("你") == pytest.approx(m.unigram_score("你"), rel=1e-6)

    def test_one_context_uses_bigram_interpolation(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("你好"))
        s_ctx = m.score("好", prev1="你")
        s_no_ctx = m.score("好")
        # With positive bigram context the score should be higher
        assert s_ctx >= s_no_ctx

    def test_two_context_uses_trigram_interpolation(self) -> None:
        m = NgramModel.build_from_phrases(_make_phrases("中文字"))
        s_tri = m.score("字", prev1="文", prev2="中")
        s_bi = m.score("字", prev1="文")
        s_uni = m.score("字")
        # trigram context should rank highest among known sequence
        assert s_tri >= s_bi >= s_uni

    def test_score_in_0_1_range(self) -> None:
        phrases = _make_phrases("香港人", "香港島")
        m = NgramModel.build_from_phrases(phrases)
        for char in "香港人島X":
            for p1 in [None, "香", "X"]:
                for p2 in [None, "港", "Y"]:
                    s = m.score(char, prev1=p1, prev2=p2)
                    assert 0.0 < s <= 1.0, f"score out of range: ({p2},{p1}) → {char} = {s}"

    def test_empty_model_score_is_positive(self) -> None:
        m = NgramModel.build_from_phrases([])
        # Pure smoothing: score should be > 0 even with empty model
        assert m.score("你") > 0
        assert m.score("你", prev1="好") > 0
        assert m.score("你", prev1="好", prev2="中") > 0


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_round_trip(self) -> None:
        phrases = _make_phrases("你好", "中文字", "香港人")
        m = NgramModel.build_from_phrases(phrases)
        data = m.to_dict()
        m2 = NgramModel.from_dict(data)
        assert m2.vocab_size == m.vocab_size
        assert m2.unigram_count("你") == m.unigram_count("你")
        assert m2.bigram_count("你", "好") == m.bigram_count("你", "好")
        assert m2.trigram_count("中", "文", "字") == m.trigram_count("中", "文", "字")

    def test_scores_preserved_after_round_trip(self) -> None:
        phrases = _make_phrases("香港人")
        m = NgramModel.build_from_phrases(phrases)
        m2 = NgramModel.from_dict(m.to_dict())
        assert m2.score("人", prev1="港", prev2="香") == pytest.approx(
            m.score("人", prev1="港", prev2="香"), rel=1e-6
        )


# ---------------------------------------------------------------------------
# Smoothing parameter
# ---------------------------------------------------------------------------

class TestSmoothing:
    def test_larger_k_reduces_difference_between_known_and_unknown(self) -> None:
        phrases = _make_phrases("你好", "你好", "你好")
        m_low = NgramModel.build_from_phrases(phrases, k=0.001)
        m_high = NgramModel.build_from_phrases(phrases, k=10.0)

        diff_low = m_low.unigram_score("你") - m_low.unigram_score("未知")
        diff_high = m_high.unigram_score("你") - m_high.unigram_score("未知")
        assert diff_low > diff_high  # high k → more uniform

    def test_zero_k_unknown_still_works(self) -> None:
        # k=0 is valid only for seen chars; unseen chars may be 0 — that's OK
        phrases = _make_phrases("你好")
        m = NgramModel.build_from_phrases(phrases, k=0.0)
        # Known bigram should still score > 0
        assert m.bigram_score("你", "好") > 0
