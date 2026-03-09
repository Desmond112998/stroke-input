"""Unit tests for InferenceEngine (fuzzy matching + contextual boost)."""

import pytest

from stroke_input.data.models import CharacterRecord, PhraseEntry
from stroke_input.data.phrase_loader import PhraseDict
from stroke_input.engine.inference_engine import InferenceEngine, ScoredCandidate
from stroke_input.engine.stroke_engine import StrokeEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_records() -> list[CharacterRecord]:
    """Small set of known character records for testing."""
    return [
        CharacterRecord(character="一", stroke_sequence=[1], frequency=0.9),
        CharacterRecord(character="二", stroke_sequence=[1, 1], frequency=0.8),
        CharacterRecord(character="三", stroke_sequence=[1, 1, 1], frequency=0.7),
        CharacterRecord(character="十", stroke_sequence=[1, 2], frequency=0.85),
        CharacterRecord(character="大", stroke_sequence=[1, 3, 4], frequency=0.95),
        CharacterRecord(character="人", stroke_sequence=[3, 4], frequency=0.92),
        CharacterRecord(character="丁", stroke_sequence=[1, 2], frequency=0.3),
        CharacterRecord(character="八", stroke_sequence=[3, 4], frequency=0.5),
        CharacterRecord(character="力", stroke_sequence=[5, 3], frequency=0.6),
    ]


def _make_phrase_dict(entries: list[tuple[str, float]]) -> PhraseDict:
    """Build a PhraseDict from (phrase, frequency) tuples."""
    pd = PhraseDict()
    phrase_entries = [PhraseEntry(phrase=p, frequency=f) for p, f in entries]
    pd._build_index(phrase_entries)
    return pd


@pytest.fixture
def engine() -> StrokeEngine:
    return StrokeEngine(_make_records())


@pytest.fixture
def phrase_dict() -> PhraseDict:
    return _make_phrase_dict([
        ("大人", 0.9),
        ("大力", 0.7),
        ("人大", 0.5),
        ("十二", 0.6),
    ])


@pytest.fixture
def ie(engine: StrokeEngine, phrase_dict: PhraseDict) -> InferenceEngine:
    return InferenceEngine(engine, phrase_dict)


@pytest.fixture
def ie_no_phrases(engine: StrokeEngine) -> InferenceEngine:
    return InferenceEngine(engine, phrase_dict=None)


# ---------------------------------------------------------------------------
# Exact matching passthrough
# ---------------------------------------------------------------------------

class TestExactMatching:
    """InferenceEngine should return exact prefix matches from StrokeEngine."""

    def test_exact_matches_returned(self, ie: InferenceEngine):
        candidates = ie.query([1])
        exact = [c for c in candidates if c.is_exact]
        chars = {c.record.character for c in exact}
        # All chars starting with HENG(1)
        assert "一" in chars
        assert "二" in chars
        assert "十" in chars
        assert "大" in chars

    def test_empty_sequence_returns_empty(self, ie: InferenceEngine):
        assert ie.query([]) == []

    def test_no_match_returns_empty(self, ie: InferenceEngine):
        assert ie.query([5, 5, 5, 5, 5]) == []


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

class TestFuzzyMatching:
    """Fuzzy matches appear when fewer than 3 exact prefix matches exist."""

    def test_fuzzy_matches_when_few_exact(self, ie: InferenceEngine):
        # [5, 3] matches only 力 exactly (1 match < 3 threshold)
        candidates = ie.query([5, 3])
        exact = [c for c in candidates if c.is_exact]
        fuzzy = [c for c in candidates if not c.is_exact]
        assert len(exact) == 1
        assert exact[0].record.character == "力"
        # Fuzzy should find chars with one-stroke substitution
        assert len(fuzzy) > 0

    def test_fuzzy_matches_ranked_below_exact(self, ie: InferenceEngine):
        candidates = ie.query([5, 3])
        # Find the boundary: all exact should come before all fuzzy
        exact_indices = [i for i, c in enumerate(candidates) if c.is_exact]
        fuzzy_indices = [i for i, c in enumerate(candidates) if not c.is_exact]
        if exact_indices and fuzzy_indices:
            assert max(exact_indices) < min(fuzzy_indices)

    def test_no_fuzzy_when_enough_exact(self, ie: InferenceEngine):
        # [1] matches 一,二,三,十,大,丁 (6 matches >= 3 threshold)
        candidates = ie.query([1])
        fuzzy = [c for c in candidates if not c.is_exact]
        assert len(fuzzy) == 0

    def test_fuzzy_excludes_exact_duplicates(self, ie: InferenceEngine):
        # Fuzzy results should not duplicate exact matches
        candidates = ie.query([5, 3])
        chars = [c.record.character for c in candidates]
        assert len(chars) == len(set(chars))


