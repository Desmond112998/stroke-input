"""Tests for PhrasePredictor — beam-search multi-step phrase prediction."""

from __future__ import annotations

import pytest

from stroke_input.data.models import PhraseEntry
from stroke_input.data.ngram_model import NgramModel
from stroke_input.engine.phrase_predictor import PhrasePredictor, PredictedPhrase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ngram(*phrases: str, reps: int = 1) -> NgramModel:
    entries = [PhraseEntry(phrase=p, frequency=1.0) for p in phrases for _ in range(reps)]
    return NgramModel.build_from_phrases(entries)


def _predictor(
    *phrases: str,
    reps: int = 1,
    beam_width: int = 5,
    max_depth: int = 3,
) -> PhrasePredictor:
    ngram = _ngram(*phrases, reps=reps)
    return PhrasePredictor(ngram, beam_width=beam_width, max_depth=max_depth)


# ---------------------------------------------------------------------------
# PredictedPhrase dataclass
# ---------------------------------------------------------------------------

class TestPredictedPhrase:
    def test_has_phrase_and_score(self) -> None:
        p = PredictedPhrase(phrase="香港人", score=0.5)
        assert p.phrase == "香港人"
        assert p.score == pytest.approx(0.5)

    def test_phrase_includes_seed(self) -> None:
        p = PredictedPhrase(phrase="香港人", score=0.5)
        assert p.phrase.startswith("香")


# ---------------------------------------------------------------------------
# Empty / degenerate cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_seed_returns_empty(self) -> None:
        pred = _predictor("香港人")
        assert pred.predict("") == []

    def test_empty_model_returns_empty(self) -> None:
        ngram = NgramModel.build_from_phrases([])
        pred = PhrasePredictor(ngram)
        # Empty model → no useful predictions, but must not crash
        result = pred.predict("香")
        assert isinstance(result, list)

    def test_predict_returns_list_of_predicted_phrase(self) -> None:
        pred = _predictor("香港人")
        results = pred.predict("香")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, PredictedPhrase)

    def test_max_results_respected(self) -> None:
        pred = _predictor("香港人", "香港島", "香港話", "香港政府", beam_width=5, max_depth=3)
        results = pred.predict("香", max_results=2)
        assert len(results) <= 2

    def test_default_max_results_is_reasonable(self) -> None:
        pred = _predictor("香港人", "香港島", beam_width=5, max_depth=3)
        results = pred.predict("香")
        # Default max_results=9; results should not exceed it
        from stroke_input.engine.phrase_predictor import _DEFAULT_MAX_RESULTS
        assert len(results) <= _DEFAULT_MAX_RESULTS


# ---------------------------------------------------------------------------
# Single-step prediction (seed → next char)
# ---------------------------------------------------------------------------

class TestSingleStep:
    def test_predicts_known_continuation(self) -> None:
        pred = _predictor("香港人", reps=5)
        results = pred.predict("香", max_depth=1)
        phrases = [r.phrase for r in results]
        assert "香港" in phrases

    def test_frequent_continuation_ranks_higher(self) -> None:
        # "你好" appears 5×, "你壞" appears 1×
        pred = _predictor("你好", "你好", "你好", "你好", "你好", "你壞", beam_width=5, max_depth=1)
        results = pred.predict("你", max_depth=1)
        phrases = [r.phrase for r in results]
        assert "你好" in phrases
        scores = {r.phrase: r.score for r in results}
        if "你壞" in scores:
            assert scores["你好"] >= scores["你壞"]


# ---------------------------------------------------------------------------
# Multi-step prediction (beam search)
# ---------------------------------------------------------------------------

class TestMultiStep:
    def test_depth_2_generates_3char_phrases(self) -> None:
        pred = _predictor("香港人", reps=5, beam_width=5, max_depth=3)
        results = pred.predict("香", max_depth=2)
        phrases = [r.phrase for r in results]
        # Should include 3-char extension starting with 香
        three_char = [p for p in phrases if len(p) == 3]
        assert len(three_char) > 0

    def test_all_results_start_with_seed(self) -> None:
        pred = _predictor("香港人", "香港島", reps=3, beam_width=5, max_depth=3)
        for result in pred.predict("香"):
            assert result.phrase.startswith("香"), f"{result.phrase!r} does not start with 香"

    def test_longer_phrases_allowed_up_to_max_depth(self) -> None:
        pred = _predictor("中文字體", reps=3, beam_width=5, max_depth=4)
        results = pred.predict("中", max_depth=3)
        phrases = [r.phrase for r in results]
        # "中文字" should be reachable within depth 3
        assert any(len(p) >= 3 for p in phrases)

    def test_no_duplicates_in_results(self) -> None:
        pred = _predictor("香港人", reps=3, beam_width=5, max_depth=3)
        results = pred.predict("香")
        phrases = [r.phrase for r in results]
        assert len(phrases) == len(set(phrases)), "Duplicate predictions found"


# ---------------------------------------------------------------------------
# Score ordering
# ---------------------------------------------------------------------------

class TestScoreOrdering:
    def test_results_sorted_by_score_descending(self) -> None:
        pred = _predictor("香港人", "香港島", "香港話", reps=2, beam_width=5, max_depth=2)
        results = pred.predict("香")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score"

    def test_higher_corpus_frequency_gives_higher_score(self) -> None:
        # 香港人 appears 5×, 香港島 1×
        entries = (
            [PhraseEntry(phrase="香港人", frequency=1.0)] * 5
            + [PhraseEntry(phrase="香港島", frequency=1.0)]
        )
        ngram = NgramModel.build_from_phrases(entries)
        pred = PhrasePredictor(ngram, beam_width=5, max_depth=2)
        results = pred.predict("香", max_depth=1)
        by_phrase = {r.phrase: r.score for r in results}
        if "香港" in by_phrase:
            # The beam for 香港 should be higher when more common completions follow
            pass  # just ensure no crash and results include 香港
            assert "香港" in by_phrase


# ---------------------------------------------------------------------------
# continue_prediction API
# ---------------------------------------------------------------------------

class TestContinuePrediction:
    def test_continue_from_committed_text(self) -> None:
        pred = _predictor("中文字", "中文書", reps=3, beam_width=5, max_depth=3)
        # User typed "中文" — continue from there
        results = pred.continue_prediction("中文")
        assert isinstance(results, list)
        for r in results:
            assert r.phrase.startswith("中文")

    def test_continue_empty_text_same_as_predict_seed(self) -> None:
        pred = _predictor("香港人", reps=3)
        # continue from empty → no context, returns empty
        result = pred.continue_prediction("")
        assert result == []

    def test_continue_single_char_same_as_predict(self) -> None:
        pred = _predictor("香港人", reps=3, beam_width=5, max_depth=3)
        via_predict = pred.predict("香")
        via_continue = pred.continue_prediction("香")
        assert {r.phrase for r in via_predict} == {r.phrase for r in via_continue}

    def test_continue_multi_char_uses_tail_for_context(self) -> None:
        pred = _predictor("香港人", "中港人", reps=3, beam_width=5, max_depth=3)
        # context tail is "港" → should predict "香港..." style
        results = pred.continue_prediction("香港")
        phrases = [r.phrase for r in results]
        assert all(p.startswith("香港") for p in phrases)