# ---------------------------------------------------------------------------
# Contextual boost
# ---------------------------------------------------------------------------

class TestContextualBoost:
    """After selecting a character, related follow-up chars get boosted."""

    def test_boost_after_selection(self, ie: InferenceEngine):
        ie.on_character_selected("大")
        # "大人" and "大力" are phrases → 人 and 力 should be boosted
        candidates = ie.query([3, 4])
        boosted = {c.record.character: c.context_boost for c in candidates}
        assert boosted.get("人", 0.0) > 0.0

    def test_boosted_char_ranks_higher(self, ie: InferenceEngine):
        ie.on_character_selected("大")
        # Query [3, 4] → exact matches: 人(freq=0.92), 八(freq=0.5)
        # 人 should be boosted (from "大人" phrase), 八 should not
        candidates = ie.query([3, 4])
        exact = [c for c in candidates if c.is_exact]
        chars = [c.record.character for c in exact]
        # 人 should come first due to both higher frequency and boost
        assert chars[0] == "人"

    def test_no_boost_without_selection(self, ie: InferenceEngine):
        candidates = ie.query([3, 4])
        for c in candidates:
            assert c.context_boost == 0.0

    def test_clear_context_resets_boost(self, ie: InferenceEngine):
        ie.on_character_selected("大")
        ie.clear_context()
        candidates = ie.query([3, 4])
        for c in candidates:
            assert c.context_boost == 0.0

    def test_no_phrase_dict_no_crash(self, ie_no_phrases: InferenceEngine):
        ie_no_phrases.on_character_selected("大")
        candidates = ie_no_phrases.query([1])
        assert len(candidates) > 0


# ---------------------------------------------------------------------------
# Sorting / ranking
# ---------------------------------------------------------------------------

class TestRanking:
    """Verify composite sorting within exact and fuzzy groups."""

    def test_exact_sorted_by_frequency(self, ie: InferenceEngine):
        # [1, 2] matches 十(0.85) and 丁(0.3) — both exact
        candidates = ie.query([1, 2])
        exact = [c for c in candidates if c.is_exact]
        assert len(exact) == 2
        assert exact[0].record.character == "十"
        assert exact[1].record.character == "丁"

    def test_context_boost_affects_sort_order(self, ie: InferenceEngine):
        ie.on_character_selected("十")
        # "十二" phrase → 二 gets boosted
        # [1, 1] matches 二(freq=0.8) and 三(freq=0.7, via prefix)
        candidates = ie.query([1, 1])
        exact = [c for c in candidates if c.is_exact]
        chars = [c.record.character for c in exact]
        # 二 should be first due to context boost
        assert chars[0] == "二"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_single_stroke_fuzzy(self, ie: InferenceEngine):
        # [4] matches no character exactly in our fixture
        # (no char starts with DIAN alone as full sequence)
        # But fuzzy substitution of 4→1 gives [1] which matches 一
        candidates = ie.query([4])
        # Should have fuzzy results since 0 exact < 3
        chars = {c.record.character for c in candidates}
        assert len(candidates) > 0

    def test_last_selected_property(self, ie: InferenceEngine):
        assert ie.last_selected is None
        ie.on_character_selected("大")
        assert ie.last_selected == "大"
        ie.clear_context()
        assert ie.last_selected is None

    def test_uses_engine_current_sequence(self, ie: InferenceEngine):
        ie._engine.append_stroke(1)
        ie._engine.append_stroke(2)
        candidates = ie.query()
        chars = {c.record.character for c in candidates}
        assert "十" in chars
        assert "丁" in chars
